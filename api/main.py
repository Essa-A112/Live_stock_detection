import math
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database.db import (
    init_db,
    get_db,
    is_cache_fresh,
    get_cached_prices,
    get_cached_company,
    get_cached_indicators,
    upsert_prices,
    upsert_company,
    upsert_indicators,
)
from data.ingestion import fetch_ohlcv, fetch_fundamentals
from analysis.technical import run_full_analysis, generate_signals

app = FastAPI(title="Stock Analysis API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


def _clean(val):
    """Return None for NaN/Inf so JSON serialisation never chokes."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _col(df, col):
    """Return a list of cleaned values for a DataFrame column."""
    if col not in df.columns:
        return []
    return [_clean(v) for v in df[col].tolist()]


@app.get("/stock/{ticker}")
def get_stock(ticker: str):
    ticker = ticker.upper().strip()

    with get_db() as db:
        fresh = is_cache_fresh(ticker, db)

        if fresh:
            # Serve from cache
            price_rows = get_cached_prices(ticker, db)
            company_row = get_cached_company(ticker, db)
            ind_rows = get_cached_indicators(ticker, db)

            if not price_rows:
                fresh = False

        if not fresh:
            # Fetch live data
            df = fetch_ohlcv(ticker)
            if df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for ticker '{ticker}'. Check the symbol and try again.",
                )

            fundamentals = fetch_fundamentals(ticker)

            df = run_full_analysis(df)
            signal = generate_signals(df)

            # Persist
            price_dicts = df[["date", "open", "high", "low", "close", "volume"]].to_dict("records")
            upsert_prices(ticker, price_dicts, db)
            upsert_company(ticker, fundamentals, db)

            ind_cols = ["date", "rsi", "macd", "macd_signal", "macd_hist",
                        "bb_upper", "bb_middle", "bb_lower", "sma20", "sma50", "ema20", "volatility"]
            ind_dicts = df[[c for c in ind_cols if c in df.columns]].to_dict("records")
            upsert_indicators(ticker, ind_dicts, db)

            # Build response directly from live df
            dates = [str(d) for d in df["date"].tolist()]
            return {
                "ticker": ticker,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "company": fundamentals,
                "prices": {
                    "dates": dates,
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

        # Assemble response from cached rows
        dates   = [str(r.date) for r in price_rows]
        company = {}
        if company_row:
            company = {
                "name": company_row.name,
                "sector": company_row.sector,
                "industry": company_row.industry,
                "market_cap": company_row.market_cap,
                "pe_ratio": company_row.pe_ratio,
                "eps": company_row.eps,
                "beta": company_row.beta,
                "dividend_yield": company_row.dividend_yield,
                "description": company_row.description,
                "website": company_row.website,
                "employees": company_row.employees,
                "current_price": company_row.current_price,
                "week_52_high": company_row.week_52_high,
                "week_52_low": company_row.week_52_low,
            }

        ind_map = {str(r.date): r for r in ind_rows}

        def ind_col(field):
            return [_clean(getattr(ind_map.get(d), field, None)) for d in dates]

        # Rebuild a minimal df to regenerate signal from cached indicators
        import pandas as pd
        cached_df_data = {
            "date":       [r.date for r in price_rows],
            "close":      [r.close for r in price_rows],
            "rsi":        [_clean(ind_map.get(str(r.date), type("x", (), {"rsi": None})()).rsi) if str(r.date) in ind_map else None for r in price_rows],
            "macd":       [_clean(ind_map.get(str(r.date), type("x", (), {"macd": None})()).macd) if str(r.date) in ind_map else None for r in price_rows],
            "macd_signal":[_clean(ind_map.get(str(r.date), type("x", (), {"macd_signal": None})()).macd_signal) if str(r.date) in ind_map else None for r in price_rows],
            "macd_hist":  [_clean(ind_map.get(str(r.date), type("x", (), {"macd_hist": None})()).macd_hist) if str(r.date) in ind_map else None for r in price_rows],
            "bb_upper":   [_clean(ind_map.get(str(r.date), type("x", (), {"bb_upper": None})()).bb_upper) if str(r.date) in ind_map else None for r in price_rows],
            "bb_middle":  [_clean(ind_map.get(str(r.date), type("x", (), {"bb_middle": None})()).bb_middle) if str(r.date) in ind_map else None for r in price_rows],
            "bb_lower":   [_clean(ind_map.get(str(r.date), type("x", (), {"bb_lower": None})()).bb_lower) if str(r.date) in ind_map else None for r in price_rows],
        }
        cached_df = pd.DataFrame(cached_df_data)
        signal = generate_signals(cached_df)

        return {
            "ticker": ticker,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "company": company,
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
