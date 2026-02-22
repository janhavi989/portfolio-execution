-- Portfolio Execution Engine - Database Initialization
-- PostgreSQL schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Broker Sessions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,          -- zerodha, fyers, angelone, upstox, groww
    access_token TEXT,
    refresh_token TEXT,
    api_key VARCHAR(255),
    api_secret VARCHAR(255),
    client_id VARCHAR(255),
    session_data JSONB DEFAULT '{}',      -- broker-specific extra fields
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, broker)
);

-- ─── Execution Batches ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,
    execution_type VARCHAR(30) NOT NULL,  -- FIRST_TIME, REBALANCE
    status VARCHAR(30) DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, COMPLETED, PARTIAL, FAILED
    target_portfolio JSONB NOT NULL,      -- uploaded target
    current_holdings JSONB DEFAULT '[]',  -- snapshot at execution time
    delta_orders JSONB DEFAULT '[]',      -- computed delta
    summary JSONB DEFAULT '{}',           -- result summary
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ─── Orders ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID REFERENCES execution_batches(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,
    broker_order_id VARCHAR(255),         -- ID returned by broker
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'NSE',
    order_type VARCHAR(20) NOT NULL,      -- BUY, SELL
    instruction_type VARCHAR(20) NOT NULL,-- BUY_NEW, SELL_EXIT, REBALANCE_BUY, REBALANCE_SELL
    quantity INTEGER NOT NULL,
    price DECIMAL(12, 4),                 -- NULL = market order
    order_status VARCHAR(30) DEFAULT 'PENDING', -- PENDING, PLACED, FILLED, REJECTED, FAILED
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price DECIMAL(12, 4),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    raw_response JSONB DEFAULT '{}',
    placed_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Notifications ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    batch_id UUID REFERENCES execution_batches(id) ON DELETE CASCADE,
    channel VARCHAR(30) NOT NULL,         -- WEBSOCKET, WEBHOOK, CONSOLE
    payload JSONB NOT NULL,
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_broker_sessions_user ON broker_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_execution_batches_user ON execution_batches(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_batch ON orders(batch_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

-- ─── Seed Demo User ───────────────────────────────────────────────────────
-- Password: demo123  (bcrypt hash)
INSERT INTO users (username, email, hashed_password) VALUES
    ('demo', 'demo@kalpi.com', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW')
ON CONFLICT DO NOTHING;



