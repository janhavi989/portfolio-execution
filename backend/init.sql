-- Portfolio Execution Engine - Database Initialization
-- PostgreSQL schema

-- ─── Users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ─── Broker Sessions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    api_key VARCHAR(255),
    api_secret VARCHAR(255),
    client_id VARCHAR(255),
    session_data JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, broker)
);

-- ─── Execution Batches ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_batches (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,
    execution_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) DEFAULT 'PENDING',
    target_portfolio JSONB NOT NULL,
    current_holdings JSONB DEFAULT '[]',
    delta_orders JSONB DEFAULT '[]',
    summary JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- ─── Orders ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(36) PRIMARY KEY,
    batch_id VARCHAR(36) REFERENCES execution_batches(id) ON DELETE CASCADE,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50) NOT NULL,
    broker_order_id VARCHAR(255),
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'NSE',
    order_type VARCHAR(20) NOT NULL,
    instruction_type VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(12, 4),
    order_status VARCHAR(30) DEFAULT 'PENDING',
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price DECIMAL(12, 4),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    raw_response JSONB DEFAULT '{}',
    placed_at TIMESTAMP,
    filled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ─── Notifications ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    batch_id VARCHAR(36) REFERENCES execution_batches(id) ON DELETE CASCADE,
    channel VARCHAR(30) NOT NULL,
    payload JSONB NOT NULL,
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ─── Indexes ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_broker_sessions_user ON broker_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_execution_batches_user ON execution_batches(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_batch ON orders(batch_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

-- Seed handled by backend startup (seed.py) — no hardcoded insert needed here.



