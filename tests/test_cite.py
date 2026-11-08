"""cite: BibTeX, text and CITATION.cff."""
import re

import pytest

from quantavane_mcp.checking import CheckError
from quantavane_mcp.citations import CiteError, cite


def balanced(bib: str) -> bool:
    depth = 0
    for ch in bib:
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


def fields(bib: str) -> dict:
    return dict(re.findall(r"^\s+(\w+)\s+= \{(.*)\},?$", bib, re.M))


def test_benchmark(store):
    c = cite(store, "benchmark")
    assert balanced(c.bibtex) and c.bibtex.startswith("@misc{quantavane-open-problems-benchmark,")
    f = fields(c.bibtex)
    assert f["author"] == "Canli, Arhan" and "quantavane-benchmark" in f["howpublished"]
    assert "117 problems" in c.text and "cff-version: 1.2.0" in c.cff and "commit: " in c.cff


def test_problem_names_the_source_of_the_best_value(store):
    c = cite(store, "problem", "1c-lower")
    assert balanced(c.bibtex) and "Koshta" in c.bibtex and "teorth.github.io" in c.text
    with pytest.raises(CiteError):
        cite(store, "problem")
    with pytest.raises(CheckError):
        cite(store, "problem", "nope")


def test_result_by_slug(store):
    c = cite(store, "result", "r-8-12")
    assert balanced(c.bibtex) and "R(8,12) $\\geq$ 523" in c.bibtex and "previously 519" in c.text
    c = cite(store, "result", "t6-k5000-v9")
    assert "doi" in fields(c.bibtex) and "10.5281/zenodo.23839216" in c.bibtex
    with pytest.raises(CiteError):
        cite(store, "result", "no-such-slug")


def test_dataset_replay_server(store):
    d = cite(store, "dataset")
    assert "kaggle.com" in d.bibtex and "CC-BY-4.0" in d.cff
    r = cite(store, "replay", "292")
    assert balanced(r.bibtex) and "quantavane-replays" in r.text
    with pytest.raises(CiteError):
        cite(store, "replay", "99999")
    s = cite(store, "server")
    assert s.bibtex.startswith("@software{quantavane-mcp,") and "version" in fields(s.bibtex)


def test_formats_and_escaping(store):
    only_bib = cite(store, "problem", "covering-36-6-2", "bibtex")
    assert only_bib.text is None and only_bib.bibtex
    only_text = cite(store, "problem", "covering-36-6-2", "text")
    assert only_text.bibtex is None and only_text.text
    c = cite(store, "problem", "ramsey-3-17")
    assert "_" not in re.sub(r"\\_|\\url\{[^}]*\}", "", c.bibtex.split("note")[0])
    with pytest.raises(CiteError):
        cite(store, "everything")
