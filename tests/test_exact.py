from fractions import Fraction

import pytest

from quantavane_mcp.exact import better, decimal_text, fraction_text, parse_value, threshold


@pytest.mark.parametrize("text,value", [
    ("282", Fraction(282)),
    ("0.4103333", Fraction(4103333, 10**7)),
    ("54/125", Fraction(54, 125)),
    (" 477,256 ", Fraction(477256)),
    ("1.5e-3", Fraction(3, 2000)),
    ("-0.25", Fraction(-1, 4)),
    (".5", Fraction(1, 2)),
])
def test_parse_value_exact(text, value):
    assert parse_value(text) == value


@pytest.mark.parametrize("text", ["", "   ", "abc", "1/0", "0x10", "1e999", "nan", "inf", "1,23", "1" * 5000, "2/3/4"])
def test_parse_value_rejects(text):
    with pytest.raises(ValueError):
        parse_value(text)


def test_threshold_exact_value_is_used():
    entry = {"value": "0.432", "exact": "54/125"}
    assert threshold("maximize", entry) == Fraction(54, 125)


def test_threshold_printed_value_moves_by_one_unit_in_last_digit():
    # obb.py: without an exact value, a minimize problem must be beaten below value - 1 unit, maximize above + 1 unit
    assert threshold("minimize", {"value": "1.457854884921989"}) == Fraction("1.457854884921988")
    assert threshold("maximize", {"value": "2.1562247706"}) == Fraction("2.1562247707")
    assert threshold("maximize", {"value": "282"}) == Fraction(283)


def test_better_respects_objective():
    assert better("maximize", Fraction(3), Fraction(2))
    assert not better("maximize", Fraction(2), Fraction(2))
    assert better("minimize", Fraction(1), Fraction(2))
    assert not better("minimize", Fraction(2), Fraction(2))


def test_text_forms():
    assert fraction_text(Fraction(17)) == "17"
    assert fraction_text(Fraction(54, 125)) == "54/125"
    assert decimal_text(Fraction(1, 3), 5) == "0.33333..."
    assert decimal_text(Fraction(1, 4), 5) == "0.25000"
    assert decimal_text(Fraction(-1, 3), 3) == "-0.333..."
    assert decimal_text(Fraction(17)) == "17"


def test_huge_integers_print_exactly():
    n = 7**20000                       # past Python's 4300-digit conversion limit
    assert fraction_text(Fraction(n)).startswith("9136929735") and len(fraction_text(Fraction(n))) == 16902
