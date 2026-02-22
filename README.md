# 🚀 Kalpi Portfolio Execution Engine

An end-to-end portfolio trade execution engine for Indian stock markets. Connects to 5 major brokers, computes portfolio deltas, and executes trades in a single click.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  React Frontend (Vite + TypeScript + Tailwind)                    │
│  ├── Login / Register                                             │
│  ├── Broker Connect (5 brokers, OAuth + TOTP + API Key)          │
│  ├── Portfolio Upload (JSON editor with schema validation)        │
│  ├── Execute Button → Real-time WebSocket progress feed           │
│  └── Results Dashboard (order table, fill rate, P&L)             │
├──────────────────────────────────────────────────────────────────┤
│  FastAPI Backend                                                  │
│  ├── POST /api/v1/auth/login         JWT authentication           │
│  ├── POST /api/v1/broker/connect     Broker auth + session store  │
│  ├── GET  /api/v1/broker/holdings    Fetch current positions       │
│  ├── POST /api/v1/execution/validate Dry-run delta preview        │
│  ├── POST /api/v1/execution/execute  🚀 ONE-CLICK EXECUTION       │
│  ├── GET  /api/v1/execution/batches  Execution history            │
│  └── WS   /ws/{user_id}             Real-time WebSocket feed      │
├──────────────────────────────────────────────────────────────────┤
│  Core Engine                                                      │
│  ├── DeltaCalculator  → Current vs Target diff (3 pass algo)      │
│  ├── OrderRouter      → Rate-limit + exponential backoff retry    │
│  └── NotificationSvc  → WebSocket + Webhook + Console log         │
├──────────────────────────────────────────────────────────────────┤
│  Broker Adapters (Adapter Pattern — BrokerAdapter ABC)            │
│  ├── ZerodhaAdapter   Kite Connect v3 (OAuth2)                    │
│  ├── FyersAdapter     Fyers API v3 (OAuth2 + PKCE)               │
│  ├── AngelOneAdapter  SmartAPI (TOTP 2FA)                         │
│  ├── UpstoxAdapter    Upstox API v2 (OAuth2)                      │
│  └── GrowwAdapter     Groww Pro REST API (API Key)                │
├──────────────────────────────────────────────────────────────────┤
│  Infrastructure                                                   │
│  ├── PostgreSQL 15    Orders, sessions, audit trail               │
│  ├── Redis 7          Rate limiting, job queue                    │
│  └── Docker Compose   Full orchestration                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker Desktop
- Docker Compose

### 1. Clone and Start

```bash
git clone <repo>
cd portfolio-execution
docker-compose up --build
```

### 2. Access the Application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| Nginx (unified) | http://localhost:80 |

### 3. Login

Demo credentials:
- **Username**: `demo`
- **Password**: `demo123`

---

## Usage Flow

### Step 1: Connect a Broker

In the UI, click **Connect** next to any broker. In **Paper Trading mode** (default), any API key works — just type anything or leave blank.

