籌碼流動 (LiquidChip) 全端技術規格與系統架構書

1. 專案概述 (Project Overview)

LiquidChip 是一個自動化台股籌碼追蹤系統。結合「玻璃擬物化 (Glassmorphism)」與「液態 (Liquid)」的現代化前端介面，並透過後端排程每日自動抓取台股盤後籌碼數據（三大法人、資券餘額），經由演算法篩選後，提供視覺化儀表板。

2. 技術選型 (Tech Stack)

2.1 前端 (Frontend)

核心框架： React 18 + Vite 8

樣式語言： Tailwind CSS v4（透過 @tailwindcss/vite plugin 整合）

圖標庫： Lucide React

狀態管理： Zustand（管理 activeTab、watchlist 狀態）

動畫處理： CSS Keyframes（液態背景 blob + 水波球）

2.2 後端 (Backend)

核心框架： Python 3.11 + FastAPI（高效能非同步 API，自動生成 Swagger 文件）

數據處理： 直接使用 Python 內建解析（JSON 欄位對應），Pandas 保留供未來擴充

排程任務： APScheduler（BackgroundScheduler，內嵌 FastAPI lifespan，零額外服務）

第三方 API 介接：
  - TWSE 主站 API (https://www.twse.com.tw/rwd/zh)（免費，無需 API Key）

2.3 資料庫 (Database)

關聯式資料庫： SQLite（檔案式，零安裝依賴，存放於 backend/data.db）

ORM： SQLAlchemy（使用 text() 查詢，SessionLocal 管理連線）

快取層： 省略（MVP 階段直接查 SQLite，延遲可接受）

3. 系統架構圖 (System Architecture)

[外部資料源]                    [後端基礎設施 - Python/FastAPI]              [前端]
TWSE 主站 API  --(每日定時)--> Data Fetcher (aiohttp 抓取 + 解析)
(www.twse.com.tw)              APScheduler 排程
                                      |
                                      v
                               [SQLite data.db]  <---(REST API)---> [React Frontend (LiquidChip)]
                               daily_chips                            - 大盤總覽儀表板
                               users                                  - 關注清單籌碼動能
                               watchlists                             - 主力水位液態球

4. 資料庫綱要設計 (Database Schema)

Table: users（使用者）
欄位        型態         說明
id          INTEGER(PK)  唯一識別碼（預設建立 id=1, username='default'）
username    VARCHAR      使用者名稱
notify_token VARCHAR     Telegram Chat ID 或 Discord Webhook URL（Phase 2）

Table: watchlists（觀察清單）
欄位        型態         說明
id          INTEGER(PK)  唯一識別碼（autoincrement）
user_id     INTEGER(FK)  關聯至 users.id
stock_id    VARCHAR      股票代號（如 '2330'）

Table: daily_chips（每日籌碼歷史紀錄）
欄位           型態          說明
date           DATE(PK)      交易日期
stock_id       VARCHAR(PK)   股票代號（'0000' 代表大盤）
foreign_buy    NUMERIC       外資買賣超（億，大盤）/ 千股（個股）
trust_buy      NUMERIC       投信買賣超
dealer_buy     NUMERIC       自營商買賣超
margin_long    INTEGER       融資餘額（交易單位，大盤用）
margin_short   INTEGER       融券餘額（交易單位，大盤用）

5. 後端 API 設計 (RESTful API Endpoints)

見 API_POINT.md。

6. 自動化排程邏輯 (Cron Jobs & Automation)

使用 APScheduler BackgroundScheduler，時區 Asia/Taipei，內嵌於 FastAPI lifespan 啟動：

16:30（法人籌碼更新）：
  - fetch_institutional_market() → 抓大盤三大法人買賣超，存入 daily_chips（stock_id='0000'）
  - fetch_institutional_stocks() → 抓所有個股法人買賣超，批次 upsert

17:30（融資券更新）：
  - fetch_margin() → 抓大盤融資/融券餘額，更新 daily_chips（stock_id='0000'）

首次啟動時若需要資料，需手動呼叫 fetcher 函式（排程不會立即執行）：
  python3 -c "import asyncio; from app.services.fetcher import fetch_institutional_market, fetch_margin; asyncio.run(fetch_institutional_market()); asyncio.run(fetch_margin())"

7. 前端實作細節與樣式規範 (Frontend Guidelines)

7.1 色彩計畫 (Color Palette)

背景底色：     Slate 50 (#f8fafc)
上漲/買超：    Red 500 (#ef4444) 搭配 Red 100 背景
下跌/賣超：    Green 500 (#22c55e) 搭配 Green 100 背景
主視覺/液態色：Blue 400 (#60a5fa) 到 Cyan 300 (#67e8f9) 漸層

7.2 全域 CSS 核心代碼（位於 frontend/src/index.css）

/* 毛玻璃卡片 */
.glass-card {
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.05);
}

/* 液態不規則圓 */
.liquid-shape {
  border-radius: 40% 60% 70% 30% / 40% 50% 60% 50%;
}

/* 液態背景 blob 動畫 */
@keyframes blob {
  0%   { transform: translate(0px, 0px) scale(1); }
  33%  { transform: translate(30px, -50px) scale(1.1); }
  66%  { transform: translate(-20px, 20px) scale(0.9); }
  100% { transform: translate(0px, 0px) scale(1); }
}

7.3 元件架構

frontend/src/
├── App.jsx                       # 根元件，資料 fetch 與組合
├── components/
│   ├── Header.jsx                # 搜尋框、重整按鈕、頭像
│   ├── Sidebar.jsx               # 頁籤 + 系統狀態綠燈
│   ├── Widget1_Institutional.jsx # 三大法人買賣超卡片
│   ├── Widget2_Watchlist.jsx     # 關注清單（新增/刪除）
│   └── Widget3_LiquidGauge.jsx  # 大盤主力水位液態球
└── store/
    └── useStore.js               # Zustand（activeTab, watchlist）

8. 專案目錄結構 (Project Structure)

whoisbuying/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── store/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js            # 含 /api proxy → http://localhost:8000
│   └── tailwind.config.js
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers
│   │   ├── models/database.py    # SQLAlchemy + SQLite
│   │   ├── services/
│   │   │   ├── fetcher.py        # TWSE 爬蟲
│   │   │   └── scheduler.py      # APScheduler
│   │   └── main.py
│   ├── data.db                   # SQLite 資料庫（自動生成）
│   └── requirements.txt
├── TECH_DOC.md
├── API_POINT.md
└── react.html                    # UI 原型參考

9. 本機開發啟動 (Local Development)

Terminal 1 — 後端：
  cd backend
  pip3 install -r requirements.txt
  uvicorn app.main:app --reload --port 8000

Terminal 2 — 前端：
  cd frontend
  npm install
  npm run dev

前端：http://localhost:5173
後端 Swagger：http://localhost:8000/docs

10. 部署策略 (Deployment Strategy)

前端託管：Vercel 或 Netlify（對 Vite/React 支援極佳，全自動 CI/CD）

後端 API：Render 或 Railway（直接綁定 GitHub Repo，支援 Python 環境）

資料庫：SQLite 檔案隨後端部署。若未來需要擴充至多機部署，可遷移至 Supabase / Neon（PostgreSQL）

自動化排程：APScheduler 內嵌後端（不需 GitHub Actions），部署後自動生效

11. Phase 2 規劃（尚未實作）

- Telegram Bot API / Discord Webhook 推播通知
- FinMind API 整合（需 Token，用於集保戶籌碼集中度計算）
- 使用者登入（目前預設 user_id=1）
- 個股詳細頁（近 N 日法人買賣趨勢圖）
