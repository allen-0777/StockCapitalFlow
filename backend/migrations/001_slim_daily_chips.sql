-- 001_slim_daily_chips.sql
-- 目的：縮小 daily_chips（T86 每日約 1.96 萬列）的儲存空間，延長 Supabase 免費版 500MB 的壽命。
--   1. 大盤彙總列（stock_id='0000'）搬到 market_daily（欄位、型別、數值完全不變）
--   2. daily_chips 只留個股三欄，numeric「張」(小數 3 位) → integer「股」(×1000，無損)
--   3. PK 改為 (stock_id, date)，刪除重複的 idx_chips_stock_date，日期查詢改用 BRIN(date)
--   4. 欄位順序：定長整數在前、varchar 在後，避免 alignment padding
--
-- 冪等：可重複執行。已遷移（daily_chips 無 margin_long 欄位）時只會補齊索引後結束。
-- 原表保留為 daily_chips_pre001 供回滾，確認無誤後再執行 001_cleanup.sql 刪除。
-- 執行：psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_slim_daily_chips.sql
-- 回滾：psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_slim_daily_chips_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS market_daily (
    date             date PRIMARY KEY,
    foreign_buy      numeric,
    trust_buy        numeric,
    dealer_buy       numeric,
    margin_long      integer,
    margin_short     integer,
    tx_foreign_long  integer,
    tx_foreign_short integer,
    mtx_retail_long  integer,
    mtx_retail_short integer,
    trust_tx_long    integer,
    trust_tx_short   integer,
    mtx_trust_long   integer,
    mtx_trust_short  integer,
    mtx_dealer_long  integer,
    mtx_dealer_short integer,
    market_volume    numeric
);

DO $$
DECLARE
    n_old_stock   bigint;
    n_new         bigint;
    n_old_market  bigint;
    n_market      bigint;
    bad           bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'daily_chips' AND column_name = 'margin_long'
    ) THEN
        RAISE NOTICE '001: daily_chips already slim, skipping data migration';
        RETURN;
    END IF;

    -- 擋住遷移期間的寫入（排程 / 後端）
    LOCK TABLE daily_chips IN ACCESS EXCLUSIVE MODE;

    -- 前置檢查：個股列必須能無損轉成 integer 股數
    SELECT count(*) INTO bad FROM daily_chips
    WHERE stock_id <> '0000' AND (
          foreign_buy IS NULL OR trust_buy IS NULL OR dealer_buy IS NULL
       OR foreign_buy * 1000 <> round(foreign_buy * 1000)
       OR trust_buy   * 1000 <> round(trust_buy   * 1000)
       OR dealer_buy  * 1000 <> round(dealer_buy  * 1000)
       OR greatest(abs(foreign_buy), abs(trust_buy), abs(dealer_buy)) * 1000 > 2147483647
       OR coalesce(margin_long, margin_short, tx_foreign_long, tx_foreign_short, mtx_retail_long,
                   mtx_retail_short, trust_tx_long, trust_tx_short, mtx_trust_long, mtx_trust_short,
                   mtx_dealer_long, mtx_dealer_short) IS NOT NULL
       OR market_volume IS NOT NULL);
    IF bad > 0 THEN
        RAISE EXCEPTION '001: % stock rows cannot be converted losslessly; aborting', bad;
    END IF;

    -- 1. 大盤列 → market_daily
    INSERT INTO market_daily
    SELECT date, foreign_buy, trust_buy, dealer_buy, margin_long, margin_short,
           tx_foreign_long, tx_foreign_short, mtx_retail_long, mtx_retail_short,
           trust_tx_long, trust_tx_short, mtx_trust_long, mtx_trust_short,
           mtx_dealer_long, mtx_dealer_short, market_volume
    FROM daily_chips WHERE stock_id = '0000'
    ON CONFLICT (date) DO NOTHING;

    -- 2. 個股列 → 新表（依日期順序寫入，BRIN 才有效）
    CREATE TABLE daily_chips_slim (
        date        date    NOT NULL,
        foreign_buy integer NOT NULL,
        trust_buy   integer NOT NULL,
        dealer_buy  integer NOT NULL,
        stock_id    varchar NOT NULL
    );
    INSERT INTO daily_chips_slim (date, foreign_buy, trust_buy, dealer_buy, stock_id)
    SELECT date,
           (foreign_buy * 1000)::integer,
           (trust_buy   * 1000)::integer,
           (dealer_buy  * 1000)::integer,
           stock_id
    FROM daily_chips WHERE stock_id <> '0000'
    ORDER BY date, stock_id;

    -- 驗證筆數與總和
    SELECT count(*) INTO n_old_stock  FROM daily_chips WHERE stock_id <> '0000';
    SELECT count(*) INTO n_new        FROM daily_chips_slim;
    SELECT count(*) INTO n_old_market FROM daily_chips WHERE stock_id = '0000';
    SELECT count(*) INTO n_market     FROM market_daily
        WHERE date IN (SELECT date FROM daily_chips WHERE stock_id = '0000');
    IF n_old_stock <> n_new OR n_old_market <> n_market THEN
        RAISE EXCEPTION '001: row count mismatch stock %/% market %/%', n_old_stock, n_new, n_old_market, n_market;
    END IF;
    IF (SELECT (sum(foreign_buy * 1000), sum(trust_buy * 1000), sum(dealer_buy * 1000))
          FROM daily_chips WHERE stock_id <> '0000')
       IS DISTINCT FROM
       (SELECT (sum(foreign_buy)::numeric, sum(trust_buy)::numeric, sum(dealer_buy)::numeric)
          FROM daily_chips_slim) THEN
        RAISE EXCEPTION '001: checksum mismatch';
    END IF;

    -- 3. 換表；舊表留作回滾
    ALTER TABLE daily_chips RENAME TO daily_chips_pre001;
    ALTER TABLE daily_chips_pre001 RENAME CONSTRAINT daily_chips_pkey TO daily_chips_pre001_pkey;
    ALTER INDEX IF EXISTS idx_chips_stock_date RENAME TO idx_chips_stock_date_pre001;
    ALTER TABLE daily_chips_slim RENAME TO daily_chips;
    ALTER TABLE daily_chips ADD CONSTRAINT daily_chips_pkey PRIMARY KEY (stock_id, date);

    RAISE NOTICE '001: migrated % stock rows, % market rows', n_new, n_market;
END $$;

CREATE INDEX IF NOT EXISTS idx_chips_date_brin ON daily_chips USING brin (date) WITH (pages_per_range = 32);
DROP INDEX IF EXISTS idx_chips_stock_date;   -- 已被 PK (stock_id, date) 取代

COMMIT;

ANALYZE daily_chips;
ANALYZE market_daily;
