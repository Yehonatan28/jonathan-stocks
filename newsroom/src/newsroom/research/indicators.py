"""Technical indicators, pure Python. Every function takes plain lists (oldest first) and returns a
list of the same length, with None where the window is not full yet. Wilder smoothing for ATR/RSI,
as in the original definitions and in every professional charting package."""
from __future__ import annotations

import math


def sma(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    if len(x) < n:
        return out
    k = 2 / (n + 1)
    e = sum(x[:n]) / n
    out[n - 1] = e
    for i in range(n, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def wilder(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    if len(x) < n:
        return out
    a = sum(x[:n]) / n
    out[n - 1] = a
    for i in range(n, len(x)):
        a = (a * (n - 1) + x[i]) / n
        out[i] = a
    return out


def true_range(h: list[float], lo: list[float], c: list[float]) -> list[float]:
    tr = [h[0] - lo[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])))
    return tr


def atr(h: list[float], lo: list[float], c: list[float], n: int = 14) -> list[float | None]:
    return wilder(true_range(h, lo, c), n)


def rsi(c: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(c)
    if len(c) <= n:
        return out
    gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(c)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(c: list[float], fast: int = 12, slow: int = 26, sig: int = 9):
    ef, es = ema(c, fast), ema(c, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    sig_part = ema([v for v in line[start:]], sig)
    signal = [None] * start + sig_part
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, hist


def bb_width(c: list[float], n: int = 20, k: float = 2.0) -> list[float | None]:
    """(upper - lower) / middle. Low values = a volatility squeeze."""
    out: list[float | None] = [None] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1: i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in w) / n)
        out[i] = (2 * k * sd) / m if m else None
    return out


def pct_rank(value: float, series: list[float]) -> float:
    """Share of `series` at or below `value`, 0-100."""
    vals = [v for v in series if v is not None]
    if not vals:
        return 50.0
    return 100.0 * sum(1 for v in vals if v <= value) / len(vals)


def ret(c: list[float], n: int) -> float | None:
    if len(c) <= n or c[-n - 1] <= 0:
        return None
    return c[-1] / c[-n - 1] - 1


def corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 20:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def daily_returns(c: list[float]) -> list[float]:
    return [c[i] / c[i - 1] - 1 for i in range(1, len(c)) if c[i - 1] > 0]
