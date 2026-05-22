# Live Stock Detection — Stock Analysis Pipeline

A full end-to-end stock analysis pipeline with live market data, technical analysis, SQLite persistence, a FastAPI backend deployed on Render, and a dark-themed interactive frontend hosted on GitHub Pages.

**Live demo:** [essa-a112.github.io/Live_stock_detection](https://essa-a112.github.io/Live_stock_detection)
**API:** [live-stock-detection.onrender.com](https://live-stock-detection.onrender.com)

---

## Features

- **Live OHLCV data** — 6-month daily price history via Alpaca Markets API (`adjustment=all`); data refreshes every 5 minutes
- **Company fundamentals** — full name, sector, industry, market cap, P/E, EPS, beta, dividend yield, 52-week high/low, current price, and business description via Yahoo Finance
- **Performance summary** — 1-day, 5-day, and 30-day price change percentages, colour-coded green/red
- **52-week range bar** — visual progress bar showing where the current price sits between the 52-week low and high
- **News feed** — latest 5 headlines for the ticker with source, date, and clickable link; always fetched fresh
- **Technical indicators** — RSI (14), MACD (12/26/9), Bollinger Bands (20/2σ), SMA 20/50, EMA 20, annualised volatility
- **Signal engine** — weighted scoring across RSI + MACD + Bollinger Bands → BUY / SELL / HOLD with confidence score, strength score, per-indicator component scores, and plain-English reasoning
- **SQLite cache** — results cached via SQLAlchemy; repeated requests within 5 minutes served from cache to reduce latency
- **FastAPI backend** — `/health` and `/stock/{ticker}` endpoints with full CORS support
- **Dark-themed frontend** — interactive Plotly.js charts (candlestick + BB + MAs, volume, RSI, MACD), company info panel, signal verdict panel, quick-ticker buttons

---

## Project Structure

```
Live_stock_detection/
├── api/
│   └── main.py            # FastAPI app, CORS middleware, /stock/{ticker} endpoint
├── data/
│   └── ingestion.py       # Alpaca OHLCV + yfinance fundamentals + news fetcher
├── analysis/
│   └── technical.py       # RSI, MACD, Bollinger Bands, MAs, signal scoring
├── database/
│   ├── models.py          # SQLAlchemy ORM models (StockPrice, CompanyInfo, TechnicalIndicator)
│   └── db.py              # Engine, session, CRUD helpers, 5-minute cache check
├── index.html             # Single-file dark UI (served by GitHub Pages)
├── frontend/
│   └── index.html         # Same file for local development
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.11+
- Alpaca Markets account (free) — for OHLCV data
- Internet access — for Yahoo Finance fundamentals and news

---

## Environment Variables

| Variable            | Required | Description                          |
|---------------------|----------|--------------------------------------|
| `ALPACA_API_KEY`    | Yes      | Alpaca Markets API key ID            |
| `ALPACA_SECRET_KEY` | Yes      | Alpaca Markets API secret key        |

Get free API keys at [alpaca.markets](https://alpaca.markets). Paper trading account keys work fine.

Set these in your shell for local development:

```bash
export ALPACA_API_KEY=your_key_here
export ALPACA_SECRET_KEY=your_secret_here
```

On Render, add them under **Environment → Environment Variables** in your service settings.

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

Then visit `http://localhost:3000` and type any US ticker (e.g. `AAPL`, `TSLA`, `SPY`) and click **Analyze**.

---

## API Reference

### `GET /health`

Returns server status.

```json
{ "status": "ok", "timestamp": "2026-05-22T14:30:00Z" }
```

### `GET /stock/{ticker}`

Runs the full pipeline for the given ticker symbol. Results are cached in SQLite for 5 minutes.

**Example:** `GET /stock/AAPL`

**Response schema:**

```json
{
  "ticker": "AAPL",
  "last_updated": "2026-05-22T14:30:00Z",
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
  "performance": {
    "change_1d": -0.42,
    "change_5d": 1.87,
    "change_30d": 5.14
  },
  "news": [
    {
      "title": "Apple hits record high ahead of WWDC",
      "source": "Reuters",
      "published_at": "May 22, 2026",
      "url": "https://..."
    }
  ],
  "prices": {
    "dates":  ["2025-11-22", "..."],
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

| Indicator      | Weight | Buy Condition              | Sell Condition              |
|----------------|--------|----------------------------|-----------------------------||
| RSI (14)       | 35%    | RSI < 30 (oversold)        | RSI > 70 (overbought)       |
| MACD histogram | 40%    | Histogram positive, rising | Histogram negative, falling |
| Bollinger Bands| 25%    | Price below lower band     | Price above upper band      |

A combined score in range [-1, 1] is computed. Scores > 0.30 → **BUY**, < -0.30 → **SELL**, else **HOLD**.

---

## Data Sources

| Data                 | Source                     | Notes                                           |
|----------------------|----------------------------|-------------------------------------------------|
| OHLCV history        | Alpaca Markets API         | Free tier, `adjustment=all`, 180-day daily bars |
| Company fundamentals | Yahoo Finance (yfinance)   | Three-tier fallback for cloud IP compatibility  |
| News headlines       | Yahoo Finance (yfinance)   | Always fetched fresh, no cache                  |

### Fundamentals Fallback Strategy

Yahoo Finance’s `quoteSummary` endpoint is often blocked on cloud IPs (e.g. Render). Three tiers are tried in order:

1. **`fast_info`** — chart endpoint, always available; provides price, market cap, 52-week range
2. **`.info`** — `quoteSummary`; provides name, sector, P/E, EPS, beta, dividend yield when accessible
3. **`v7/finance/quote`** — alternate REST endpoint; fallback when `.info` returns empty

---

## Deployment

### Backend — Render

1. Connect the GitHub repo to a new Render web service
2. Set **Build Command:** `pip install -r requirements.txt`
3. Set **Start Command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables: `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
5. Render auto-deploys on every push to `main`

### Frontend — GitHub Pages

1. Go to **Settings → Pages** in the repo
2. Set source to the root of the `main` branch
3. `index.html` at the repo root is served automatically
4. `API_BASE` in `index.html` already points to the Render URL — no changes needed

---

## Tech Stack

| Layer               | Technology                        |
|---------------------|-----------------------------------|
| OHLCV data          | Alpaca Markets API                |
| Fundamentals / news | Yahoo Finance (via yfinance)      |
| Analysis            | pandas, numpy                     |
| Database            | SQLite + SQLAlchemy 2.0           |
| Backend API         | FastAPI + uvicorn                 |
| Hosting             | Render (API), GitHub Pages (UI)   |
| Frontend charts     | Plotly.js (CDN)                   |
| Frontend style      | Vanilla CSS (dark terminal theme) |
