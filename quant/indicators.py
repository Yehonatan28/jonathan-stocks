"""Technical indicators, one definition each, used by every route and by the engine.

Conventions (the ones charting platforms and the original authors use):
* SMA: arithmetic mean of the last n closes; undefined (NaN) until n values exist.
* EMA: alpha = 2/(n+1), seeded with the SMA of the first n values.
* Wilder smoothing (RMA): alpha = 1/n, seeded with the SMA of the first n values;
  used by RSI, ATR and ADX as J. Welles Wilder defined them (1978).
* Every value at bar i uses bars <= i only, so backtests that walk forward over these
  series never see the future.
Inputs are pandas Series/DataFrames indexed by date; outputs keep the same index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def _seeded(x: pd.Series, n: int, alpha: float) -> pd.Series:
    """Exponential smoothing seeded with the SMA of the first n valid values."""
    vals = x.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    valid = np.flatnonzero(~np.isnan(vals))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    start = valid[0]
    seed_end = start + n                     # first n values from the first valid one
    window = vals[start:seed_end]
    if np.isnan(window).any():
        return pd.Series(out, index=x.index)
    prev = window.mean()
    out[seed_end - 1] = prev
    for i in range(seed_end, len(vals)):
        v = vals[i]
        prev = prev if np.isnan(v) else prev + alpha * (v - prev)
        out[i] = prev
    return pd.Series(out, index=x.index)


def ema(x: pd.Series, n: int) -> pd.Series:
    return _seeded(x, n, 2.0 / (n + 1))


def rma(x: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average."""
    return _seeded(x, n, 1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI. 100 when there are no losses in the window, 0 when no gains."""
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma((-delta).clip(lower=0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = gain / loss
        out = 100 - 100 / (1 + rs)
    out[(loss == 0) & (gain > 0)] = 100.0
    out[(loss == 0) & (gain == 0)] = 50.0
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["High"].iloc[0] - df["Low"].iloc[0]       # no previous close on the first bar
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(ADX, +DI, -DI), Wilder's directional movement system."""
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    plus_dm.iloc[0] = minus_dm.iloc[0] = np.nan
    tr = true_range(df)
    tr.iloc[0] = np.nan
    atr_n = rma(tr, n)
    plus_di = 100 * rma(plus_dm, n) / atr_n
    minus_di = 100 * rma(minus_dm, n) / atr_n
    with np.errstate(divide="ignore", invalid="ignore"):
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return rma(dx, n), plus_di, minus_di


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(MACD line, signal line, histogram)."""
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """(middle, upper, lower, %B). Population standard deviation, as Bollinger defines the bands."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pct_b = (close - lower) / (upper - lower)
    return mid, upper, lower, pct_b


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP over the frame given (pass one session's intraday bars for a session VWAP)."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    return (typical * df["Volume"]).cumsum() / df["Volume"].cumsum().replace(0, np.nan)


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    """Slow stochastic (%K smoothed by `smooth`, %D = SMA(d) of %K)."""
    lo = df["Low"].rolling(k, min_periods=k).min()
    hi = df["High"].rolling(k, min_periods=k).max()
    with np.errstate(divide="ignore", invalid="ignore"):
        fast_k = 100 * (df["Close"] - lo) / (hi - lo)
    slow_k = sma(fast_k, smooth)
    return slow_k, sma(slow_k, d)


def relative_volume(volume: pd.Series, n: int = 20) -> pd.Series:
    """Today's volume against the average of the previous n sessions (today excluded)."""
    return volume / volume.shift(1).rolling(n, min_periods=n).mean()


def momentum(close: pd.Series, n: int = 63) -> pd.Series:
    """Rate of change over n sessions, in percent."""
    return (close / close.shift(n) - 1) * 100
