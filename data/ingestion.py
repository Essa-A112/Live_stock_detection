import math
import yfinance as yf
import pandas as pd


def _safe(val):
    """Return None for NaN/Inf float values."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV history. Returns empty DataFrame on failure."""
    try:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "date"
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    except Exception:
        return pd.DataFrame()


def fetch_fundamentals(ticker: str) -> dict:
    """Download company info and fundamental metrics. Missing values become None."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    def g(key):
        return _safe(info.get(key))

    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": g("marketCap"),
        "pe_ratio": g("trailingPE"),
        "eps": g("trailingEps"),
        "beta": g("beta"),
        "dividend_yield": g("dividendYield"),
        "description": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
        "current_price": g("currentPrice") or g("regularMarketPrice"),
        "week_52_high": g("fiftyTwoWeekHigh"),
        "week_52_low": g("fiftyTwoWeekLow"),
    }
