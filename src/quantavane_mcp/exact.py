"""Exact values and the benchmark's comparison rule (the same rule as obb.py in quantavane-benchmark)."""
from __future__ import annotations

import re
from decimal import Decimal
from fractions import Fraction
from typing import Any

MAX_VALUE_CHARS = 4000
MAX_EXPONENT = 400

_DECIMAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_FRACTION = re.compile(r"^[+-]?\d+/\d+$")
_GROUPED = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")


def parse_value(text: str) -> Fraction:
    """A value given as an integer ('282'), a decimal ('0.4103333', '1.5e-3', '477,256') or a fraction ('54/125'),
    read exactly. Raises ValueError with the reason otherwise."""
    if not isinstance(text, str):
        raise ValueError("the value must be a string such as '0.4103333', '54/125' or '282'")
    s = text.strip().replace(" ", "")
    if not s:
        raise ValueError("the value is empty")
    if len(s) > MAX_VALUE_CHARS:
        raise ValueError(f"the value has {len(s)} characters; at most {MAX_VALUE_CHARS} are accepted")
    if _GROUPED.match(s):
        s = s.replace(",", "")
    if _FRACTION.match(s):
        num, den = s.split("/")
        if int(den) == 0:
            raise ValueError("the denominator is zero")
        return Fraction(int(num), int(den))
    m = _DECIMAL.match(s)
    if not m:
        raise ValueError(f"{text!r} is not an integer, a decimal or a fraction p/q")
    if m.group(3) and abs(int(m.group(3)[1:])) > MAX_EXPONENT:
        raise ValueError(f"the exponent is larger than {MAX_EXPONENT} in absolute value")
    return Fraction(s)


def threshold(objective: str, entry: dict[str, Any]) -> Fraction:
    """The value a submission must beat (obb.py): the exact value when known; otherwise the printed value moved by one
    unit in its last printed decimal, so that the unrounded original never counts as an improvement."""
    if entry.get("exact"):
        return Fraction(entry["exact"])
    v = entry["value"]
    unit = Fraction(1, 10 ** len(v.split(".")[1])) if "." in v else Fraction(1)
    return Fraction(v) - unit if objective == "minimize" else Fraction(v) + unit


def better(objective: str, a: Fraction, b: Fraction) -> bool:
    return a < b if objective == "minimize" else a > b


def int_text(n: int) -> str:
    """str(n), also past Python's limit on converting very long integers to decimal text."""
    try:
        return str(n)
    except ValueError:
        return format(Decimal(n), "f")


def fraction_text(x: Fraction) -> str:
    """'p/q', or the integer when the denominator is 1."""
    return int_text(x.numerator) if x.denominator == 1 else f"{int_text(x.numerator)}/{int_text(x.denominator)}"


def decimal_text(x: Fraction, digits: int = 20) -> str:
    """x truncated toward zero to `digits` decimals, followed by '...' when digits were cut; for reading only
    (comparisons use the exact value)."""
    if x.denominator == 1:
        return int_text(x.numerator)
    sign = "-" if x < 0 else ""
    q = abs(x)
    whole, rest = divmod(q.numerator, q.denominator)
    frac = (rest * 10 ** digits) // q.denominator
    text = f"{sign}{int_text(whole)}.{str(frac).rjust(digits, '0')}" if digits else f"{sign}{int_text(whole)}"
    return text + ("..." if (rest * 10 ** digits) % q.denominator else "")
