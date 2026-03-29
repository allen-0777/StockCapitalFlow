LiquidChip 籌碼流動：API 端點總表 (API Endpoints List)

本文件列出 LiquidChip 系統中所有使用到的 API，分為三大類：
外部資料源 (Data Sources)、推播服務 (Notifications，Phase 2) 與 自建後端 (Internal RESTful APIs)。

---

1. 外部資料源 API (External Data Sources)

由 backend/app/services/fetcher.py 負責呼叫，透過 APScheduler 每日盤後自動執行。

注意：原 API_POINT.md 記載的 openapi.twse.com.tw/v1/fund/BFI82U 與 T86 端點已失效（302 → 404）。
      目前改用 TWSE 主站 API（www.twse.com.tw/rwd/zh），完全免費，無需 API Key。

1.1 TWSE 主站 API (www.twse.com.tw)

大盤三大法人買賣超：
GET https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json

用途：取得外資、投信、自營商的每日總買賣差額（對應 Widget1）。
執行時間：每日 16:30 排程。

Response (JSON):
{
  "stat": "OK",
  "date": "20260317",
  "title": "115年03月17日 三大法人買賣金額統計表",
  "fields": ["單位名稱", "買進金額", "賣出金額", "買賣差額"],
  "data": [
    ["自營商(自行買賣)", "9,658,406,308", "5,971,297,625", "3,687,108,683"],
    ["自營商(避險)", "27,140,440,066", "21,732,274,789", "5,408,165,277"],
    ["投信", "17,114,867,709", "16,909,073,997", "205,793,712"],
    ["外資及陸資(不含外資自營商)", "274,468,229,393", "273,995,847,292", "472,382,101"],
    ["外資自營商", "0", "0", "0"]
  ]
}

解析說明：
- 外資：row[0] 含 "外資及陸資"（data[3]），買賣差額 = row[3]，除以 1e8 轉億
- 投信：row[0] 含 "投信"，同上
- 自營商：row[0] 含 "自營商"，累加自行買賣 + 避險


個股三大法人買賣超：
GET https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL

用途：取得所有上市個股當日的法人買賣超股數。
執行時間：每日 16:30 排程。

Response (JSON):
{
  "stat": "OK",
  "date": "20260317",
  "fields": ["證券代號", "證券名稱",
             "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)", "外陸資買賣超股數(不含外資自營商)",
             "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數",
             "投信買進股數", "投信賣出股數", "投信買賣超股數",
             "自營商買賣超股數", "自營商買進股數", "自營商賣出股數",
             "三大法人買賣超股數"],
  "data": [
    ["2330", "台積電", "12345678", "9876543", "2469135", ...]
  ]
}

解析說明：
- stock_id = row[0]，外資買賣超 = row[4]，投信 = row[10]，自營商 = row[11]
- 單位為「股」，存入 DB 時除以 1000 轉為「千股」


大盤信用交易統計（融資融券）：
GET https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&selectType=MS

用途：取得今日融資餘額與融券餘額（對應 Widget3 液態球底部數據）。
執行時間：每日 17:30 排程。

Response (JSON):
{
  "stat": "OK",
  "tables": [{
    "title": "115年03月17日 信用交易統計",
    "fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"],
    "data": [
      ["融資(交易單位)", "480,207", "487,105", "4,348", "8,085,690", "8,074,444"],
      ["融券(交易單位)", "18,219", "19,105", "9,759", "223,950", "215,077"],
      ["融資金額(仟元)", "32,519,811", "31,000,701", "336,155", "392,284,076", "393,467,031"]
    ]
  }]
}

解析說明：
- 融資餘額（交易單位）= row[4]（前日餘額），row[0] 含 "融資" 且不含 "金額"
- 融券餘額（交易單位）= row[4]，row[0] 含 "融券"


廢棄端點（勿使用）：
- https://openapi.twse.com.tw/v1/fund/BFI82U → 302 重定向至 404
- https://openapi.twse.com.tw/v1/fund/T86 → 302 重定向至 404
- https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN → 改用 marginTrading 路徑

---

2. 推播服務 API（Phase 2，尚未實作）

2.1 Telegram Bot API

發送訊息：
POST https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage

Payload (JSON):
{
  "chat_id": "使用者的_CHAT_ID",
  "text": "📊 LiquidChip 盤後籌碼速報\n外資今日買超 4.72 億",
  "parse_mode": "Markdown"
}


2.2 Discord Webhook API

POST https://discord.com/api/webhooks/<WEBHOOK_ID>/<WEBHOOK_TOKEN>

支援 Rich Embeds，可發送帶有顏色（紅漲綠跌）的排版卡片。

