# Kalpi Portfolio Execution Engine

An end-to-end portfolio trade execution engine for Indian stock markets, built for systematic and quantitative trading. Connect to 5 major Indian brokers, upload a target portfolio, and execute all required trades in a single click â€” with real-time progress, live funds validation, and full execution history.

---

## What This System Does

### Broker Connectivity (5 Brokers)
- Connects to **Zerodha, Fyers, AngelOne, Upstox, and Groww** via their official APIs
- Built on an **Adapter Pattern** â€” every broker implements the same interface, making it trivial to add a 6th broker
- Supports multiple auth flows: OAuth2 (Zerodha, Fyers, Upstox), TOTP 2FA (AngelOne), API Key (Groww)

### Semi-Automated Zerodha Login
- Instead of manually copying a `request_token` from a URL, the system opens a **real Chrome browser window** via Selenium
- You log in normally (enter your password + TOTP yourself â€” we never touch those fields)
- The system automatically detects the redirect URL, extracts the `request_token`, and closes the browser
- Status updates stream live to the UI via **Server-Sent Events (SSE)**

### Live Funds Validation
- After connecting a broker, the system immediately fetches your **real margin and funds** from the broker API
- Displays **Equity Segment** and **Commodity Segment** balances: Net Available, Cash, Opening Balance, Live Balance, Collateral, Debits, SPAN, Exposure
- A green "Broker connection verified" badge confirms the token is working â€” not just saved, but actually authenticated
- The nav bar shows **"LIVE"** (green) or **"PAPER TRADING"** (amber) based on the actual backend mode

### Credential Persistence
- All broker credentials are securely saved in the database: API Key, API Secret, Access Token, Refresh Token, Request Token, TOTP Secret, Client ID
- View saved credentials anytime via the collapsible **Credentials Panel** (masked by default, reveal on click)
- Credentials survive server restarts â€” no need to reconnect on every session

### Portfolio Delta Execution
- Upload a **target portfolio** as JSON (symbol, exchange, quantity)
- The engine fetches your **current holdings** from the broker
- Computes the **delta** (difference) using a 3-pass algorithm:
  - Stocks not in current holdings â†’ `BUY_NEW`
  - Target quantity > current â†’ `REBALANCE_BUY` (buy the difference)
  - Target quantity < current â†’ `REBALANCE_SELL` (sell the difference)
  - Stocks in current but not in target â†’ `SELL_EXIT`
  - SELLs are always executed before BUYs to free up capital
- Supports explicit instructions: `BUY_NEW`, `SELL_EXIT`, `REBALANCE_BUY`, `REBALANCE_SELL`

### Real-Time Execution Feed
- Click **Execute Now** and watch per-order status updates stream live via **WebSocket**
- Each order shows: symbol, side, quantity, status (PENDING â†’ PLACED â†’ FILLED / REJECTED)
- Toast notifications for every order fill or rejection

### Execution History
- Every execution is saved as a **batch** with full audit trail
- View past executions in the **Execution History** tab: status, fill rate, order count, timestamps
- Drill into any batch to see individual order details

### Dry-Run / Preview
- Click **Preview Delta** before executing to see exactly which orders will be placed
- Shows the computed delta without touching the broker

### Retry Logic with Exponential Backoff
- Failed orders are retried up to 3 times: wait 2s â†’ 4s â†’ 8s
- Permanent failures (bad symbol, insufficient funds) are not retried
- Transient failures (network, broker 5xx) are retried automatically

### Notifications
- **WebSocket**: real-time per-order progress during execution
- **Webhook**: HTTP POST to a configured URL after execution completes
- **Console**: structured JSON logs for full audit trail

### Paper Trading Mode
- Default mode â€” all orders are simulated, no real money involved
- Simulates ~95% fill rate, realistic broker order IDs, random prices
- Switch to live trading by setting `PAPER_TRADING=false` in `.env`

---



## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + Vite + TypeScript + Tailwind CSS |
| Backend | Python 3.11 + FastAPI + SQLAlchemy (async) |
| Database | PostgreSQL 15 (Docker) / SQLite (local dev) |
| Auth | JWT (python-jose) + bcrypt |
| Real-time | WebSocket (FastAPI native) + SSE (EventSource) |
| Browser Automation | Selenium + Chrome (Zerodha token fetch) |
| Containerization | Docker + Docker Compose + Nginx |

---

## Running with Docker (Recommended)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### 1. Clone the repo
```bash
git clone <repo-url>
cd portfolio-execution
```

