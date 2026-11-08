"""cite: BibTeX and plain citation text (and CITATION.cff where it fits) for the benchmark, a problem, a result, the
dataset, a replay or this server."""
from __future__ import annotations

import re
from typing import Any

from . import __version__
from .checking import find_problem
from .data import Store
from .models import CitationResult
from .replays import find as find_replay

AUTHOR_BIB = "Canli, Arhan"
AUTHOR_TEXT = "Arhan Canli (Quantavane)"
BENCHMARK_URL = "https://github.com/arhancanli/quantavane-benchmark"
DATASET_URL = "https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results"
SERVER_URL = "https://github.com/arhancanli/quantavane-mcp"
COVERING_ARRAYS_DOI = "10.5281/zenodo.23839216"
TARGETS = ("benchmark", "problem", "result", "dataset", "replay", "server")


class CiteError(ValueError):
    """A request the caller can fix."""


def _tex(s: str) -> str:
    """Escape the characters BibTeX fields cannot hold as they are."""
    return re.sub(r"([&%#_$])", r"\\\1", s).replace("≥", r"$\geq$").replace("≤", r"$\leq$")


def _bib(kind: str, key: str, fields: dict[str, str]) -> str:
    width = max(len(k) for k in fields)
    body = ",\n".join(f"  {k.ljust(width)} = {{{v}}}" for k, v in fields.items())
    return f"@{kind}{{{key},\n{body}\n}}"


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _cff(title: str, url: str, version: str, date: str | None, license_id: str, commit: str | None = None,
         kind: str = "software") -> str:
    lines = ["cff-version: 1.2.0", 'message: "If you use this, please cite it as below."', f"type: {kind}",
             f'title: "{title}"', f'version: "{version}"', "authors:", "  - family-names: Canli",
             "    given-names: Arhan", "    affiliation: Quantavane", f'url: "{url}"', f"license: {license_id}"]
    if date:
        lines.append(f"date-released: {date}")
    if commit:
        lines.append(f"commit: {commit}")
    return "\n".join(lines) + "\n"


def _year(date: str | None) -> str:
    return (date or "2026")[:4]


