-- 001 遷移確認無誤（建議跑過至少一次 17:30 排程、前端檢查正常）後執行，釋放舊表空間。
-- 執行後就無法用 001_slim_daily_chips_rollback.sql 回滾。
DROP TABLE IF EXISTS daily_chips_pre001;
