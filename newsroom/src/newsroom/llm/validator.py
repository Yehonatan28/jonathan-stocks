"""Iron rule: numbers come from the APIs, never from the model.

Every number in a text the model wrote must exist in the data it was sent. A number counts as
present when it equals a number in the input, or equals one rounded to the precision the
model wrote ("1.2" for 1.23; whole numbers must match exactly). Signs are ignored ("fell 1.2%" for -1.23). Anything else fails
the text.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

# A number not glued to a Latin letter or another digit (so Q3, H100, 8-K's "K" side are skipped
# only where the digits are part of a Latin token). Hebrew prefixes ("ב-3%", "ב3%") are checked.
NUM_RE = re.compile(r"(?<![A-Za-z0-9.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])|(?<![A-Za-z0-9.,])\d+(?:\.\d+)?(?![\d])")


def _dec(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def numbers_in(text: str) -> list[Decimal]:
    out = []
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        # "2.4σ" etc. are fine; a trailing "." ends a sentence and is not part of the number
        d = _dec(tok.rstrip("."))
        if d is not None:
            out.append(d)
    return out


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _walk(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def allowed_numbers(payload: Any) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for v in _walk(payload):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            d = _dec(repr(v)) if isinstance(v, float) else Decimal(v)
            if d is not None:
                allowed.add(abs(d))
        elif isinstance(v, str):
            allowed.update(abs(n) for n in numbers_in(v))
    return allowed


def _matches(n: Decimal, allowed: set[Decimal]) -> bool:
    n = abs(n)
    if n in allowed:
        return True
    places = -n.as_tuple().exponent if n.as_tuple().exponent < 0 else 0
    if places == 0:
        return False          # whole numbers must match exactly: "3%" is not a rounding of 3.07
    q = Decimal(1).scaleb(-places)
    for a in allowed:
        try:
            if a.quantize(q) == n:
                return True
        except InvalidOperation:
            continue
    return False


def invalid_numbers(text: str, allowed: set[Decimal]) -> list[str]:
    return [str(n) for n in numbers_in(text) if not _matches(n, allowed)]


def validate_fields(out: Any, allowed: set[Decimal]) -> tuple[Any, list[str]]:
    """Return (cleaned output, problems). Any string with an unknown number is removed
    (set to None in dicts, dropped from lists), so one bad sentence does not sink the edition."""
    problems: list[str] = []

    def clean(v: Any, path: str) -> Any:
        if isinstance(v, str):
            bad = invalid_numbers(v, allowed)
            if bad:
                problems.append(f"{path}: {', '.join(bad)}")
                return None
            return v
        if isinstance(v, dict):
            return {k: clean(x, f"{path}.{k}") for k, x in v.items()}
        if isinstance(v, list):
            items = [clean(x, f"{path}[{i}]") for i, x in enumerate(v)]
            return [x for x in items if x is not None]
        return v

    return clean(out, "$"), problems
