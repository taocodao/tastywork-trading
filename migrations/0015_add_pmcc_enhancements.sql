-- Migration: PMCC Enhancements to IV-Switching positions and orders
-- Run date: 2026-03-22
-- Adds columns for PMCC overlay tracking, stop-loss prices, and
-- short-call expiry tracking on top of the existing schema.

-- ── 1. user_daily_orders: new PMCC fields ──────────────────────────────────

ALTER TABLE user_daily_orders
    ADD COLUMN IF NOT EXISTS short_expiry_date   DATE,
    ADD COLUMN IF NOT EXISTS stop_loss_price     FLOAT,
    ADD COLUMN IF NOT EXISTS profit_target       FLOAT,
    ADD COLUMN IF NOT EXISTS roll_delta_trigger  FLOAT;

-- ── 2. iv_switching_positions: new PMCC overlay columns ────────────────────

ALTER TABLE iv_switching_positions
    ADD COLUMN IF NOT EXISTS overlay_contracts   INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS overlay_strike      FLOAT,
    ADD COLUMN IF NOT EXISTS overlay_expiry      DATE,
    ADD COLUMN IF NOT EXISTS overlay_premium     FLOAT,
    ADD COLUMN IF NOT EXISTS overlay_status      VARCHAR DEFAULT 'NONE',
    -- 'NONE' | 'ACTIVE' | 'CLOSED_PROFIT' | 'CLOSED_ROLLED'
    ADD COLUMN IF NOT EXISTS stop_loss_price     FLOAT,
    ADD COLUMN IF NOT EXISTS stop_loss_triggered BOOLEAN DEFAULT FALSE;

-- ── 3. Add 'OVERLAY_SHORT_CALL' and 'HOLD_LEAPS_DEFENSE' to known signal_types
--       (No ENUM change needed if signal_type is VARCHAR — just documenting)
-- Valid signal_type values now:
--   OPEN_ZEBRA, OPEN_ZEBRA_D3, OPEN_CSP, OPEN_CCS, OPEN_SQQQ
--   OVERLAY_SHORT_CALL   <-- P3 new
--   HOLD_LEAPS_DEFENSE   <-- P4 new
--   NO_ACTION, ERROR

-- ── 4. Index for overlay status lookups ────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ivs_positions_overlay
    ON iv_switching_positions (user_id, overlay_status)
    WHERE overlay_status = 'ACTIVE';