### 2. Start all services
```bash
docker compose up --build
```

This builds and starts 4 containers:
- `kalpi_postgres` â€” PostgreSQL database
- `kalpi_backend` â€” FastAPI backend (port 8000)
- `kalpi_frontend` â€” React app served via Nginx (port 3000)
- `kalpi_nginx` â€” Reverse proxy (port 80)

First build takes 3-5 minutes. Wait for:
```
kalpi_backend | startup.complete paper_trading=False
kalpi_backend | Application startup complete.
```

### 3. Open the app
```
http://localhost:3000
```

### 4. Login with demo account
- **Username**: `demo`
- **Password**: `demo123`

### Other Docker Commands

```bash
# Run in background
docker compose up --build -d

# View all logs
docker compose logs -f

# View backend logs only
docker compose logs -f backend

# Stop everything
docker compose down

# Stop and wipe database (fresh start)
docker compose down -v

# Rebuild only the backend
docker compose up --build backend -d
```

---

## Running Locally (Without Docker)

### Prerequisites
- Python 3.11+
- Node.js 20+

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

# Set encoding for Windows
$env:PYTHONIOENCODING="utf-8"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend runs at: `http://localhost:8000`
API docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:5173`

> Local dev uses **SQLite** (no PostgreSQL needed). The database file `backend/kalpi.db` is created automatically on first run.

---

## Configuration

All settings are in `backend/.env`:

```env
# Trading mode â€” set to false for real broker API calls
PAPER_TRADING=false

# Database (SQLite for local, PostgreSQL for Docker)
DATABASE_URL=sqlite+aiosqlite:///./kalpi.db

# JWT secret â€” change in production
SECRET_KEY=your-secret-key-here

# CORS origins
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Docker overrides these via `docker-compose.yml` environment variables.

---

## Connecting a Real Zerodha Account

1. Go to [kite.trade](https://kite.trade) and create an app â€” get your `api_key` and `api_secret`
2. Set your app's redirect URL to `http://127.0.0.1` in the Kite Connect dashboard
3. In the UI, enter your `api_key`, then click **"Auto-Fetch Request Token (Opens Browser)"**
4. A Chrome window opens at the Zerodha login page
5. Enter your **Zerodha password** and **TOTP** manually
6. The system automatically captures the `request_token` from the redirect URL
7. Click **Connect** â€” the system exchanges the token for an `access_token` and saves everything
8. The **Live Funds** widget immediately shows your real equity and commodity margins

> Note: The browser automation (step 3-6) only works when running locally, not in Docker headless mode.

---

## API Reference

### Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'

# Register new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "email": "t@kalpi.com", "password": "secret123"}'
```

### Broker
```bash
# Connect broker (paper trading â€” any key works)
curl -X POST http://localhost:8000/api/v1/broker/connect \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"broker": "zerodha", "api_key": "any_key"}'

# Fetch live funds (validates connection is working)
curl http://localhost:8000/api/v1/broker/funds/zerodha \
  -H "Authorization: Bearer <token>"

# View saved credentials
curl http://localhost:8000/api/v1/broker/credentials/zerodha \
  -H "Authorization: Bearer <token>"
```

### Execution
```bash
# Preview delta (dry run)
curl -X POST http://localhost:8000/api/v1/execution/validate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "broker": "zerodha",
    "portfolio": {
      "execution_type": "AUTO",
      "holdings": [
        {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 10},
        {"symbol": "TCS", "exchange": "NSE", "quantity": 5}
      ]
    }
  }'

# Execute portfolio
curl -X POST http://localhost:8000/api/v1/execution/execute \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "broker": "zerodha",
    "portfolio": {
      "execution_type": "AUTO",
      "holdings": [
        {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 10},
        {"symbol": "TCS", "exchange": "NSE", "quantity": 5}
      ]
    }
  }'

# Execution history
curl http://localhost:8000/api/v1/execution/batches \
  -H "Authorization: Bearer <token>"
```

### WebSocket (Real-time)
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${userId}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  // msg.type: "CONNECTED" | "ORDER_PROGRESS" | "EXECUTION_COMPLETE"
};
```

---

## Project Structure

