-- 回滾 001：還原舊 daily_chips（含遷移後新寫入的資料），之後需同時部署遷移前的程式碼。
-- 需要 daily_chips_pre001 仍存在（尚未執行 001_cleanup.sql）。
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = 'daily_chips_pre001') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                   AND table_name = 'daily_chips' AND column_name = 'margin_long') THEN
            RAISE NOTICE 'rollback: daily_chips is already the old schema, nothing to do';
            RETURN;
        END IF;
        RAISE EXCEPTION 'rollback: daily_chips_pre001 not found (cleanup already ran?)';
    END IF;

    LOCK TABLE daily_chips IN ACCESS EXCLUSIVE MODE;
    LOCK TABLE market_daily IN ACCESS EXCLUSIVE MODE;

    -- 遷移後新寫入的個股資料寫回舊表（股 → 張）
    INSERT INTO daily_chips_pre001 (date, stock_id, foreign_buy, trust_buy, dealer_buy)
    SELECT date, stock_id, round(foreign_buy / 1000.0, 3), round(trust_buy / 1000.0, 3), round(dealer_buy / 1000.0, 3)
    FROM daily_chips
    ON CONFLICT (date, stock_id) DO UPDATE SET
        foreign_buy = EXCLUDED.foreign_buy, trust_buy = EXCLUDED.trust_buy, dealer_buy = EXCLUDED.dealer_buy;

    -- 大盤資料寫回 stock_id='0000'
    INSERT INTO daily_chips_pre001 (date, stock_id, foreign_buy, trust_buy, dealer_buy, margin_long, margin_short,
        tx_foreign_long, tx_foreign_short, mtx_retail_long, mtx_retail_short, trust_tx_long, trust_tx_short,
        mtx_trust_long, mtx_trust_short, mtx_dealer_long, mtx_dealer_short, market_volume)
    SELECT date, '0000', foreign_buy, trust_buy, dealer_buy, margin_long, margin_short,
        tx_foreign_long, tx_foreign_short, mtx_retail_long, mtx_retail_short, trust_tx_long, trust_tx_short,
        mtx_trust_long, mtx_trust_short, mtx_dealer_long, mtx_dealer_short, market_volume
    FROM market_daily
    ON CONFLICT (date, stock_id) DO UPDATE SET
        foreign_buy = EXCLUDED.foreign_buy, trust_buy = EXCLUDED.trust_buy, dealer_buy = EXCLUDED.dealer_buy,
        margin_long = EXCLUDED.margin_long, margin_short = EXCLUDED.margin_short,
        tx_foreign_long = EXCLUDED.tx_foreign_long, tx_foreign_short = EXCLUDED.tx_foreign_short,
        mtx_retail_long = EXCLUDED.mtx_retail_long, mtx_retail_short = EXCLUDED.mtx_retail_short,
        trust_tx_long = EXCLUDED.trust_tx_long, trust_tx_short = EXCLUDED.trust_tx_short,
        mtx_trust_long = EXCLUDED.mtx_trust_long, mtx_trust_short = EXCLUDED.mtx_trust_short,
        mtx_dealer_long = EXCLUDED.mtx_dealer_long, mtx_dealer_short = EXCLUDED.mtx_dealer_short,
        market_volume = EXCLUDED.market_volume;

    DROP TABLE daily_chips;
    DROP TABLE market_daily;
    ALTER TABLE daily_chips_pre001 RENAME TO daily_chips;
    ALTER TABLE daily_chips RENAME CONSTRAINT daily_chips_pre001_pkey TO daily_chips_pkey;
    ALTER INDEX IF EXISTS idx_chips_stock_date_pre001 RENAME TO idx_chips_stock_date;
END $$;

COMMIT;
