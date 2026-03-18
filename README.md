# StockCapitalFlow 台股籌碼流動追蹤系統

即時追蹤台股三大法人動向、外資持股比例與券商分點進出，以毛玻璃液態介面呈現籌碼數據。

## 功能介紹

| 頁籤 | 功能 |
|------|------|
| 大盤總覽 | 當日外資／投信／自營商買賣超，融資融券餘額變化 |
| 法人進出 | 個股法人買賣超排行，多空強度儀表板 |
| 券商分點 | 特定股票的分點買賣超彙整（開發中） |
| 籌碼集中度 | 三大法人近10日明細表、連買連賣天數、外資持股比例走勢圖 |

## 技術架構

```
StockCapitalFlow/
├── frontend/          # React + Vite + TailwindCSS
│   └── src/
│       ├── components/    # 各功能 Widget 元件
│       └── store/         # Zustand 全域狀態
└── backend/           # FastAPI + SQLAlchemy + APScheduler
    └── app/
        ├── api/           # REST API 路由
        ├── models/        # SQLite 資料庫模型
        └── services/      # 爬蟲排程、FinMind 整合
```

**前端：** React 18、Vite、TailwindCSS、Zustand、Lucide Icons

**後端：** FastAPI、SQLAlchemy、APScheduler、aiohttp

**資料庫：** SQLite

**資料來源：**
- [TWSE OpenAPI](https://openapi.twse.com.tw/)（三大法人、融資券，免費）
- [FinMind API](https://finmindtrade.com/)（法人買賣超明細、外資持股比例，免費 Token）

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
# 編輯 .env，填入 FINMIND_TOKEN

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

```
FINMIND_TOKEN=你的FinMind免費Token
```

FinMind 免費 Token 申請：至 [finmindtrade.com](https://finmindtrade.com/) 註冊後即可取得。

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/health` | 系統狀態與最後更新時間 |
| GET | `/api/v1/market/summary` | 大盤三大法人 + 融資券摘要 |
| GET | `/api/v1/stocks/search?q=` | 股號或股名模糊搜尋 |
| GET | `/api/v1/stocks/{id}/concentration` | 個股法人買賣超 + 外資持股比例 |
| GET | `/api/v1/institutional/ranking` | 法人買賣超排行 |
| GET | `/api/v1/users/1/watchlist` | 觀察清單 |
| POST | `/api/v1/users/1/watchlist` | 新增觀察股 |
| DELETE | `/api/v1/users/1/watchlist/{id}` | 移除觀察股 |

## 資料更新排程

| 時間 | 任務 |
|------|------|
| 每日 16:30 | 抓取三大法人買賣超（大盤 + 個股） |
| 每日 17:30 | 抓取融資融券餘額 |

## 注意事項

- 本系統僅供個人學習研究使用，不構成任何投資建議
- 資料來源為公開 API，時間上可能有延遲
- `.env` 檔案含有 API Token，請勿提交至版本控制
