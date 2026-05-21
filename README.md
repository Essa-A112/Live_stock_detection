# Live Stock Detection — Stock Analysis Pipeline

A full end-to-end stock analysis pipeline with live data ingestion, technical analysis, SQLite persistence, a FastAPI backend, and a dark-themed interactive frontend.

---

## Features

- **Live OHLCV data** via `yfinance` (6-month history, adjustable)
- **Company fundamentals** — market cap, P/E, EPS, beta, dividend yield, 52-week range
- **Technical indicators** — RSI (14), MACD (12/26/9), Bollinger Bands (20/2σ), SMA 20/50, EMA 20, volatility
- **Signal engine** — weighted scoring across RSI + MACD + Bollinger Bands → BUY / SELL / HOLD with confidence score and reasoning
- **SQLite cache** — results stored via SQLAlchemy; re-requests within 60 minutes served from cache
- **FastAPI backend** — single endpoint `/stock/{ticker}` returning complete JSON
- **Dark-themed frontend** — interactive Plotly charts (candlestick, volume, RSI, MACD), company info panel, signal verdict panel

---

## Project Structure

```
Live_stock_detection/
├── api/
│   └── main.py            # FastAPI app, CORS middleware, /stock/{ticker} endpoint
├── data/
│   └── ingestion.py       # yfinance OHLCV + fundamentals fetcher
├── analysis/
│   └── technical.py       # RSI, MACD, Bollinger Bands, MAs, signal scoring
├── database/
│   ├── models.py          # SQLAlchemy ORM models (StockPrice, CompanyInfo, TechnicalIndicator)
│   └── db.py              # Engine, session, CRUD helpers, cache check
├── frontend/
│   └── index.html         # Single-file dark UI with embedded Plotly charts
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.11+
- Internet access (for yfinance)

---

## Installation

```bash
git clone https://github.com/essa-a112/live_stock_detection.git
cd live_stock_detection
pip install -r requirements.txt
```

---

## Running the Backend

```bash
uvicorn api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

The SQLite database (`stock_data.db`) is created automatically on first run.

---

## Using the Frontend

Open `frontend/index.html` directly in your browser:

```bash
# macOS
open frontend/index.html

# Linux
xdg-open frontend/index.html

# Windows
start frontend/index.html
```

Or serve it with any static file server:

```bash
cd frontend && python -m http.server 3000
```

Then visit `http://localhost:3000`.

Type any US ticker (e.g. `AAPL`, `TSLA`, `SPY`) and click **Analyze**.

---

## API Reference

### `GET /health`

Returns server status.

```json
{ "status": "ok", "timestamp": "2026-05-21T14:30:00Z" }
```

### `GET /stock/{ticker}`

Runs the full pipeline for the given ticker symbol. Results are cached in SQLite for 60 minutes.

**Example:** `GET /stock/AAPL`

**Response schema:**

```json
{
  "ticker": "AAPL",
  "last_updated": "2026-05-21T14:30:00Z",
  "company": {
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "market_cap": 2850000000000,
    "pe_ratio": 32.5,
    "eps": 5.82,
    "beta": 1.24,
    "dividend_yield": 0.0046,
    "description": "...",
    "website": "https://www.apple.com",
    "employees": 164000,
    "current_price": 189.45,
    "week_52_high": 215.30,
    "week_52_low": 163.80
  },
  "prices": {
    "dates":  ["2025-11-21", "..."],
    "open":   [182.5, "..."],
    "high":   [184.75, "..."],
    "low":    [182.1, "..."],
    "close":  [184.2, "..."],
    "volume": [52300000, "..."]
  },
  "indicators": {
    "rsi":         [45.2, "..."],
    "macd":        [0.32, "..."],
    "macd_signal": [0.28, "..."],
    "macd_hist":   [0.04, "..."],
    "bb_upper":    [188.2, "..."],
    "bb_middle":   [182.5, "..."],
    "bb_lower":    [176.8, "..."],
    "sma20":       [181.2, "..."],
    "sma50":       [178.9, "..."],
    "ema20":       [181.5, "..."],
    "volatility":  [0.18, "..."]
  },
  "signal": {
    "verdict": "BUY",
    "confidence": 0.72,
    "strength_score": 0.58,
    "reasons": [
      "RSI oversold at 28.4",
      "MACD histogram positive (0.18), bullish momentum",
      "Price near lower Bollinger Band"
    ],
    "component_scores": {
      "rsi_score": 0.7,
      "macd_score": 0.6,
      "bollinger_score": 0.55
    }
  }
}
```

**Error response (404):**
```json
{ "detail": "No data found for ticker 'ZZZZZ'. Check the symbol and try again." }
```

---

## Signal Logic

Signals are generated from a weighted combination of three indicators:

| Indicator      | Weight | Buy Condition              | Sell Condition             |
|----------------|--------|----------------------------|----------------------------|
| RSI (14)       | 35%    | RSI < 30 (oversold)        | RSI > 70 (overbought)       |
| MACD histogram | 40%    | Histogram positive, rising | Histogram negative, falling |
| Bollinger Bands| 25%    | Price below lower band     | Price above upper band      |

A combined score in range [-1, 1] is computed. Scores > 0.30 → **BUY**, < -0.30 → **SELL**, else **HOLD**.

---

## Deploying the Frontend to GitHub Pages

1. The frontend is a single static HTML file — no build step needed.
2. Push `frontend/index.html` to your repo.
3. In GitHub → Settings → Pages, set source to the `frontend/` folder (or root).
4. Update the `API_BASE` constant in `frontend/index.html` to point to your deployed backend URL:
   ```js
   const API_BASE = 'https://your-backend.example.com';
   ```
5. The backend has `allow_origins=["*"]` so it accepts calls from any GitHub Pages domain.

---

## Tech Stack

| Layer           | Technology                              |
|-----------------|-----------------------------------------|
| Data ingestion  | yfinance                                |
| Analysis        | pandas, numpy                           |
| Database        | SQLite + SQLAlchemy 2.0                 |
| Backend API     | FastAPI + uvicorn                       |
| Frontend charts | Plotly.js (CDN)                         |
| Frontend style  | Vanilla CSS (dark terminal theme)       |
