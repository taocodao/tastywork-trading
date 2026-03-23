-- Migration: Add user_daily_orders table
-- Run date: 2026-03-22
-- Adds per-user IV-Switching strategy daily orders table

-- user_daily_orders: stores computed orders for each user per trading day
CREATE TABLE IF NOT EXISTS user_daily_orders (
    id                VARCHAR PRIMARY KEY,
    user_id           VARCHAR NOT NULL REFERENCES users(id),
    trade_date        DATE NOT NULL,

    -- Strategy context
    strategy_mode     VARCHAR,          -- A, B, C, D2, D3
    signal_type       VARCHAR,          -- OPEN_ZEBRA, OPEN_CSP, OPEN_CCS, OPEN_SQQQ,
                                        -- OPEN_ZEBRA_D3, HOLD, NO_ACTION, ERROR

    -- Account snapshot at computation time
    account_cash      FLOAT,
    account_nlv       FLOAT,
    account_bp        FLOAT,
    open_zebra_count  INTEGER DEFAULT 0,
    open_csp_count    INTEGER DEFAULT 0,
    open_ccs_count    INTEGER DEFAULT 0,
    open_sqqq_shares  INTEGER DEFAULT 0,

    -- Order details
    symbol            VARCHAR,          -- QQQM, TQQQ, QQQ, SQQQ
    option_type       VARCHAR,          -- ZEBRA, CSP, CCS, EQUITY
    contracts         INTEGER DEFAULT 0,
    capital_required  FLOAT DEFAULT 0,
    nav_pct           FLOAT DEFAULT 0,

    -- Exact TastyTrade-ready order legs (JSON)
    -- Example: [{"action":"BUY_TO_OPEN","symbol":"QQQM  260606C00480000","qty":2,"instrument_type":"Equity Option"}]
    order_legs        JSONB,

    -- Pricing
    limit_price       FLOAT,
    long_strike       FLOAT,
    short_strike      FLOAT,
    expiry_date       DATE,

    -- Status lifecycle: PENDING → CONFIRMED → PLACED → FILLED
    --                   PENDING → SKIPPED
    status            VARCHAR DEFAULT 'PENDING',
    order_id          VARCHAR,          -- TastyTrade order ID once placed
    fill_price        FLOAT,
    placed_at         TIMESTAMP,
    filled_at         TIMESTAMP,
    skip_reason       VARCHAR,

    -- Metadata
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP,
    generation_error  VARCHAR(500),

    -- Composite unique index: one record per user per day
    CONSTRAINT uq_user_daily_orders_user_date UNIQUE (user_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_user_daily_orders_user ON user_daily_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_user_daily_orders_date ON user_daily_orders(trade_date);
CREATE INDEX IF NOT EXISTS idx_user_daily_orders_status ON user_daily_orders(status);

-- Add iv_strategy_enabled + current_nav to users table if not present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='iv_strategy_enabled'
    ) THEN
        ALTER TABLE users ADD COLUMN iv_strategy_enabled BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='current_nav'
    ) THEN
        ALTER TABLE users ADD COLUMN current_nav FLOAT;
    END IF;
END
$$;
