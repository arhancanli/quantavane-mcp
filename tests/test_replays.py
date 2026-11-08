"""get_replay over the bundled index of quantavane-replays."""
import pytest

from quantavane_mcp.replays import ReplayError, find, parse_row


def test_by_pull_request(store):
    r = find(store.replays, pr=292)
    assert r.found and r.matches[0].heading.startswith("C1a, C1c and C1d")
    m = r.matches[0]
    assert any("#292" in row and "134648548624804778248790016" in row for row in m.rows)
    assert m.rederive[0].startswith("git clone https://github.com/arhancanli/quantavane-replays")
    assert "./fetch.sh && ./run_all.sh" in m.rederive
    assert m.readme_url.endswith("#c1a-c1c-and-c1d-3-to-7-november-2026")


def test_by_row_goes_through_the_asterisk_index(store):
    r = find(store.replays, row="1c Kos2026")
    assert r.found
    assert [(a.constant, a.tag, a.status_class) for a in r.asterisk_rows] == [("1c", "Kos2026", "a")]
    assert r.matches[0].heading.startswith("C1a, C1c and C1d")      # via #292, Koshta's row
    assert "87b4ebb" in r.asterisk_snapshot


def test_by_row_tag_in_a_section(store):
    r = find(store.replays, row="42a Gri26")
    assert r.found and r.matches[0].heading.startswith("C42: Turán")
    assert any("[Gri26]" in row for row in r.matches[0].rows) or "Gri26" in r.matches[0].summary
    assert "(cd c42 && ./fetch.sh && ./run_all.sh)" in r.matches[0].rederive


def test_by_constant(store):
    r = find(store.replays, constant="42a", limit=10)
    assert len(r.matches) == 4 and all("42" in m.constants for m in r.matches)
    assert find(store.replays, constant="C68").found


def test_c_checkers_say_they_need_a_compiler(store):
    r = find(store.replays, pr=222)
    assert r.found and r.matches[0].heading.startswith("C12a")
    assert any("C compiler" in c for c in r.matches[0].rederive)


def test_not_found_is_an_answer_not_an_error(store):
    r = find(store.replays, pr=99999)
    assert not r.found and r.matches == [] and "No replay" in r.note


def test_bad_queries(store):
    with pytest.raises(ReplayError):
        find(store.replays)
    with pytest.raises(ReplayError):
        find(store.replays, constant="forty-two")
    with pytest.raises(ReplayError):
        parse_row("???")


def test_parse_row():
    assert parse_row("1c Kos2026") == ((1, "c"), "Kos2026")
    assert parse_row("42a [Gri26]") == ((42, "a"), "Gri26")
    assert parse_row("Kos2026") == (None, "Kos2026")


def test_replay_folders_without_a_readme_section_are_found(store):
    r = find(store.replays, pr=187)
    m = r.matches[0]
    assert r.found and m.heading.startswith("C4b") and m.folder_urls[0].endswith("/c4b")
    assert m.readme_url == m.folder_urls[0] and "Kra2026" in m.summary
    assert "(cd c4b && ./fetch.sh && ./run_all.sh)" in m.rederive