For real trading:
- **Zerodha**: Get `api_key` + `api_secret` from [kite.trade](https://kite.trade), visit the login URL, get `request_token`
- **Fyers**: Get `api_key` + `api_secret` from [myapi.fyers.in](https://myapi.fyers.in), get `auth_code`
- **AngelOne**: Get `api_key` from [smartapi.angelbroking.com](https://smartapi.angelbroking.com), provide `client_id` + `password` + `totp_secret`
- **Upstox**: Get `api_key` + `api_secret` from [upstox.com/developer](https://upstox.com/developer), get OAuth `code`
- **Groww**: Get `api_key` + `api_secret` + `client_id` from Groww Pro

### Step 2: Upload Target Portfolio

Paste your target portfolio as JSON:

```json
[
  {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 10},
  {"symbol": "TCS", "exchange": "NSE", "quantity": 5},
  {"symbol": "INFY", "exchange": "NSE", "quantity": 20}
]
```

For rebalancing with explicit instructions:

```json
[
  {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 5, "instruction": "REBALANCE_SELL"},
  {"symbol": "SBIN", "exchange": "NSE", "quantity": 50, "instruction": "BUY_NEW"},
  {"symbol": "TCS", "exchange": "NSE", "quantity": 0, "instruction": "SELL_EXIT"}
]
```

### Step 3: Preview (Optional)

Click **"Preview Delta"** to see what orders will be placed without executing.

### Step 4: Execute

Click **"🚀 Execute Now"** — watch real-time order updates in the live feed.

---

## API Reference

### Authentication

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "email": "t@kalpi.com", "password": "secret123"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'
```

### Connect Broker (Paper Trading)

```bash
curl -X POST http://localhost:8000/api/v1/broker/connect \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"broker": "zerodha", "api_key": "any_key_for_paper_trading"}'
```

### Execute Portfolio

```bash
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
```

### WebSocket (Real-time Updates)

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${userId}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  // msg.type: "CONNECTED" | "ORDER_PROGRESS" | "EXECUTION_COMPLETE"
  console.log(msg);
};
```

---

## Design Decisions

### Adapter Pattern for Broker Integration

Each broker implements the `BrokerAdapter` abstract base class:

```python
class BrokerAdapter(ABC):
    async def authenticate(self) -> AuthResult: ...
    async def get_holdings(self) -> List[Holding]: ...
    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult: ...
    async def get_order_status(self, broker_order_id: str) -> PlaceOrderResult: ...
    async def cancel_order(self, broker_order_id: str) -> bool: ...
```

**Adding broker #6**: Create `backend/app/adapters/newbroker.py`, implement the 5 methods, add one entry to `BROKER_REGISTRY` in `__init__.py`. Zero other changes needed.

### Delta Calculation Algorithm

```
Pass 1: For each target stock:
  - Not in current → BUY_NEW
  - target > current → REBALANCE_BUY (buy the difference)
  - target < current → REBALANCE_SELL (sell the difference)
  - target == current → skip

Pass 2: For each current stock not in target:
  - SELL_EXIT (full exit)

Ordering: SELLs first → free capital → then BUYs
```

### Retry Logic

```
Attempt 1 → fail → wait 2s
Attempt 2 → fail → wait 4s  (exponential backoff)
Attempt 3 → fail → wait 8s
→ Mark order as FAILED, continue with next order
```

No retry on: `REJECTED` (bad symbol, insufficient funds) — permanent failures.
Retry on: network errors, HTTP 5xx (transient broker failures).

### Notification Channels

1. **WebSocket** — real-time push during execution (per-order progress + final summary)
2. **Webhook** — HTTP POST to configured URL after execution completes
3. **Console** — structured JSON log (always active, for audit trail)

---

## Paper Trading Mode

All orders are simulated by default (`PAPER_TRADING=true`). The simulation:
- Returns realistic broker order IDs (`PAPER-XXXXXXXXXXXX`)
- Simulates ~95% fill rate, ~5% rejection rate
- Uses random prices in ₹100–₹5000 range
- Respects the same execution flow as live trading

To enable live trading:
```yaml
# docker-compose.yml
environment:
  PAPER_TRADING: "false"
```

---

## Project Structure

```
portfolio-execution/
├── backend/
│   ├── app/
│   │   ├── adapters/          # Broker adapters (Adapter Pattern)
│   │   │   ├── base.py        # BrokerAdapter ABC
│   │   │   ├── zerodha.py
│   │   │   ├── fyers.py
│   │   │   ├── angelone.py
│   │   │   ├── upstox.py
│   │   │   └── groww.py
│   │   ├── core/              # Execution engine
│   │   │   ├── delta_calculator.py
│   │   │   ├── order_router.py
│   │   │   └── execution_engine.py
│   │   ├── api/               # FastAPI routes
│   │   │   ├── auth.py
│   │   │   ├── broker.py
│   │   │   ├── execution.py
│   │   │   └── notifications.py
│   │   ├── models/            # SQLAlchemy ORM
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic
│   │   │   ├── auth_service.py
│   │   │   ├── broker_service.py
│   │   │   ├── notification_service.py
│   │   │   └── websocket_manager.py
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── init.sql               # DB schema + seed data
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/client.ts      # Axios + WebSocket setup
│   │   ├── components/        # React components
│   │   ├── pages/             # Page components
│   │   ├── store/auth.ts      # Auth state
│   │   └── types.ts           # TypeScript types
│   ├── Dockerfile
│   └── vite.config.ts
├── nginx/nginx.conf           # Reverse proxy config
├── docker-compose.yml
└── README.md
```