```
portfolio-execution/
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ adapters/           # Broker adapters (Adapter Pattern)
â”‚   â”‚   â”‚   â”œâ”€â”€ base.py         # BrokerAdapter ABC
â”‚   â”‚   â”‚   â”œâ”€â”€ zerodha.py
â”‚   â”‚   â”‚   â”œâ”€â”€ fyers.py
â”‚   â”‚   â”‚   â”œâ”€â”€ angelone.py
â”‚   â”‚   â”‚   â”œâ”€â”€ upstox.py
â”‚   â”‚   â”‚   â””â”€â”€ groww.py
â”‚   â”‚   â”œâ”€â”€ core/               # Execution engine
â”‚   â”‚   â”‚   â”œâ”€â”€ delta_calculator.py
â”‚   â”‚   â”‚   â”œâ”€â”€ order_router.py
â”‚   â”‚   â”‚   â”œâ”€â”€ execution_engine.py
â”‚   â”‚   â”‚   â”œâ”€â”€ zerodha_token_fetcher.py  # Selenium automation
â”‚   â”‚   â”‚   â””â”€â”€ seed.py
â”‚   â”‚   â”œâ”€â”€ api/                # FastAPI routes
â”‚   â”‚   â”‚   â”œâ”€â”€ auth.py
â”‚   â”‚   â”‚   â”œâ”€â”€ broker.py
â”‚   â”‚   â”‚   â”œâ”€â”€ execution.py
â”‚   â”‚   â”‚   â””â”€â”€ notifications.py
â”‚   â”‚   â”œâ”€â”€ models/             # SQLAlchemy ORM
â”‚   â”‚   â”œâ”€â”€ schemas/            # Pydantic schemas
â”‚   â”‚   â”œâ”€â”€ services/           # Business logic
â”‚   â”‚   â”‚   â”œâ”€â”€ auth_service.py
â”‚   â”‚   â”‚   â”œâ”€â”€ broker_service.py
â”‚   â”‚   â”‚   â”œâ”€â”€ notification_service.py
â”‚   â”‚   â”‚   â””â”€â”€ websocket_manager.py
â”‚   â”‚   â”œâ”€â”€ config.py
â”‚   â”‚   â”œâ”€â”€ database.py
â”‚   â”‚   â””â”€â”€ main.py
â”‚   â”œâ”€â”€ init.sql                # PostgreSQL schema
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â”œâ”€â”€ .env                    # Local environment config
â”‚   â””â”€â”€ Dockerfile
â”œâ”€â”€ frontend/
â”‚   â”œâ”€â”€ src/
â”‚   â”‚   â”œâ”€â”€ api/client.ts       # Axios + WebSocket + SSE setup
â”‚   â”‚   â”œâ”€â”€ components/
â”‚   â”‚   â”‚   â”œâ”€â”€ BrokerConnectPanel.tsx    # Broker connection + auto token fetch
â”‚   â”‚   â”‚   â”œâ”€â”€ BrokerFundsWidget.tsx     # Live margin display
â”‚   â”‚   â”‚   â”œâ”€â”€ BrokerCredentialsPanel.tsx # Saved credentials viewer
â”‚   â”‚   â”‚   â”œâ”€â”€ ExecutionPanel.tsx        # Portfolio upload + execute
â”‚   â”‚   â”‚   â”œâ”€â”€ ResultsPanel.tsx          # Execution results
â”‚   â”‚   â”‚   â””â”€â”€ HistoryPanel.tsx          # Past executions
â”‚   â”‚   â”œâ”€â”€ pages/
â”‚   â”‚   â”‚   â”œâ”€â”€ DashboardPage.tsx
â”‚   â”‚   â”‚   â””â”€â”€ LoginPage.tsx
â”‚   â”‚   â””â”€â”€ types.ts
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â””â”€â”€ vite.config.ts
â”œâ”€â”€ nginx/nginx.conf            # Reverse proxy config
â”œâ”€â”€ docker-compose.yml
â””â”€â”€ README.md
```

---

## Adding a New Broker

1. Create `backend/app/adapters/newbroker.py`
2. Implement the `BrokerAdapter` abstract class (5 methods):
   ```python
   class NewBrokerAdapter(BrokerAdapter):
       async def authenticate(self) -> AuthResult: ...
       async def get_holdings(self) -> List[Holding]: ...
       async def place_order(self, req: PlaceOrderRequest) -> PlaceOrderResult: ...
       async def get_order_status(self, order_id: str) -> PlaceOrderResult: ...
       async def cancel_order(self, order_id: str) -> bool: ...
       async def get_funds(self) -> FundsData: ...
   ```
3. Add one entry to `BROKER_REGISTRY` in `backend/app/adapters/__init__.py`
4. Add the broker name to the frontend `BROKERS` list in `BrokerConnectPanel.tsx`

No other changes needed.