---

3. 自建內部後端 API（Internal FastAPI Endpoints）

Base URL: http://localhost:8000（開發）
前端透過 Vite proxy 轉發，設定於 vite.config.js：server.proxy['/api'] = 'http://localhost:8000'

---

3.1 系統狀態 (Health)

GET /api/v1/health

用途：React Sidebar 左下角「系統狀態」綠燈，確認 DB 最後更新時間。

Response 200:
{
  "status": "healthy",
  "last_update": "2026-03-17",
  "last_institutional": "2026-03-17",
  "last_margin": "2026-03-16"
}

- `last_update`：`stock_id='0000'` 列上最新 `date`。
- `last_institutional`：同上列且 `foreign_buy` 非空之最新 `date`。
- `last_margin`：同上列且 `margin_long` 非空之最新 `date`。  
  若 DB 無資料則各欄位可為 `null`。

---

3.2 大盤數據 (Market)

GET /api/v1/market/summary

用途：Widget1（三大法人）與 Widget3（液態球）共用，取今日大盤籌碼。

Response 200:
{
  "date": "2026-03-17",
  "institutional": {
    "foreign": 4.72,
    "trust": 2.06,
    "dealer": 90.95,
    "total": 97.73
  },
  "margin": {
    "long_balance_change": 8085690,
    "short_balance_change": 223950
  }
}

Response 404：DB 中尚無大盤資料（需先執行爬蟲）。
單位說明：institutional 欄位為「億元」；margin 欄位為「交易單位（千股）」。

---

3.3 個股籌碼 (Stocks)

GET /api/v1/stocks/{stock_id}/chips?days=5

用途：點擊觀察清單個股後，取得近 N 日法人買賣趨勢（供未來 K 線圖使用）。

Query Params:
  days: int，預設 5，範圍 1–60

Response 200（陣列，由新到舊）:
[
  {
    "date": "2026-03-17",
    "foreign_buy": 2.47,
    "trust_buy": 0.05,
    "dealer_buy": -0.12,
    "margin_long": 0,
    "margin_short": 0
  }
]

---

3.4 觀察清單 (Watchlist)

取得觀察清單（含今日籌碼摘要）
GET /api/v1/users/{user_id}/watchlist

用途：Widget2「關注清單籌碼動能」列表資料來源。
目前 MVP 固定使用 user_id=1（預設使用者，啟動時自動建立）。

Response 200:
[
  {
    "stock_id": "2330",
    "foreign_buy": 2.47,
    "trust_buy": 0.05,
    "dealer_buy": -0.12,
    "date": "2026-03-17"
  }
]

若該股票尚無籌碼資料（DB 中無記錄），各買賣超欄位回傳 0，date 回傳 null。


新增股票至觀察清單
POST /api/v1/users/{user_id}/watchlist

Payload: { "stock_id": "2330" }

Response 201: { "message": "新增成功", "stock_id": "2330" }
Response 409: { "detail": "已在觀察清單中" }


刪除觀察股票
DELETE /api/v1/users/{user_id}/watchlist/{stock_id}

Response 200: { "message": "已移除", "stock_id": "2330" }

---

3.5 Admin 排程觸發（需 TRIGGER_SECRET）

POST `/api/v1/admin/trigger/all?secret=...`  
一次排程內所有 job（`institutional`、`futures`、`margin`、`industry`）；非交易日會 skipped。

POST `/api/v1/admin/trigger/{job}?secret=...`  
`job`：`institutional` | `futures` | `margin` | `industry`。`industry` 允許非交易日觸發。

**Query 選填**

- `notify=true`：完成或失敗時嘗試 Telegram 通知（若已設定 bot）。
- `force=true`：略過「當日已有資料」快取，強制重跑。
- **`target_date=YYYY-MM-DD`**：將「預期交易日」設為該日，供 `_job_already_done` 與 `date_match` 比對。  
  **限制**：證交所／期交所多數公開 API **無法指定歷史日期**，只回傳「目前已發布之最新交易日」資料；此參數無法讓後端向 TWSE 索取任意過去日期，主要用於「日曆已進下一日，但官方仍僅釋出昨日盤後資料」時，把 expected 對齊昨日，使 skip/force 判斷正確。格式錯誤回 HTTP 400。

GET `/api/v1/admin/job-status/{job}?secret=...`：輪詢背景 job 狀態。

---

3.6 推播設定（Phase 2，尚未實作）

PUT /api/v1/users/{user_id}/notifications

用途：讓使用者綁定 Telegram Chat ID 或 Discord Webhook URL。
Payload: { "notify_token": "telegram_chat_id_or_discord_webhook" }
