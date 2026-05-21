import math
import numpy as np
import pandas as pd


def _clean(val):
    """Convert NaN/Inf to None for JSON serialisation."""
    if val is None:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).rename("rsi")


def calculate_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = (ema_fast - ema_slow).rename("macd")
    signal_line = macd_line.ewm(span=signal, adjust=False).mean().rename("macd_signal")
    histogram = (macd_line - signal_line).rename("macd_hist")
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(period).mean().rename("bb_middle")
    std = close.rolling(period).std(ddof=0)
    upper = (middle + num_std * std).rename("bb_upper")
    lower = (middle - num_std * std).rename("bb_lower")
    return upper, middle, lower


def calculate_moving_averages(close: pd.Series) -> dict[str, pd.Series]:
    return {
        "sma20": close.rolling(20).mean().rename("sma20"),
        "sma50": close.rolling(50).mean().rename("sma50"),
        "ema20": close.ewm(span=20, adjust=False).mean().rename("ema20"),
    }


def calculate_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    returns = close.pct_change()
    return (returns.rolling(window).std() * math.sqrt(252)).rename("volatility")


def run_full_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Attach all technical indicator columns to the OHLCV DataFrame."""
    close = df["close"]

    df["rsi"] = calculate_rsi(close)

    macd, macd_sig, macd_hist = calculate_macd(close)
    df["macd"] = macd
    df["macd_signal"] = macd_sig
    df["macd_hist"] = macd_hist

    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
    df["bb_upper"] = bb_upper
    df["bb_middle"] = bb_middle
    df["bb_lower"] = bb_lower

    mas = calculate_moving_averages(close)
    df["sma20"] = mas["sma20"]
    df["sma50"] = mas["sma50"]
    df["ema20"] = mas["ema20"]

    df["volatility"] = calculate_volatility(close)

    return df


def generate_signals(df: pd.DataFrame) -> dict:
    """
    Produce a BUY / SELL / HOLD verdict from the most recent row's indicators.
    Weighted scoring: MACD 40%, RSI 35%, Bollinger 25%.
    """
    last = df.dropna(subset=["rsi", "macd", "macd_hist"]).iloc[-1]

    rsi_val = last["rsi"]
    macd_hist_val = last["macd_hist"]
    macd_val = last["macd"]
    signal_val = last["macd_signal"]
    price = last["close"]
    bb_upper = last["bb_upper"]
    bb_lower = last["bb_lower"]
    bb_middle = last["bb_middle"]

    reasons: list[str] = []

    # --- RSI score [-1, 1] ---
    if rsi_val < 20:
        rsi_score = 0.90
        reasons.append(f"RSI critically oversold at {rsi_val:.1f}")
    elif rsi_val < 30:
        rsi_score = 0.70
        reasons.append(f"RSI oversold at {rsi_val:.1f}")
    elif rsi_val < 40:
        rsi_score = 0.30
        reasons.append(f"RSI below neutral zone ({rsi_val:.1f})")
    elif rsi_val > 80:
        rsi_score = -0.90
        reasons.append(f"RSI critically overbought at {rsi_val:.1f}")
    elif rsi_val > 70:
        rsi_score = -0.70
        reasons.append(f"RSI overbought at {rsi_val:.1f}")
    elif rsi_val > 60:
        rsi_score = -0.30
        reasons.append(f"RSI above neutral zone ({rsi_val:.1f})")
    else:
        rsi_score = 0.0
        reasons.append(f"RSI neutral at {rsi_val:.1f}")

    # --- MACD score [-1, 1] ---
    hist_abs = abs(macd_hist_val)
    hist_sign = 1 if macd_hist_val >= 0 else -1
    if hist_abs > 0.5:
        macd_base = 0.85
    elif hist_abs > 0.15:
        macd_base = 0.60
    elif hist_abs > 0.05:
        macd_base = 0.35
    else:
        macd_base = 0.10
    macd_score = hist_sign * macd_base
    if macd_hist_val > 0:
        reasons.append(f"MACD histogram positive ({macd_hist_val:.4f}), bullish momentum")
        if macd_val > 0:
            macd_score = min(1.0, macd_score + 0.15)
            reasons.append("MACD line above zero confirms uptrend")
    else:
        reasons.append(f"MACD histogram negative ({macd_hist_val:.4f}), bearish momentum")
        if macd_val < 0:
            macd_score = max(-1.0, macd_score - 0.15)
            reasons.append("MACD line below zero confirms downtrend")

    # --- Bollinger score [-1, 1] ---
    band_range = bb_upper - bb_lower if (bb_upper - bb_lower) != 0 else 1
    if price < bb_lower:
        bb_score = 0.85
        reasons.append("Price below lower Bollinger Band — potential reversal")
    elif price < (bb_lower + 0.25 * band_range):
        bb_score = 0.55
        reasons.append("Price near lower Bollinger Band")
    elif price > bb_upper:
        bb_score = -0.85
        reasons.append("Price above upper Bollinger Band — potentially overextended")
    elif price > (bb_upper - 0.25 * band_range):
        bb_score = -0.55
        reasons.append("Price near upper Bollinger Band")
    elif price < bb_middle:
        bb_score = 0.15
        reasons.append("Price in lower half of Bollinger Bands")
    elif price > bb_middle:
        bb_score = -0.15
        reasons.append("Price in upper half of Bollinger Bands")
    else:
        bb_score = 0.0
        reasons.append("Price at Bollinger midline")

    # --- Aggregate ---
    combined = rsi_score * 0.35 + macd_score * 0.40 + bb_score * 0.25
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.30:
        verdict = "BUY"
    elif combined < -0.30:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    return {
        "verdict": verdict,
        "confidence": round(abs(combined), 3),
        "strength_score": round(combined, 3),
        "reasons": reasons,
        "component_scores": {
            "rsi_score": round(rsi_score, 3),
            "macd_score": round(macd_score, 3),
            "bollinger_score": round(bb_score, 3),
        },
    }
