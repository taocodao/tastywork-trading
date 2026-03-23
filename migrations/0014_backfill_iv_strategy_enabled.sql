-- Migration: Backfill iv_strategy_enabled for TurboCore Pro users
-- Run date: 2026-03-22
-- Automatically enables iv_strategy_enabled for any user who has
-- turbocore_pro or both_bundle subscription (active or trialing).

-- One-time backfill
UPDATE users
SET iv_strategy_enabled = TRUE
WHERE id IN (
    SELECT us.user_id
    FROM user_settings us
    WHERE us.subscription_tier IN ('turbocore_pro', 'both_bundle')
      AND us.subscription_status IN ('active', 'trialing')
);

-- Ensure future subs auto-activate on any tier change:
-- Create a trigger that syncs iv_strategy_enabled from user_settings

CREATE OR REPLACE FUNCTION sync_iv_strategy_enabled()
RETURNS TRIGGER AS $$
BEGIN
    -- Enable when upgrading to turbocore_pro or both_bundle
    IF NEW.subscription_tier IN ('turbocore_pro', 'both_bundle')
       AND NEW.subscription_status IN ('active', 'trialing') THEN
        UPDATE users
        SET iv_strategy_enabled = TRUE
        WHERE id = NEW.user_id;

    -- Disable when subscription is cancelled or downgraded
    ELSIF NEW.subscription_status NOT IN ('active', 'trialing') THEN
        UPDATE users
        SET iv_strategy_enabled = FALSE
        WHERE id = NEW.user_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_iv_strategy ON user_settings;
CREATE TRIGGER trg_sync_iv_strategy
AFTER INSERT OR UPDATE OF subscription_tier, subscription_status
ON user_settings
FOR EACH ROW
EXECUTE FUNCTION sync_iv_strategy_enabled();
