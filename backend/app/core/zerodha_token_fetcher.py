"""
Zerodha Semi-Automated Token Fetcher
─────────────────────────────────────
Uses Selenium to open the Kite Connect login page in a real browser window.

Flow:
  1. We open: https://kite.zerodha.com/connect/login?api_key=<KEY>&v=3
  2. Browser window appears — user manually types their password + TOTP
  3. Zerodha redirects to the callback URL with ?request_token=<TOKEN>
  4. We detect the redirect, extract request_token, close the browser
  5. Caller gets the request_token to exchange for an access_token

Environments:
  - Windows (local dev): Opens a visible Chrome window, user logs in manually.
  - Docker/Linux: Runs Chrome in headless mode. User must complete login via
    a VNC viewer or this feature is not usable in headless Docker.
"""
import asyncio
import glob
import os
import sys
import time
from typing import AsyncGenerator
from urllib.parse import urlparse, parse_qs

import structlog

logger = structlog.get_logger()

KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"
POLL_INTERVAL = 0.5   # seconds between URL checks
MAX_WAIT = 180        # seconds before timeout (3 minutes)

IS_WINDOWS = sys.platform == "win32"


def _get_chrome_version() -> str | None:
    """Read installed Chrome version from the Windows registry / filesystem."""
    try:
        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe):
            chrome_exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe):
            return None
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-Item '{chrome_exe}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip()
        return version if version else None
    except Exception:
        return None


def _find_chromedriver_exe() -> str:
    """
    Locate chromedriver on Windows by scanning the webdriver-manager cache.
    Strategy:
      1. Get installed Chrome version (e.g. 145.0.7632.77)
      2. Look for chromedriver-win64/chromedriver.exe for that exact version
      3. Fall back to any win64 chromedriver.exe in cache (newest first)
      4. Fall back to any win32 chromedriver.exe in cache (newest first)
      5. Last resort: 'chromedriver' on PATH
    On Linux: always return 'chromedriver' (installed via apt).
    """
    if not IS_WINDOWS:
        logger.info("zerodha_token_fetcher.chromedriver", platform="linux", path="chromedriver")
        return "chromedriver"

    home = os.path.expanduser("~")
    wdm_cache = os.path.join(home, ".wdm", "drivers", "chromedriver")

    # Step 1 — try exact Chrome version match with win64
    chrome_ver = _get_chrome_version()
    if chrome_ver:
        exact = os.path.join(wdm_cache, "win64", chrome_ver, "chromedriver-win64", "chromedriver.exe")
        if os.path.isfile(exact):
            logger.info("zerodha_token_fetcher.chromedriver_exact", path=exact, version=chrome_ver)
            return exact

    # Step 2 — scan entire cache, strongly prefer win64
    if os.path.isdir(wdm_cache):
        all_drivers = glob.glob(os.path.join(wdm_cache, "**", "chromedriver.exe"), recursive=True)
        if all_drivers:
            win64 = [p for p in all_drivers if "chromedriver-win64" in p]
            win32 = [p for p in all_drivers if "chromedriver-win64" not in p]
            win64.sort(key=os.path.getmtime, reverse=True)
            win32.sort(key=os.path.getmtime, reverse=True)
            chosen = (win64 + win32)[0]
            logger.info("zerodha_token_fetcher.chromedriver_found", path=chosen)
            return chosen

    logger.warning("zerodha_token_fetcher.chromedriver_fallback", note="Using chromedriver from PATH")
    return "chromedriver"


async def fetch_zerodha_request_token(
    api_key: str,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields status events and finally the request_token.

    Yields dicts:
      {"status": "opening",  "message": "Opening browser..."}
      {"status": "waiting",  "message": "Waiting for login..."}
      {"status": "success",  "message": "Token captured!", "request_token": "<TOKEN>"}
      {"status": "error",    "message": "<reason>"}
    """
    login_url = f"{KITE_LOGIN_URL}?api_key={api_key}&v=3"

    if IS_WINDOWS:
        yield {"status": "opening", "message": "Launching Chrome browser window..."}
    else:
        yield {"status": "opening", "message": "Launching headless Chrome (Docker mode)..."}

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _selenium_worker():
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            chromedriver_path = _find_chromedriver_exe()

            options = Options()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if IS_WINDOWS:
                # Visible window on Windows — user logs in manually
                options.add_argument("--window-size=520,700")
            else:
                # Headless mode in Docker/Linux
                options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1280,800")

            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)

            # Remove navigator.webdriver flag so Zerodha doesn't detect automation
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "status": "waiting",
                    "message": "Browser opened. Please log in with your Zerodha credentials (password + TOTP).",
                },
            )

            driver.get(login_url)

            # Poll the URL until we see ?request_token= in the redirect
            elapsed = 0
            request_token = None
            while elapsed < MAX_WAIT:
                current_url = driver.current_url
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)

                if "request_token" in params:
                    request_token = params["request_token"][0]
                    break

                if "error" in params:
                    error_msg = params.get("error_description", ["Login failed"])[0]
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"status": "error", "message": f"Zerodha returned error: {error_msg}"},
                    )
                    return

                time.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL

                # Heartbeat every 10 seconds
                if int(elapsed) % 10 == 0 and elapsed > 0:
                    remaining = MAX_WAIT - int(elapsed)
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"status": "waiting", "message": f"Still waiting for login... ({remaining}s remaining)"},
                    )

            if request_token:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "status": "success",
                        "message": "Request token captured successfully! Closing browser...",
                        "request_token": request_token,
                    },
                )
            else:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"status": "error", "message": f"Timed out after {MAX_WAIT}s. Please try again."},
                )

        except Exception as e:
            logger.error("zerodha_token_fetcher.error", error=str(e))
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"status": "error", "message": f"Browser error: {str(e)}"},
            )
        finally:
            if driver:
                try:
                    time.sleep(1.5)
                    driver.quit()
                except Exception:
                    pass
            loop.call_soon_threadsafe(queue.put_nowait, None)

    thread_future = loop.run_in_executor(None, _selenium_worker)

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
        if event.get("status") in ("success", "error"):
            break

    try:
        await asyncio.wait_for(thread_future, timeout=5)
    except asyncio.TimeoutError:
        pass
