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

This is "semi-automated":
  - We automate opening the browser and capturing the token
  - The user still types their own password and TOTP (we never touch those fields)

Fix for WinError 193:
  webdriver-manager 4.x has a bug on Windows where it returns the path to
  THIRD_PARTY_NOTICES.chromedriver (a text file) instead of chromedriver.exe.
  We bypass this by scanning the wdm cache for the actual .exe directly.
"""
import asyncio
import glob
import os
import time
from typing import AsyncGenerator
from urllib.parse import urlparse, parse_qs

import structlog

logger = structlog.get_logger()

KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"
POLL_INTERVAL = 0.5   # seconds between URL checks
MAX_WAIT = 180        # seconds before timeout (3 minutes)


def _find_chromedriver_exe() -> str:
    """
    Locate the correct 64-bit chromedriver.exe on Windows.

    webdriver-manager 4.x has two bugs on Windows:
      1. Returns path to THIRD_PARTY_NOTICES.chromedriver (text file) not the .exe
      2. Downloads chromedriver-win32 (32-bit) even on 64-bit systems

    Strategy:
      1. Prefer any path containing 'win64' in the wdm cache
      2. Fall back to any chromedriver.exe in the cache (sorted newest first)
      3. Last resort: 'chromedriver' on PATH
    """
    wdm_cache = os.path.expanduser("~/.wdm/drivers/chromedriver")
    if os.path.isdir(wdm_cache):
        pattern = os.path.join(wdm_cache, "**", "chromedriver.exe")
        matches = glob.glob(pattern, recursive=True)
        if matches:
            # Strongly prefer win64 builds over win32
            win64 = [p for p in matches if "win64" in p.replace("\\", "/")]
            win32 = [p for p in matches if "win64" not in p.replace("\\", "/")]

            # Within each group sort by mtime descending (newest version first)
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

    yield {"status": "opening", "message": "Launching browser window..."}

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _selenium_worker():
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            # Find the actual chromedriver.exe — bypasses webdriver-manager bug
            chromedriver_path = _find_chromedriver_exe()

            options = Options()
            options.add_argument("--window-size=520,700")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

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
