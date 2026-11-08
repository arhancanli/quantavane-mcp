"""search_results over the bundled open data."""
import pytest

from quantavane_mcp.search import SearchError, parse_cell, search


def test_by_table(store):
    r = search(store.open_data, table="spherical-codes", limit=5)
    assert r.total == 443 and r.count == 5 and r.has_more and r.next_offset == 5
    assert all(h.area == "spherical-codes" for h in r.results)
    r2 = search(store.open_data, table="spherical-codes", limit=5, offset=440)
    assert r2.count == 3 and not r2.has_more and r2.next_offset is None


def test_table_by_keeper_name(store):
    assert search(store.open_data, table="Brouwer").total == 39
    assert search(store.open_data, table="codetables").total == 16 + 34


def test_unknown_table_lists_the_tables(store):
    with pytest.raises(SearchError, match="spherical-codes"):
        search(store.open_data, table="nowhere")


def test_covering_array_cell_returns_the_entry(store):
    r = search(store.open_data, cell="CAN(3,2872,4)")
    assert [(e.t, e.k, e.v, e.N, e.previous_N, e.family_rows_k) for e in r.covering_array_entries] == \
        [(3, 2872, 4, 604, 607, 2876)]


def test_covering_array_record_cell(store):
    r = search(store.open_data, cell="CAN(6,5000,9)")
    assert r.total == 1 and r.results[0].ours == "11160081" and r.results[0].previous == "48292736"


def test_covering_array_cell_without_entry_says_so(store):
    r = search(store.open_data, cell="CAN(3,5,4)")
    assert r.covering_array_entries == [] and "no row" in r.interpreted_as


@pytest.mark.parametrize("cell,name", [
    ("C(84,7,2,5)", "C(84,7,2,5)"),
    ("A(51,6,6)", "A(51,6,6) ≥ 11354"),
    ("R(12,8)", "R(8,12) ≥ 523"),
    ("[63,14,33] over GF(5)", "[63,14,33] over GF(5)"),
    ("[[53,23,11]]_7", "[[53,23,11]]_7"),
    ("d22-n119", "119 points in 22 dimensions"),
    ("119 points in 22 dimensions", "119 points in 22 dimensions"),
    ("gap 376428", "Prime gap 376,428"),
    ("Leuven2", "Leuven2"),
])
def test_cells(store, cell, name):
    r = search(store.open_data, cell=cell)
    assert name in [h.name for h in r.results], (cell, [h.name for h in r.results])


def test_dates_and_status(store):
    r = search(store.open_data, date_from="2026-11-06", date_to="2026-11-06", date_field="found", limit=50)
    assert r.total > 0 and all(h.found == "2026-11-06" for h in r.results)
    listed = search(store.open_data, status="listed", limit=1)
    assert listed.total == 946
    with pytest.raises(SearchError):
        search(store.open_data, date_from="2026-11-07", date_to="2026-11-01")


def test_words_and_citation(store):
    r = search(store.open_data, query="orbits group")
    assert r.total > 0
    assert "kaggle.com/datasets/arhancanli12/quantavane-verified-results" in r.citation
    assert r.data_as_of.startswith("open data of 2026-11-07")


def test_newest_first(store):
    r = search(store.open_data, limit=50)
    founds = [h.found or "" for h in r.results]
    assert founds == sorted(founds, reverse=True)


def test_parse_cell_falls_back_to_names():
    desc, pred, ca = parse_cell("NR_TF")
    assert "name" in desc and ca is None
    assert pred({"name": "NR_TF additions", "slug": "ghent-nr-tf-additions"})
