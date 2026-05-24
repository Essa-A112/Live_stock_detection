import os
import math
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def _safe(val):
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _v7_quote(ticker: str) -> dict:
    """Direct Yahoo Finance v7/finance/quote fallback. Returns first result or {}."""
    try:
        r = requests.get(
            'https://query1.finance.yahoo.com/v7/finance/quote',
            params={'symbols': ticker},
            timeout=8,
        )
        results = r.json().get('quoteResponse', {}).get('result', [])
        return results[0] if results else {}
    except Exception:
        return {}


def _quotesummary_modules(ticker: str) -> dict:
    """Tier-4 fallback: fetch a crumb (with session cookie) then call quoteSummary
    with summaryDetail + defaultKeyStatistics modules. Returns a flat dict."""
    _UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
    # Session is required: Yahoo ties the crumb to the session cookie set during
    # the getcrumb call; a plain requests.get loses the cookie and the
    # subsequent quoteSummary call returns Unauthorized.
    sess = requests.Session()
    sess.headers.update({'User-Agent': _UA})
    try:
        crumb_r = sess.get(
            'https://query2.finance.yahoo.com/v1/test/getcrumb',
            timeout=6,
        )
        crumb = crumb_r.text.strip()
        # Yahoo returns "Too+Many+Requests" or empty string when blocking
        if not crumb or '+' in crumb or len(crumb) > 24:
            return {}

        r = sess.get(
            f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
            params={
                'modules': 'summaryDetail,defaultKeyStatistics',
                'crumb':   crumb,
            },
            timeout=10,
        )
        results = r.json().get('quoteSummary', {}).get('result') or []
        if not results:
            return {}

        # Flatten: quoteSummary wraps every value as {"raw": x, "fmt": "…"}
        out = {}
        for module_dict in results[0].values():
            if not isinstance(module_dict, dict):
                continue
            for k, v in module_dict.items():
                if isinstance(v, dict) and 'raw' in v:
                    out[k] = v['raw']
                elif not isinstance(v, (dict, list)):
                    out[k] = v
        return out
    except Exception:
        return {}


def fetch_ohlcv(ticker: str, period: int, interval: str) -> pd.DataFrame:
    """Download OHLCV from Alpaca Markets API using ALPACA_API_KEY / ALPACA_SECRET_KEY.

    period   – look-back window in calendar days
    interval – Alpaca timeframe string: '15Min', '1Hour', or '1Day'

    Returns an empty DataFrame on failure; raises EnvironmentError when
    credentials are not configured so the caller can return a 503.
    """
    api_key    = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise EnvironmentError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")

    is_intraday = interval != "1Day"

    try:
        end   = datetime.utcnow()
        start = end - timedelta(days=period)

        all_bars = []
        page_token = None

        while True:
            params = {
                "timeframe":  interval,
                "start":      start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end":        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "adjustment": "all",
                "limit":      1000,
            }
            if page_token:
                params["page_token"] = page_token

            r = requests.get(
                f"https://data.alpaca.markets/v2/stocks/{ticker}/bars",
                headers={
                    "APCA-API-KEY-ID":     api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
                params=params,
                timeout=15,
            )
            data = r.json()
            bars = data.get("bars") or []
            all_bars.extend(bars)
            page_token = data.get("next_page_token")
            if not page_token:
                break

        if not all_bars:
            return pd.DataFrame()

        df = pd.DataFrame(all_bars).rename(columns={
            "t": "date", "o": "open", "h": "high",
            "l": "low",  "c": "close", "v": "volume",
        })[["date", "open", "high", "low", "close", "volume"]]

        if is_intraday:
            # Keep full timestamp (UTC) so Plotly renders a proper time axis
            df["date"] = pd.to_datetime(df["date"], utc=True).dt.strftime("%Y-%m-%d %H:%M")
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date

        return df.sort_values("date").reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


def fetch_fundamentals(ticker: str) -> dict:
    """Four-tier fundamentals fetch:
    1. fast_info   — chart endpoint, always available; price/mktcap/52W
    2. .info       — quoteSummary via yfinance (curl_cffi); full data when accessible
    3. v7/quote    — always run; fills PE/EPS/beta/dividend when .info is partial
    4. quoteSummary — crumb+cookie session call; last resort for missing fields
    """
    yft = yf.Ticker(ticker)

    # ── Tier 1: fast_info (always available) ──────────────────────────────
    fi = {}
    for key in ('lastPrice', 'marketCap', 'yearHigh', 'yearLow',
                'regularMarketPreviousClose', 'currency'):
        try:
            fi[key] = _safe(yft.fast_info[key])
        except Exception:
            fi[key] = None

    # ── Tier 2: .info (quoteSummary via yfinance curl_cffi session) ────────
    info = {}
    try:
        raw = yft.info or {}
        if len(raw) > 5:          # blocked response returns {'maxAge': 1}
            info = raw
    except Exception:
        pass

    # ── Tier 3: v7/quote (always run — supplements info for missing fields) ──
    # yfinance can return name/sector on cloud IPs but still omit PE/EPS/beta;
    # v7/quote is a separate endpoint that often carries those fields.
    quote = _v7_quote(ticker)

    def pick(*keys_sources):
        """Return the first non-None value from (key, source_dict) pairs."""
        for key, src in keys_sources:
            v = _safe(src.get(key))
            if v is not None:
                return v
        return None

    # ── Tier 4: crumb-based quoteSummary — only when tiers 1–3 still leave
    #    PE/EPS/beta as None (adds ~1 s; skipped when not needed) ────────────
    need_t4 = (
        pick(("trailingPE",  info), ("trailingPE",  quote)) is None or
        pick(("trailingEps", info), ("epsTrailingTwelveMonths", quote)) is None or
        pick(("beta",        info), ("beta",         quote)) is None
    )
    qs = _quotesummary_modules(ticker) if need_t4 else {}

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
            ("trailingPE", qs),
        ),
        "eps":            pick(
            ("trailingEps",               info),
            ("epsTrailingTwelveMonths",   quote),
            ("trailingEps",               qs),
        ),
        "beta":           pick(
            ("beta", info),
            ("beta", quote),
            ("beta", qs),
        ),
        "dividend_yield": pick(
            ("dividendYield",                info),
            ("trailingAnnualDividendYield",  quote),
            ("dividendYield",                qs),
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
    """Fetch up to 5 recent news articles from Finnhub (FINNHUB_API_KEY required)."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return []

    try:
        to_date   = datetime.utcnow()
        from_date = to_date - timedelta(days=7)

        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker,
                "from":   from_date.strftime("%Y-%m-%d"),
                "to":     to_date.strftime("%Y-%m-%d"),
                "token":  api_key,
            },
            timeout=8,
        )
        items = r.json()
        if not isinstance(items, list):
            return []

        out = []
        for item in items[:5]:
            ts = item.get("datetime", 0)
            out.append({
                "title":        item.get("headline"),
                "source":       item.get("source"),
                "published_at": pd.Timestamp(ts, unit="s").strftime("%b %d, %Y") if ts else None,
                "url":          item.get("url"),
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
