"""compare_to_record: exact comparison with the page best and the verified values in review."""
from fractions import Fraction

import pytest

from quantavane_mcp.checking import CheckError
from quantavane_mcp.exact import parse_value


def test_equal_to_the_record_does_not_improve(checker):
    r = checker.compare("ramsey-5-15", Fraction(282))
    assert r.improves_page_best is False and r.improves_verified_in_review is None
    assert "R(5,15) >= n + 1" in r.note and "read 6 Nov 2026" in r.best_known_read


def test_one_more_vertex_improves_ramsey(checker):
    assert checker.compare("ramsey-5-15", Fraction(283)).improves_page_best is True


def test_minimize_problems_need_a_smaller_value(checker):
    assert checker.compare("covering-17-7-4-6", Fraction(16)).improves_page_best is True
    assert checker.compare("covering-17-7-4-6", Fraction(17)).improves_page_best is False
    assert checker.compare("cvrp-antwerp1", parse_value("477,255")).improves_page_best is True


def test_exact_record_compared_exactly(checker):
    # 1c-lower: page best known exactly as a fraction; a value one unit above the fraction's 30th decimal improves
    exact = Fraction("134648548624804778248790016/328144294688458468928334649")
    assert checker.compare("1c-lower", exact).improves_page_best is False
    assert checker.compare("1c-lower", exact + Fraction(1, 10**30)).improves_page_best is True


def test_verified_in_review_is_compared_apart(checker):
    r = checker.compare("1c-lower", parse_value("0.4104"))
    assert r.improves_page_best is True and r.improves_verified_in_review is True
    r = checker.compare("1c-lower", parse_value("0.41035"))
    assert r.improves_page_best is True and r.improves_verified_in_review is False
    assert [c.reference for c in r.comparisons] == ["page best", "verified in review"]


def test_printed_value_without_exact_needs_more_than_its_last_digit(checker):
    # 1d-upper: page value 1.457854884921989 printed only; it must be beaten below 1.457854884921988
    assert checker.compare("1d-upper", parse_value("1.4578548849219885")).improves_page_best is False
    assert checker.compare("1d-upper", parse_value("1.4578548849219879")).improves_page_best is True


def test_claims_not_replayed_are_listed_not_compared(checker):
    r = checker.compare("68a-lower", parse_value("0.44"))
    assert [c.value for c in r.claimed_not_replayed] == ["0.447"]
    assert all(c.reference != "claimed" for c in r.comparisons)


def test_unknown_problem_and_bad_value(checker):
    with pytest.raises(CheckError):
        checker.compare("no-such-problem", Fraction(1))
    with pytest.raises(ValueError):
        parse_value("twelve")
