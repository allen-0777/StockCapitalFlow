# StockCapitalFlow 台股籌碼流動追蹤系統

即時追蹤台股三大法人動向、期貨未平倉多空比、選擇權籌碼，以毛玻璃液態介面呈現籌碼數據。

## 功能介紹

| 頁籤 | 功能 |
|------|------|
| 大盤總覽 | 外資／投信／自營商當日買賣超、融資融券餘額、台指期外資未平倉多空比、小台散戶多空比、選擇權 P/C 比與最大未平倉履約價 |
| 法人進出 | 個股法人買賣超排行，多空強度儀表板 |
| 券商分點 | 特定股票的分點買賣超彙整 |
| 籌碼集中度 | 三大法人近10日明細表、連買連賣天數、外資持股比例走勢圖 |

## 技術架構

```
StockCapitalFlow/
├── frontend/                  # React + Vite + TailwindCSS
│   └── src/
│       ├── components/        # Widget 元件（法人、期貨、選擇權、融資券…）
│       └── store/             # Zustand 全域狀態
└── backend/                   # FastAPI + SQLAlchemy
    └── app/
        ├── api/               # REST API 路由
        ├── models/            # SQLite 資料庫模型
        └── services/          # 資料抓取（fetcher）、排程、Telegram 推播
```

**前端：** React 18、Vite、TailwindCSS、Zustand、Lucide Icons

**後端：** FastAPI、SQLAlchemy、aiohttp、exchange-calendars

**資料庫：** SQLite（本地）/ PostgreSQL（雲端 Render）

**資料來源：**

| 來源 | 資料 | 延遲 |
|------|------|------|
| [TWSE OpenAPI](https://openapi.twse.com.tw/) | 三大法人買賣超（大盤＋個股）、融資融券 | 當日盤後 |
| [TAIFEX OpenAPI v1](https://openapi.taifex.com.tw/v1/) | 期貨三大法人未平倉、選擇權三大法人未平倉 | 當日盤後 |
| [FinMind API](https://finmindtrade.com/) | 選擇權 P/C 比、最大未平倉履約價、法人買賣超明細、外資持股比例 | 當日～次日 |

## 安裝與啟動

### 環境需求

- Python 3.10+
- Node.js 18+

### 後端

```bash
cd backend
pip install -r requirements.txt

# 設定環境變數
cp .env.example .env
# 編輯 .env，依需求填入各項設定

uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

開啟瀏覽器前往 `http://localhost:5173`

## 環境變數

在 `backend/.env` 中設定：

```env
# FinMind（選擇權 P/C 比、個股外資持股）
FINMIND_TOKEN=your_finmind_token_here

# Telegram 推播（選填）
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 管理端點驗證（GitHub Actions 觸發用）
TRIGGER_SECRET=your_trigger_secret
```

FinMind 免費 Token：至 [finmindtrade.com](https://finmindtrade.com/) 註冊後即可取得。

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/health` | 系統狀態與各資料最後更新時間 |
| GET | `/api/v1/market/summary` | 大盤三大法人 + 融資券 + 期貨未平倉摘要 |
| GET | `/api/v1/market/options` | 選擇權 P/C 比、最大未平倉履約價 |
| GET | `/api/v1/stocks/search?q=` | 股號或股名模糊搜尋 |
| GET | `/api/v1/stocks/{id}/concentration` | 個股法人買賣超 + 外資持股比例 |
| GET | `/api/v1/institutional/ranking` | 法人買賣超排行 |
| GET | `/api/v1/users/1/watchlist` | 觀察清單 |
| POST | `/api/v1/users/1/watchlist` | 新增觀察股 |
| DELETE | `/api/v1/users/1/watchlist/{id}` | 移除觀察股 |
| POST | `/api/v1/admin/trigger/{job}?secret=&notify=` | 手動觸發爬蟲（`job`: `institutional` / `futures` / `margin`；`notify=true` 失敗時發 Telegram） |
| POST | `/api/v1/admin/daily-digest?secret=` | 每日彙整推播至 Telegram |

## 資料更新排程（GitHub Actions）

每個交易日由 GitHub Actions 觸發，排程採並行架構：

```
17:30 CST（週一～五）
  └── wake job：喚醒 Render 後端（最多 20 次 health check）
       ├── institutional：抓取三大法人買賣超（大盤 + 個股）
       ├── futures：      抓取台指期 / 小台散戶未平倉（TAIFEX OpenAPI）
       └── margin：       抓取融資融券餘額

22:00 CST（每日含假日）
  └── daily-digest：Telegram 每日彙整推播
```

三個資料 job 在 wake 完成後**並行**執行，縮短整體等待時間。
各 job 失敗最多重試 3 次（間隔 3 分鐘），最後一次失敗時發 Telegram 通知。

## 雲端部署（Render）

後端部署於 [Render](https://render.com/) 免費方案，閒置 15 分鐘後自動休眠，排程由 GitHub Actions 負責定時喚醒與觸發。

所需 GitHub Secrets：

| Secret | 說明 |
|--------|------|
| `RENDER_BACKEND_URL` | Render 後端完整 URL |
| `TRIGGER_SECRET` | 與後端 `TRIGGER_SECRET` 相同 |

## 資料日期說明

大盤總覽各區塊的資料日期可能不完全一致，原因是各來源釋出時間不同：

- **三大法人 / 融資券**：來自 TWSE，盤後約 17:30 釋出
- **期貨 / 選擇權未平倉**：來自 TAIFEX，盤後約 17:00 釋出
- **P/C 比 / 最大未平倉履約價**：來自 FinMind，當日或次日更新

頁面上方的「本頁資料日」區塊會顯示各指標實際對應的交易日。

## 注意事項

- 本系統僅供個人學習研究使用，不構成任何投資建議
- `.env` 檔案含有 API Token，已加入 `.gitignore`，請勿手動提交至版本控制
- TAIFEX / TWSE API 為公開免費，FinMind 免費方案有每月用量上限
