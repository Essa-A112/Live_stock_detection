import math
import yfinance as yf
import pandas as pd
import requests
import os

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
    """Download OHLCV history from Alpaca live market data API."""
    try:
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")

        # Map period to number of days
        period_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        days = period_map.get(period, 180)

        end = pd.Timestamp.utcnow().date()
        start = end - pd.Timedelta(days=days)

        url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key
        }
        params = {
            "start": str(start),
            "end": str(end),
            "timeframe": "1Day",
            "limit": 1000,
            "feed": "iex"
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        bars = data.get("bars", [])
        if not bars:
            return pd.DataFrame()

        df = pd.DataFrame(bars)
        df = df.rename(columns={
            "t": "date",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume"
        })[["date", "open", "high", "low", "close", "volume"]]

        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    except Exception as e:
        print(f"Alpaca fetch failed: {e}")
        return pd.DataFrame()

def fetch_fundamentals(ticker: str) -> dict:
    """Download company info and fundamental metrics from Yahoo Finance."""
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
