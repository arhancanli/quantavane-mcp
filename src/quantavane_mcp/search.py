"""search_results: our verified results from the bundled open data, by table, cell or date."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .data import OpenData
from .models import CoveringArrayEntry, SearchHit, SearchResult

DATASET = "https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results"


class SearchError(ValueError):
    """A query the caller can fix."""


def _norm(s: str) -> str:
    return re.sub(r"[\s_]+", "", s.lower()).replace("≥", ">=")


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _p(r: dict[str, Any], key: str) -> int | None:
    v = (r.get("params") or {}).get(key)
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_cell(cell: str) -> tuple[str, Callable[[dict[str, Any]], bool], tuple[int, int, int] | None]:
    """(description, record predicate, covering-array (t, k, v) or None) for a cell such as CAN(3,2872,4),
    C(84,7,2,5), A(51,6,6), R(8,12), [63,14,33] over GF(5), [[53,23,11]]_7, d22-n119, 'gap 376428' or a name."""
    s = cell.strip()
    c = re.sub(r"\s+", "", s)
    m = re.fullmatch(r"CAN\((\d+),(\d+),(\d+)\)", c, re.I) or re.fullmatch(r"CA\(\d+;(\d+),(\d+),(\d+)\)", c, re.I)
    if m:
        t, k, v = (int(x) for x in m.groups())
        return (f"covering array CAN({t},{k},{v}) (strength t={t}, k={k} columns, v={v} symbols)",
                lambda r: r["area"] == "covering-arrays" and (_p(r, "t"), _p(r, "k"), _p(r, "v")) == (t, k, v),
                (t, k, v))
    m = re.fullmatch(r"C\((\d+),(\d+),(\d+)(?:,(\d+))?\)", c, re.I)
    if m:
        v, k, t = (int(x) for x in m.groups()[:3])
        mm = int(m.group(4)) if m.group(4) else t
        return (f"covering design C({v},{k},{t}{',' + str(mm) if mm != t else ''})",
                lambda r: r["area"] == "coverings" and (_p(r, "v"), _p(r, "k"), _p(r, "t")) == (v, k, t)
                and (_p(r, "m") if _p(r, "m") is not None else _p(r, "t")) == mm, None)
    m = re.fullmatch(r"A\((\d+),(\d+),(\d+)\)", c, re.I)
    if m:
        n, d, w = (int(x) for x in m.groups())
        return (f"constant weight code A({n},{d},{w})",
                lambda r: r["area"] == "constant-weight" and (_p(r, "n"), _p(r, "d"), _p(r, "w")) == (n, d, w), None)
    m = re.fullmatch(r"R\((\d+),(\d+)\)", c, re.I)
    if m:
        a, b = sorted(int(x) for x in m.groups())
        return (f"Ramsey number R({a},{b})",
                lambda r: r["area"] == "ramsey" and sorted([_p(r, "s") or 0, _p(r, "t") or 0]) == [a, b], None)
    m = re.fullmatch(r"\[\[(\d+),(\d+)(?:,(\d+))?\]\]_?\(?(\d+)\)?", c)
    if m:
        n, k, q = int(m.group(1)), int(m.group(2)), int(m.group(4))
        return (f"quantum code [[{n},{k}]]_{q}",
                lambda r: r["area"] == "quantum-codes" and (_p(r, "n"), _p(r, "k"), _p(r, "q")) == (n, k, q), None)
    m = re.fullmatch(r"\[(\d+),(\d+)(?:,(\d+))?\]_?(?:over)?(?:GF)?\(?(\d+)\)?", c, re.I)
    if m:
        n, k, q = int(m.group(1)), int(m.group(2)), int(m.group(4))
        return (f"linear code [{n},{k}] over GF({q})",
                lambda r: r["area"] == "codes" and (_p(r, "n"), _p(r, "k"), _p(r, "q")) == (n, k, q), None)
    m = re.fullmatch(r"d(\d+)[-_,]?n(\d+)", c, re.I) or re.fullmatch(r"(\d+)points?in(\d+)dim\w*", c, re.I)
    if m:
        d, n = (int(m.group(1)), int(m.group(2))) if c.lower().startswith("d") else (int(m.group(2)), int(m.group(1)))
        return (f"spherical code: {n} points in {d} dimensions",
                lambda r: r["area"] == "spherical-codes" and (_p(r, "d"), _p(r, "n")) == (d, n), None)
    m = re.fullmatch(r"(?:primegap|gap)([\d,]+)", c, re.I)
    if m:
        g = _num(m.group(1))
        return f"prime gap {g:,}", lambda r: r["area"] == "prime-gaps" and _p(r, "gap") == g, None
    key = _norm(s)
    return (f"name or slug containing {s!r}",
            lambda r: key in _norm(r.get("name", "")) or key in _norm(r.get("slug", "")), None)


def tables(records: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in records:
        out.setdefault(r["area"], (r.get("venue") or {}).get("name", ""))
    return dict(sorted(out.items()))


def _text(v: Any) -> str | None:
    return None if v is None else str(v)


def search(od: OpenData, *, query: str | None = None, table: str | None = None, cell: str | None = None,
           date_from: str | None = None, date_to: str | None = None, date_field: str = "either",
           status: str | None = None, limit: int = 10, offset: int = 0) -> SearchResult:
    records = od.records
    preds: list[Callable[[dict[str, Any]], bool]] = []
    said: list[str] = []
    ca_cell = None
    if table:
        key = _norm(table)
        known = tables(records)
        areas = {a for a, venue in known.items() if key in _norm(a) or key in _norm(venue)}
        if not areas:
            raise SearchError(f"No table matches {table!r}. Tables: " +
                              "; ".join(f"{a} ({v})" for a, v in known.items()))
        preds.append(lambda r: r["area"] in areas)
        said.append("table " + ", ".join(sorted(areas)))
    if cell:
        desc, pred, ca_cell = parse_cell(cell)
        preds.append(pred)
        said.append(desc)
    if query:
        words = [_norm(w) for w in query.split() if w.strip()]

        def has_words(r: dict[str, Any]) -> bool:
            hay = _norm(" ".join(str(x) for x in (r.get("name"), r.get("slug"), r.get("area"),
                                                   (r.get("venue") or {}).get("name"), r.get("construction")) if x))
            return all(w in hay for w in words)
        preds.append(has_words)
        said.append(f"text {query!r}")
    if status:
        preds.append(lambda r: r.get("status") == status)
        said.append(f"status {status}")
    if date_from or date_to:
        lo, hi = date_from or "0000-00-00", date_to or "9999-99-99"
        if lo > hi:
            raise SearchError("date_from is after date_to.")
        fields = ("found", "status_date") if date_field == "either" else (date_field,)
        preds.append(lambda r: any(r.get(f) and lo <= r[f] <= hi for f in fields))
        said.append(f"{' or '.join(fields)} from {lo if date_from else 'the start'} to {hi if date_to else 'today'}")
    hits = [r for r in records if all(p(r) for p in preds)]
    hits.sort(key=lambda r: (r.get("found") or "", r.get("area", ""), r.get("name", "")), reverse=True)
    page = hits[offset:offset + limit]
    entries: list[CoveringArrayEntry] = []
    if ca_cell:
        t, k, v = ca_cell
        for rt, rv, k0, k1, n, prev, fam, src in od.covering_array_runs:
            if (rt, rv) == (t, v) and k0 <= k <= k1:
                entries.append(CoveringArrayEntry(t=t, k=k, v=v, N=n, previous_N=prev, family_rows_k=fam, source=src))
        if not entries:
            said.append("no row of covering_array_entries.csv for this cell (it lists the cells of the live ca-tools "
                        "table where our families give the smallest known size; first entries past the table's width "
                        "are counted in totals.json only)")
    more = offset + len(page) < len(hits)
    asof = od.totals.get("date")
    return SearchResult(
        total=len(hits), count=len(page), offset=offset, has_more=more,
        next_offset=offset + len(page) if more else None,
        interpreted_as="; ".join(said) or "every result",
        results=[SearchHit(area=r["area"], name=r["name"], ours=_text(r.get("ours")), previous=_text(r.get("previous")),
                           status=r.get("status", ""), status_date=r.get("status_date"), found=r.get("found"),
                           venue=(r.get("venue") or {}).get("name", ""), venue_url=(r.get("venue") or {}).get("url"),
                           data_url=r.get("data_url"), slug=r["slug"]) for r in page],
        covering_array_entries=entries,
        citation=(f"Quantavane verified results, {DATASET} (CC BY 4.0), as of {asof}. A result counts as verified once "
                  "its table lists it (status 'listed'). cite(target='result', id=SLUG) gives BibTeX for one result."),
        data_as_of=f"open data of {asof} (records.json, {len(records)} results; "
                   f"{od.totals.get('verified_results', 0):,} verified results in all)")
