import math
import requests
import yfinance as yf
import pandas as pd


def _safe(val):
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return s


def _v7_quote(ticker: str, sess: requests.Session) -> dict:
    """Direct Yahoo Finance v7/finance/quote — different endpoint from quoteSummary,
    more reliable on cloud IPs. Returns the first result dict or {}."""
    try:
        r = sess.get(
            'https://query1.finance.yahoo.com/v7/finance/quote',
            params={'symbols': ticker},
            timeout=8,
        )
        results = r.json().get('quoteResponse', {}).get('result', [])
        return results[0] if results else {}
    except Exception:
        return {}


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV history. Returns empty DataFrame on failure."""
    try:
        df = yf.Ticker(ticker, session=_session()).history(
            period=period, interval=interval, auto_adjust=True
        )
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "date"
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    except Exception:
        return pd.DataFrame()


def fetch_fundamentals(ticker: str) -> dict:
    """Three-tier fundamentals fetch:
    1. fast_info  — chart endpoint, same as history(), never fails
    2. .info      — quoteSummary endpoint, may be blocked on cloud IPs
    3. v7/quote   — alternate REST endpoint, fallback when .info returns empty
    """
    sess = _session()
    yft = yf.Ticker(ticker, session=sess)

    # ── Tier 1: fast_info (always available) ──────────────────────────────
    fi = {}
    for key in ('lastPrice', 'marketCap', 'yearHigh', 'yearLow',
                'regularMarketPreviousClose', 'currency'):
        try:
            fi[key] = _safe(yft.fast_info[key])
        except Exception:
            fi[key] = None

    # ── Tier 2: .info (quoteSummary — may be empty on cloud IPs) ──────────
    info = {}
    try:
        raw = yft.info or {}
        if len(raw) > 5:          # blocked response returns {'maxAge': 1}
            info = raw
    except Exception:
        pass

    # ── Tier 3: v7/quote (only if .info came back empty) ──────────────────
    quote = _v7_quote(ticker, sess) if not info else {}

    def pick(*keys_sources):
        """Return the first non-None value from (key, source_dict) pairs."""
        for key, src in keys_sources:
            v = _safe(src.get(key))
            if v is not None:
                return v
        return None

    name = (
        info.get("longName") or info.get("shortName") or
        quote.get("longName") or quote.get("shortName")
    )

    return {
        "name":           name,
        "sector":         info.get("sector")   or quote.get("sector"),
        "industry":       info.get("industry") or quote.get("industry"),
        "market_cap":     pick(
            ("marketCap",  info),
            ("marketCap",  quote),
            ("marketCap",  fi),
        ),
        "pe_ratio":       pick(
            ("trailingPE", info),
            ("trailingPE", quote),
        ),
        "eps":            pick(
            ("trailingEps",               info),
            ("epsTrailingTwelveMonths",   quote),
        ),
        "beta":           pick(("beta", info), ("beta", quote)),
        "dividend_yield": pick(
            ("dividendYield",                info),
            ("trailingAnnualDividendYield",  quote),
        ),
        "description":    info.get("longBusinessSummary"),
        "website":        info.get("website"),
        "employees":      info.get("fullTimeEmployees"),
        "current_price":  pick(
            ("currentPrice",               info),
            ("regularMarketPrice",         info),
            ("regularMarketPrice",         quote),
            ("lastPrice",                  fi),
        ),
        "week_52_high":   pick(
            ("fiftyTwoWeekHigh", info),
            ("fiftyTwoWeekHigh", quote),
            ("yearHigh",         fi),
        ),
        "week_52_low":    pick(
            ("fiftyTwoWeekLow", info),
            ("fiftyTwoWeekLow", quote),
            ("yearLow",         fi),
        ),
    }


def fetch_news(ticker: str) -> list[dict]:
    """Fetch up to 5 recent news items via yfinance (no API key required)."""
    try:
        items = yf.Ticker(ticker, session=_session()).news or []
        out = []
        for item in items[:5]:
            ts = item.get("providerPublishTime", 0)
            out.append({
                "title":        item.get("title"),
                "source":       item.get("publisher"),
                "published_at": pd.Timestamp(ts, unit="s").strftime("%b %d, %Y") if ts else None,
                "url":          item.get("link"),
            })
        return out
    except Exception:
        return []


def compute_performance(closes: list) -> dict:
    """1-day, 5-day, 30-day % change from an ordered list of close prices."""
    if not closes or len(closes) < 2:
        return {"change_1d": None, "change_5d": None, "change_30d": None}
    last = closes[-1]

    def pct(n):
        if len(closes) > n:
            prev = closes[-n - 1]
            if prev:
                return round((last - prev) / prev * 100, 2)
        return None

    return {"change_1d": pct(1), "change_5d": pct(5), "change_30d": pct(30)}
