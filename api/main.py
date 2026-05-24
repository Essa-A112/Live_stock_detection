import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from database.db import (
    init_db, get_db, is_cache_fresh,
    get_cached_prices, get_cached_company, get_cached_indicators,
    upsert_prices, upsert_company, upsert_indicators,
)
from data.ingestion import (
    fetch_ohlcv, fetch_fundamentals, fetch_news, compute_performance,
)
from analysis.technical import run_full_analysis, generate_signals


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Stock Analysis API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


def _clean(val):
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _col(df, col):
    if col not in df.columns:
        return []
    return [_clean(v) for v in df[col].tolist()]


def _build_signal_from_cache(price_rows, ind_map) -> dict:
    def pick(date_str, field):
        row = ind_map.get(date_str)
        return _clean(getattr(row, field, None)) if row else None

    cached_df = pd.DataFrame({
        "date":        [r.date for r in price_rows],
        "close":       [r.close for r in price_rows],
        "rsi":         [pick(str(r.date), "rsi")         for r in price_rows],
        "macd":        [pick(str(r.date), "macd")        for r in price_rows],
        "macd_signal": [pick(str(r.date), "macd_signal") for r in price_rows],
        "macd_hist":   [pick(str(r.date), "macd_hist")   for r in price_rows],
        "bb_upper":    [pick(str(r.date), "bb_upper")    for r in price_rows],
        "bb_middle":   [pick(str(r.date), "bb_middle")   for r in price_rows],
        "bb_lower":    [pick(str(r.date), "bb_lower")    for r in price_rows],
    })
    return generate_signals(cached_df)


# Maps each frontend timeframe key → (look-back days, Alpaca interval string)
_TIMEFRAME_CONFIG = {
    "1D":  (5,    "15Min"),
    "1W":  (10,   "1Hour"),
    "1M":  (35,   "1Day"),
    "3M":  (95,   "1Day"),
    "6M":  (185,  "1Day"),
    "1Y":  (370,  "1Day"),
    "MAX": (3650, "1Day"),
}
# Sub-day intervals are never written to the DB (schema stores dates, not timestamps)
_INTRADAY = {"1D", "1W"}


@app.get("/stock/{ticker}")
def get_stock(ticker: str, timeframe: str = Query(default="6M")):
    ticker = ticker.upper().strip()
    period, interval = _TIMEFRAME_CONFIG.get(timeframe, (185, "1Day"))
    is_intraday = timeframe in _INTRADAY

    with get_db() as db:
        # Skip cache entirely for intraday timeframes
        fresh = False if is_intraday else is_cache_fresh(ticker, db)
        if fresh:
            price_rows = get_cached_prices(ticker, db)
            if not price_rows:
                fresh = False

        if not fresh:
            try:
                df = fetch_ohlcv(ticker, period, interval)
            except EnvironmentError as e:
                raise HTTPException(status_code=503, detail=str(e))
            if df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"No price data returned for '{ticker}' ({timeframe}). "
                           "Verify the ticker symbol is correct and traded on US markets.",
                )

            fundamentals = fetch_fundamentals(ticker)
            news         = fetch_news(ticker)
            df           = run_full_analysis(df)
            signal       = generate_signals(df)
            performance  = compute_performance(df["close"].tolist())

            # Only persist daily-bar data — intraday is too granular for the DB schema
            if not is_intraday:
                price_dicts = df[["date", "open", "high", "low", "close", "volume"]].to_dict("records")
                upsert_prices(ticker, price_dicts, db)
                upsert_company(ticker, fundamentals, db)

                ind_cols = ["date", "rsi", "macd", "macd_signal", "macd_hist",
                            "bb_upper", "bb_middle", "bb_lower", "sma20", "sma50", "ema20", "volatility"]
                ind_dicts = df[[c for c in ind_cols if c in df.columns]].to_dict("records")
                upsert_indicators(ticker, ind_dicts, db)

            dates = [str(d) for d in df["date"].tolist()]
            return {
                "ticker":       ticker,
                "timeframe":    timeframe,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "company":      fundamentals,
                "performance": performance,
                "news":        news,
                "prices": {
                    "dates":  dates,
                    "open":   _col(df, "open"),
                    "high":   _col(df, "high"),
                    "low":    _col(df, "low"),
                    "close":  _col(df, "close"),
                    "volume": _col(df, "volume"),
                },
                "indicators": {
                    "rsi":         _col(df, "rsi"),
                    "macd":        _col(df, "macd"),
                    "macd_signal": _col(df, "macd_signal"),
                    "macd_hist":   _col(df, "macd_hist"),
                    "bb_upper":    _col(df, "bb_upper"),
                    "bb_middle":   _col(df, "bb_middle"),
                    "bb_lower":    _col(df, "bb_lower"),
                    "sma20":       _col(df, "sma20"),
                    "sma50":       _col(df, "sma50"),
                    "ema20":       _col(df, "ema20"),
                    "volatility":  _col(df, "volatility"),
                },
                "signal": signal,
            }

        # ── Serve from cache ──────────────────────────────────────────────
        company_row = get_cached_company(ticker, db)
        ind_rows    = get_cached_indicators(ticker, db)

        dates   = [str(r.date) for r in price_rows]
        ind_map = {str(r.date): r for r in ind_rows}

        company = {}
        if company_row:
            company = {
                "name":           company_row.name,
                "sector":         company_row.sector,
                "industry":       company_row.industry,
                "market_cap":     company_row.market_cap,
                "pe_ratio":       company_row.pe_ratio,
                "eps":            company_row.eps,
                "beta":           company_row.beta,
                "dividend_yield": company_row.dividend_yield,
                "description":    company_row.description,
                "website":        company_row.website,
                "employees":      company_row.employees,
                "current_price":  company_row.current_price,
                "week_52_high":   company_row.week_52_high,
                "week_52_low":    company_row.week_52_low,
            }

        def ind_col(field):
            return [_clean(getattr(ind_map.get(d), field, None)) for d in dates]

        signal      = _build_signal_from_cache(price_rows, ind_map)
        performance = compute_performance([_clean(r.close) for r in price_rows])
        news        = fetch_news(ticker)   # always fresh — news changes

        return {
            "ticker":       ticker,
            "timeframe":    timeframe,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "company":      company,
            "performance": performance,
            "news":        news,
            "prices": {
                "dates":  dates,
                "open":   [_clean(r.open)   for r in price_rows],
                "high":   [_clean(r.high)   for r in price_rows],
                "low":    [_clean(r.low)    for r in price_rows],
                "close":  [_clean(r.close)  for r in price_rows],
                "volume": [_clean(r.volume) for r in price_rows],
            },
            "indicators": {
                "rsi":         ind_col("rsi"),
                "macd":        ind_col("macd"),
                "macd_signal": ind_col("macd_signal"),
                "macd_hist":   ind_col("macd_hist"),
                "bb_upper":    ind_col("bb_upper"),
                "bb_middle":   ind_col("bb_middle"),
                "bb_lower":    ind_col("bb_lower"),
                "sma20":       ind_col("sma20"),
                "sma50":       ind_col("sma50"),
                "ema20":       ind_col("ema20"),
                "volatility":  ind_col("volatility"),
            },
            "signal": signal,
        }