def cite(store: Store, target: str, id: str | None = None, fmt: str = "both") -> CitationResult:
    if target not in TARGETS:
        raise CiteError(f"target must be one of {', '.join(TARGETS)}.")
    bench = store.benchmark
    meta = bench.meta
    commit = meta.get("commit") or ""
    bdate = (meta.get("commit_date") or "2026-11-07")[:10]
    bib = text = cff = None

    if target == "benchmark":
        bib = _bib("misc", "quantavane-open-problems-benchmark", {
            "author": AUTHOR_BIB,
            "title": "Open Problems Benchmark (v1): open problems with exact checkers",
            "year": _year(bdate),
            "howpublished": rf"\url{{{BENCHMARK_URL}}}",
            "note": f"Quantavane; {len(bench.problems)} problems; commit {commit[:7]} ({bdate}); MIT licence",
        })
        text = (f"{AUTHOR_TEXT}. Open Problems Benchmark (v1): open problems with exact checkers. {_year(bdate)}. "
                f"{BENCHMARK_URL} (commit {commit[:7]}, {bdate}; {len(bench.problems)} problems).")
        cff = _cff("Open Problems Benchmark", BENCHMARK_URL, "v1", bdate, "MIT", commit or None)

    elif target == "problem":
        if not id:
            raise CiteError("cite(target='problem') needs id, a problem id such as '1c-lower' (see list_problems).")
        p = find_problem(bench, id)
        bk = p.best_known
        bib = _bib("misc", f"quantavane-obb-{_key(p.id)}", {
            "author": AUTHOR_BIB,
            "title": _tex(f"{p.raw['title']} (problem {p.id} of the Open Problems Benchmark v1)"),
            "year": _year(bdate),
            "howpublished": rf"\url{{{BENCHMARK_URL}/blob/{commit[:7] or 'main'}/problems/{p.id}.json}}",
            "note": _tex(f"Best known value {bk['value']}: {bk['source']}. Source page: {p.raw['page']}"),
        })
        text = (f"{AUTHOR_TEXT}. {p.raw['title']}, problem {p.id} of the Open Problems Benchmark (v1), "
                f"{BENCHMARK_URL} (commit {commit[:7]}). Best known value {bk['value']} ({bk['source']}); cite that "
                f"source too: {p.raw['page']}.")

    elif target == "result":
        if not id:
            raise CiteError("cite(target='result') needs id, a result's slug from search_results (such as 'r-8-12').")
        rec = _record(store, id)
        venue = rec.get("venue") or {}
        url = rec.get("data_url") or venue.get("url") or DATASET_URL
        what = f"{rec['name']}" + (f": {rec['ours']}" if str(rec.get("ours")) not in rec["name"] else "")
        prev = f" (previously {rec['previous']})" if rec.get("previous") not in (None, "") else ""
        status = f"{rec.get('status')}" + (f" {rec['status_date']}" if rec.get("status_date") else "")
        note = f"{venue.get('name', 'its table')}, status {status}; Quantavane verified results, {DATASET_URL}"
        if rec.get("area") == "covering-arrays":
            note += f"; doi:{COVERING_ARRAYS_DOI}"
        if rec.get("construction"):
            note += f". Construction: {rec['construction'][:250]}"
        fields = {"author": AUTHOR_BIB, "title": _tex(what + prev), "year": _year(rec.get("found")),
                  "howpublished": rf"\url{{{url}}}", "note": _tex(note)}
        if rec.get("area") == "covering-arrays":
            fields["doi"] = COVERING_ARRAYS_DOI
        bib = _bib("misc", f"quantavane-{_key(rec['slug'])}", fields)
        text = (f"{AUTHOR_TEXT}. {what}{prev}. Found {rec.get('found')}; {venue.get('name', 'its table')} "
                f"({status}). {url}.")

    elif target == "dataset":
        od = store.open_data
        date = od.totals.get("date", "")
        bib = _bib("misc", "quantavane-verified-results", {
            "author": AUTHOR_BIB,
            "title": "Quantavane verified results",
            "year": _year(date),
            "howpublished": rf"\url{{{DATASET_URL}}}",
            "note": f"Records and first entries listed by the public tables, each checked exactly; version of {date}; "
                    "CC BY 4.0",
        })
        text = (f"{AUTHOR_TEXT}. Quantavane verified results (version of {date}). {DATASET_URL}. CC BY 4.0. For the "
                f"covering arrays also cite doi:{COVERING_ARRAYS_DOI}.")
        cff = _cff("Quantavane verified results", DATASET_URL, date, date, "CC-BY-4.0", kind="dataset")

    elif target == "replay":
        if not id:
            raise CiteError("cite(target='replay') needs id: a pull request number (such as '292') or a row "
                            "(such as '1c Kos2026').")
        num = re.fullmatch(r"#?(\d+)", id.strip())
        res = find_replay(store.replays, pr=int(num.group(1))) if num else find_replay(store.replays, row=id)
        if not res.matches:
            raise CiteError(f"No replay matches {id!r}; get_replay lists what there is.")
        m = res.matches[0]
        rc = store.replays.index["commit"]
        bib = _bib("misc", f"quantavane-replay-{_key(m.heading)[:48]}", {
            "author": AUTHOR_BIB,
            "title": _tex(f"Quantavane replays: {m.heading}"),
            "year": _year(m.date),
            "howpublished": rf"\url{{{m.folder_urls[0] if m.folder_urls else m.readme_url}}}",
            "note": _tex(f"Independent exact replay; quantavane-replays commit {rc[:7]}"),
        })
        text = (f"{AUTHOR_TEXT}. Quantavane replays: {m.heading}. "
                f"{m.folder_urls[0] if m.folder_urls else m.readme_url} (commit {rc[:7]}).")

    else:  # server
        bib = _bib("software", "quantavane-mcp", {
            "author": AUTHOR_BIB,
            "title": "quantavane-mcp: an MCP server for open problems with exact checkers",
            "year": "2026",
            "version": __version__,
            "url": SERVER_URL,
            "note": "MIT licence; the bundled verified results are CC BY 4.0",
        })
        text = (f"{AUTHOR_TEXT}. quantavane-mcp {__version__}: an MCP server for open problems with exact checkers. "
                "2026.")
        cff = _cff("quantavane-mcp", SERVER_URL, __version__, None, "MIT")

    if fmt == "bibtex":
        text, cff = None, None
    elif fmt == "text":
        bib = None
    return CitationResult(target=target, id=id, bibtex=bib, text=text, cff=cff)


def _record(store: Store, id: str) -> dict[str, Any]:
    recs = store.open_data.records
    key = id.strip().lower()
    for r in recs:
        if r["slug"].lower() == key:
            return r
    hits = [r for r in recs if r["name"].lower().startswith(key)]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise CiteError(f"{id!r} matches {len(hits)} results; use the slug from search_results, such as "
                        f"{hits[0]['slug']!r}.")
    raise CiteError(f"No result with slug {id!r}; search_results gives each result's slug.")
