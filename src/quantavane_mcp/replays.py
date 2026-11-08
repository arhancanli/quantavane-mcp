"""get_replay: our independent replays of certificates in the optimization constants repository, from the bundled
index of github.com/arhancanli/quantavane-replays."""
from __future__ import annotations

import re
from typing import Any

from .data import ReplayIndex
from .models import AsteriskRow, ReplayMatch, ReplayResult

_TAG = re.compile(r"\[?([A-Z][A-Za-z]*\d{2,4}[a-z]?)\]?$")
_CONST = re.compile(r"^[Cc]?(\d{1,3})([a-z]{0,2})$")


class ReplayError(ValueError):
    """A query the caller can fix."""


def norm_constant(text: str) -> tuple[int, str] | None:
    m = _CONST.match(text.strip())
    return (int(m.group(1)), m.group(2)) if m else None


def constant_matches(q: tuple[int, str], c: str) -> bool:
    cc = norm_constant(c)
    if cc is None:
        return False
    return cc[0] == q[0] and (cc[1] == q[1] or not cc[1] or not q[1])


def parse_row(row: str) -> tuple[tuple[int, str] | None, str | None]:
    """'1c Kos2026', '42a [Gri26]', 'Kos2026' or '68a' -> (constant, tag)."""
    const, tag = None, None
    for tok in re.split(r"[\s,;]+", row.strip()):
        if not tok:
            continue
        c, t = norm_constant(tok), _TAG.match(tok)
        if const is None and c:
            const = c
        elif tag is None and t:
            tag = t.group(1)
    if const is None and tag is None:
        raise ReplayError(f"Could not read {row!r} as a row: give the constant and the row's reference key, such as "
                          "'1c Kos2026' or '42a Gri26'.")
    return const, tag


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "..."


def find(index: ReplayIndex, pr: int | None = None, row: str | None = None, constant: str | None = None,
         limit: int = 3) -> ReplayResult:
    if pr is None and not row and not constant:
        raise ReplayError("Give pr (a pull request number of teorth/optimizationproblems), row (such as "
                          "'1c Kos2026') or constant (such as '42a').")
    idx = index.index
    const, tag = parse_row(row) if row else (None, None)
    if constant:
        const = norm_constant(constant)
        if const is None:
            raise ReplayError(f"{constant!r} is not a constant id; use the page number of the optimization constants "
                              "repository, such as 1c, 42a or C68.")
    star = idx["asterisk_index"]["rows"]
    star_hits = []
    for r in star:
        if pr is not None and pr in r["prs"]:
            star_hits.append(r)
        elif tag and r["tag"].lower() == tag.lower() and (const is None or constant_matches(const, r["constant"])):
            star_hits.append(r)
        elif const and not tag and pr is None and constant_matches(const, r["constant"]):
            star_hits.append(r)
    row_prs = {p for r in star_hits for p in r["prs"]} if tag else set()

    scored = []
    for s in idx["sections"]:
        c_hit = const is not None and any(constant_matches(const, c) for c in s["constants"])
        if pr is not None:
            if pr not in s["prs"]:
                continue
        elif tag:
            if tag not in s["tags"] and not (row_prs & set(s["prs"])):
                continue
            if const and s["constants"] and not c_hit:
                continue
        elif const and not c_hit:
            continue
        score = (3 if pr is not None else 0) + (2 if tag in s["tags"] else 0) + (1 if row_prs & set(s["prs"]) else 0) \
            + (1 if c_hit else 0)
        scored.append((score, s))
    scored.sort(key=lambda x: (x[1]["dates"] or [""])[-1], reverse=True)   # newest first among equal scores
    scored.sort(key=lambda x: -x[0])
    matches = [_match(idx, s, pr, tag, row_prs) for _, s in scored[:limit]]

    query = ", ".join(x for x in (f"pr #{pr}" if pr is not None else "", f"row {row!r}" if row else "",
                                  f"constant {constant!r}" if constant else "") if x)
    commit = idx["commit"][:7]
    if matches:
        note = (f"{len(scored)} replay section(s) match; {len(matches)} shown. Each replay uses our own code, written "
                "from the definition on the constant page; the certificates' own verifiers were neither read nor run.")
    else:
        consts = sorted({c for s in idx["sections"] for c in s["constants"]}, key=lambda c: norm_constant(c) or (0, ""))
        note = (f"No replay in quantavane-replays at {commit} matches. Its replays cover the constants "
                f"{', '.join(consts)} and the Ramsey lower bounds since Small Ramsey Numbers revision 18; a replay "
                "published after this bundle is not in it (see quantavane://about).")
    return ReplayResult(
        found=bool(matches), query=query, matches=matches,
        asterisk_rows=[AsteriskRow(constant=r["constant"], tag=r["tag"], bound=r["bound"].replace("\\*", "*"),
                                   status_class=r["class"], prs=r["prs"]) for r in star_hits[:10]],
        asterisk_snapshot=idx["asterisk_index"]["snapshot"], replays_commit=idx["commit"], note=note)


def _match(idx: dict[str, Any], s: dict[str, Any], pr: int | None, tag: str | None,
           row_prs: set[int]) -> ReplayMatch:
    repo, commit = idx["repository"], idx["commit"]
    want = ({pr} if pr is not None else set()) | row_prs
    rows = [r["text"] for r in s["rows"] if (want & set(r["prs"])) or (tag and tag in r["tags"])]
    if not rows and pr is None and not tag:
        rows = [r["text"] for r in s["rows"][:3]]
    folders = s["folders"]
    urls = [f"{repo}/tree/{commit}" + ("" if f == "." else f"/{f}") for f in folders]
    checks, results, cmds = [], [], [f"git clone {repo}.git", f"cd quantavane-replays && git checkout {commit[:7]}"]
    for f in folders:
        info = s["files"].get(f, {})
        checks += [(f"{f}/" if f != "." else "") + c for c in info.get("checks", [])]
        results += [(f"{f}/" if f != "." else "") + r for r in info.get("results", [])[:8]]
        steps = (["./fetch.sh"] if info.get("fetch") else []) + (["./run_all.sh"] if info.get("run_all") else [])
        if steps:
            prefix = "" if f == "." else f"(cd {f} && "
            cmds.append(prefix + " && ".join(steps) + ("" if f == "." else ")"))
    if any(c.endswith(".c") for c in checks):
        cmds.append("# needs a C compiler as well as Python 3.9+")
    return ReplayMatch(
        heading=s["heading"], date=(s["dates"] or [None])[-1], constants=s["constants"],
        readme_url=(f"{repo}/blob/{commit}/README.md#{s['anchor']}" if s.get("anchor") else (urls or [repo])[0]),
        folder_urls=urls, summary=_cut(s["summary"], 900),
        rows=[_cut(r, 700) for r in rows[:4]], checks=checks, results=results, rederive=cmds)
