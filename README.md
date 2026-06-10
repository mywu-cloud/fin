# 台股月營收查詢系統

Taiwan Stock Monthly Revenue Query System

## 技術架構

- **Backend**: Python FastAPI + SQLite + APScheduler
- **Frontend**: React + Vite + Zustand + CSS Modules + Recharts
- **資料來源**:
  - TWSE OpenAPI — 上市股票清單 + 收盤價
  - TPEx OpenAPI — 上櫃股票清單 + 收盤價
  - FinMind API — 月營收歷史資料

## 快速啟動

### 1. 設定環境變數

```bash
cd backend
cp .env.example .env
# 編輯 .env，填入 FINMIND_TOKEN
```

### 2. 啟動 Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend 會在 http://localhost:8000 啟動，並自動同步資料。

### 3. 啟動 Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend 會在 http://localhost:5173 啟動。

## API 端點

| 端點 | 說明 |
|------|------|
| GET /api/stocks | 股票清單（支援 q, market 搜尋） |
| GET /api/stocks/{stock_id} | 單支股票資訊 |
| GET /api/stocks/count | 股票總數 |
| GET /api/revenue/{stock_id} | 月營收資料 |
| POST /api/sync | 手動觸發同步 |
| GET /health | 健康檢查 |

## 資料同步

- 啟動時自動執行一次增量同步（priority stocks + 近 3 個月）
- 每天 18:30 自動增量同步
- 可透過 POST /api/sync?full=true 觸發完整歷史同步

## 色彩規範（台股慣例）

- 🔴 上漲：`#e05252`
- 🟢 下跌：`#3fb950`
