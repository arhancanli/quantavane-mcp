"""run_claim_checks: Quantavane's claim pipeline, offline, on an object submitted for a benchmark problem.

The pipeline (the gate Quantavane uses before a result goes to a keeper) says RECORD only when two separately written
checkers both pass the object, every red control (a deliberately broken copy of the object) is refused by every
checker, and the object's value strictly beats the value the table's keeper lists. Here the checkers are the benchmark's own
(sandboxed, exactly as check_candidate runs it) and a second checker written apart from it (independent/second_check.py,
run in the same sandbox); the red controls are built from the submitted object, each broken in a way that must be
refused; the keeper's value is the one on file in the bundled data, with the date it was read. The pipeline re-reads
the keeper's page the same day before a claim is sent: offline, this cannot, and every result says so. Nothing is
written, sent or posted."""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import sandbox
from .checking import PYTHON_FLAGS, Checker, CheckError, find_problem
from .data import Problem
from .exact import better, decimal_text, fraction_text
from .independent import second_check as sc
from .models import ClaimCheck, ClaimResult, KeeperOnFile, LiteratureQuery

SECOND = Path(sc.__file__).resolve()
CLAIM_MIN_TIMEOUT = 600          # the second checkers are plain Python: give every program of a claim this much


def second_kind(p: Problem) -> str | None:
    """The second checker that doubles the problem's checker, or None (collection checkers, analytic constants and
    the routing and scheduling checkers have none yet)."""
    prog = p.checker["program"]
    if "/" in prog:
        return None
    kind = re.sub(r"_check(\.py)?$", "", prog)
    return kind if kind in sc.CHECKS else None


def second_kinds() -> list[str]:
    return sorted(sc.CHECKS)


# ------------------------------------------------------------------------------------------------- red controls


def _text(data: bytes) -> str:
    raw = data.decode("utf-8", "replace")
    return "\n".join(line.split("#")[0] for line in raw.splitlines())


def _lines(text: str) -> list[str]:
    return sc.data_lines(text)


def _join(lines: list[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def _red_ramsey(p: Problem, text: str) -> list[tuple[str, bytes]]:
    s, t = (int(a) for a in p.checker["args"])
    rows = [list(r) for r in _lines(text)]
    n = len(rows)
    if n >= s:
        for i in range(s):
            for j in range(s):
                if i != j:
                    rows[i][j] = "1"
        return [(f"a red K_{s} planted on the vertices 0..{s - 1}", _join(["".join(r) for r in rows]))]
    if n >= t:
        for i in range(t):
            for j in range(t):
                if i != j:
                    rows[i][j] = "0"
        return [(f"a blue K_{t} planted on the vertices 0..{t - 1}", _join(["".join(r) for r in rows]))]
    return []


def _red_multiramsey(p: Problem, text: str) -> list[tuple[str, bytes]]:
    s = int(p.checker["args"][0])
    rows = [list(r) for r in _lines(text)]
    if len(rows) < s:
        return []
    for i in range(s):
        for j in range(s):
            if i != j:
                rows[i][j] = "0"
    return [(f"a K_{s} in colour 0 planted on the vertices 0..{s - 1}", _join(["".join(r) for r in rows]))]


def _red_schur(p: Problem, text: str) -> list[tuple[str, bytes]]:
    kind = p.checker["args"][0]
    s = list(sc.digits(text))
    if kind == "weak" and len(s) >= 3:
        s[1] = s[2] = s[0]
        return [("1, 2 and 3 given one colour (1 + 2 = 3)", ("".join(s) + "\n").encode())]
    if kind == "schur" and len(s) >= 2:
        s[1] = s[0]
        return [("1 and 2 given one colour (1 + 1 = 2)", ("".join(s) + "\n").encode())]
    return []


def _red_vdw(p: Problem, text: str) -> list[tuple[str, bytes]]:
    k = int(p.checker["args"][1])
    s = sc.digits(text)
    if len(s) < k:
        return []
    return [(f"1..{k} given colour 0 (a {k}-term progression)", ("0" * k + s[k:] + "\n").encode())]


def _red_covering(p: Problem, text: str) -> list[tuple[str, bytes]]:
    v, k, t, m = (int(a) for a in p.checker["args"])
    target = set(range(1, m + 1))
    lines = _lines(text)
    kept = [ln for ln in lines if len(target & set(sc.ints(ln))) < t]
    if len(kept) == len(lines):
        return []
    what = f"{{1..{m}}}" if m > t else f"the {t}-subset {{1..{t}}}"
    return [(f"every block meeting {{1..{m}}} in {t} or more points removed ({what} is then uncovered)",
             _join(kept) if kept else b"\n")]


def _red_dup_first(what: str) -> Callable[[Problem, str], list[tuple[str, bytes]]]:
    def red(p: Problem, text: str) -> list[tuple[str, bytes]]:
        lines = _lines(text)
        return [(f"the first {what} repeated", _join(lines[:1] + lines))] if lines else []
    return red


def _red_sph(p: Problem, text: str) -> list[tuple[str, bytes]]:
    d = int(p.checker["args"][0])
    lines = text.splitlines()
    idx = [i for i, ln in enumerate(lines) if len(ln.split(",")) == d and sc.ints(ln)]
    if len(idx) < 2:
        return []
    lines[idx[1]] = lines[idx[0]]
    return [("the second point replaced by the first (cosine 1)", _join(lines))]


def _red_golomb(p: Problem, text: str) -> list[tuple[str, bytes]]:
    marks = sorted(sc.ints(text))
    if len(marks) < 3:
        return []
    marks[-1] = marks[-2] + (marks[1] - marks[0])
    return [("the last mark moved to repeat the first difference", (" ".join(map(str, marks)) + "\n").encode())]


def _red_sortnet(p: Problem, text: str) -> list[tuple[str, bytes]]:
    nums = sc.ints(text)
    comps = [(a, b) for a, b in zip(nums[::2], nums[1::2]) if 0 not in (a, b)]
    if len(comps) * 2 == len(nums):
        return []
    return [("every comparator on channel 0 removed", _join([f"{a} {b}" for a, b in comps]))]


def _red_capset(p: Problem, text: str) -> list[tuple[str, bytes]]:
    pts = text.split()
    if len(pts) < 2 or len(pts[0]) != len(pts[1]):
        return []
    c = "".join(str((-int(x) - int(y)) % 3) for x, y in zip(pts[0], pts[1]))
    return [("the third point of the line through the first two added", _join(pts + [c]))]


def _red_no3line(p: Problem, text: str) -> list[tuple[str, bytes]]:
    toks = text.split()
    pts = [tuple(int(c) for c in t.split(",")) for t in toks if t.count(",") == 1]
    have = set(pts)
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if (a[0] + b[0]) % 2 == 0 and (a[1] + b[1]) % 2 == 0:
                mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
                if mid not in have:
                    return [(f"the midpoint {mid[0]},{mid[1]} of two of the points added",
                             (" ".join(toks + [f"{mid[0]},{mid[1]}"]) + "\n").encode())]
    return []


def _red_hadamard(p: Problem, text: str) -> list[tuple[str, bytes]]:
    lines = _lines(text)
    if not lines:
        return []
    first = lines[0]
    if re.fullmatch(r"[+\-]+", first):
        lines[0] = ("-" if first[0] == "+" else "+") + first[1:]
    else:
        vals = sc.ints(first)
        if not vals:
            return []
        vals[0] = -vals[0]
        lines[0] = " ".join(map(str, vals))
    return [("the entry in row 1, column 1 negated", _join(lines))]


def _red_cwm(p: Problem, text: str) -> list[tuple[str, bytes]]:
    t = text.replace(",", " ").split()
    if t and all(set(x) <= set("+-0") for x in t):
        row = [{"+": 1, "-": -1, "0": 0}[ch] for ch in "".join(t)]
    else:
        row = sc.ints(text)
    if not row:
        return []
    if 0 in row:
        row[row.index(0)] = 1
        why = "a zero entry set to 1 (the weight changes)"
    else:
        row[0] = 0
        why = "the first entry set to 0 (the weight changes)"
    return [(why, (" ".join(map(str, row)) + "\n").encode())]


def _red_costas(p: Problem, text: str) -> list[tuple[str, bytes]]:
    perm = sc.ints(text)
    if len(perm) < 2:
        return []
    perm[1] = perm[0]
    return [("the second dot moved to the first dot's row (not a permutation)", (" ".join(map(str, perm)) + "\n")
             .encode())]


def _red_mols(p: Problem, text: str) -> list[tuple[str, bytes]]:
    n = int(p.checker["args"][0])
    nums = sc.ints(text)
    if len(nums) < n * n or n < 2:
        return []
    nums[0], nums[1] = nums[1], nums[0]
    rows = [" ".join(map(str, nums[i:i + n])) for i in range(0, len(nums), n)]
    return [("two entries of the first row of the first square swapped (a column repeats a symbol)", _join(rows))]


def _red_projplane(p: Problem, text: str) -> list[tuple[str, bytes]]:
    lines = _lines(text)
    if len(lines) < 2:
        return []
    lines[1] = lines[0]
    return [("the second line replaced by the first", _join(lines))]


def _graph(text: str, matrix_ok: bool = False) -> tuple[int, list[tuple[int, int]]] | None:
    try:
        return sc.decode_graph(text, matrix_ok=matrix_ok)
    except (sc.Invalid, sc.Unreadable, ValueError, IndexError):
        return None


def _red_drop_edge(matrix_ok: bool) -> Callable[[Problem, str], list[tuple[str, bytes]]]:
    def red(p: Problem, text: str) -> list[tuple[str, bytes]]:
        g = _graph(text, matrix_ok)
        if g is None or not g[1]:
            return []
        n, edges = g
        a, b = edges[0]
        return [(f"the edge {a} {b} removed (two vertices lose a neighbour)",
                 _join([f"{x} {y}" for x, y in edges[1:]] or ["0 0"]))]
    return red


def _red_degdiam(p: Problem, text: str) -> list[tuple[str, bytes]]:
    diam = int(p.checker["args"][1])
    g = _graph(text)
    if g is None:
        return []
    n, edges = g
    path = [0] + list(range(n, n + diam + 1))
    extra = list(zip(path, path[1:]))
    return [(f"a path of {diam + 1} new vertices hung from vertex 0 (its end is at distance {diam + 1})",
             _join([f"{x} {y}" for x, y in edges + extra]))]


def _red_snake(p: Problem, text: str) -> list[tuple[str, bytes]]:
    s = sc.digits(text)
    return [("the first transition taken twice (back to the vertex 0)", (s[0] + s + "\n").encode())] if s else []


def _red_superperm(p: Problem, text: str) -> list[tuple[str, bytes]]:
    s = sc.digits(text)
    return [("every 1 replaced by 2 (no permutation left)", (s.replace("1", "2") + "\n").encode())] if s else []


def _red_strongpow(p: Problem, text: str) -> list[tuple[str, bytes]]:
    m = int(p.checker["args"][0])
    words = text.split()
    if not words or not words[0].isdigit():
        return []
    w = words[0]
    nb = str((int(w[0]) + 1) % m) + w[1:]
    return [(f"the neighbour {nb} of the first vertex added", _join(words + [nb]))]


def _red_tree(p: Problem, text: str) -> list[tuple[str, bytes]]:
    lines = _lines(text)
    head = lines[:1] if lines and lines[0].split()[0] == "n" else []
    edges = lines[len(head):]
    out = []
    if edges:
        out.append(("the first edge repeated", _join(head + edges[:1] + edges)))
    n = int(head[0].split()[1]) if head else 1 + max((max(sc.ints(e)) for e in edges if sc.ints(e)), default=0)
    if n >= 2:
        out.append((f"a path on {n} vertices (its sequence is unimodal)",
                    _join([f"n {n}"] + [f"{i} {i + 1}" for i in range(n - 1)])))
    return out


def _red_lincode(p: Problem, text: str) -> list[tuple[str, bytes]]:
    lines = _lines(text)
    if not lines:
        return []
    if len(lines) >= 2:
        return [("the second row replaced by the first (rank drops)", _join([lines[0], lines[0]] + lines[2:]))]
    return [("the row replaced by zeros (rank drops)", _join([re.sub(r"\d", "0", lines[0])]))]


def _red_ca(p: Problem, text: str) -> list[tuple[str, bytes]]:
    t, k, v = (int(a) for a in p.checker["args"])
    if t < 2 or k < 2 or v < 2:
        return []
    rows = []
    for ln in _lines(text):
        r = [int(x) for x in ln] if v <= 10 and re.fullmatch(r"\d+", ln) and len(ln) == k else sc.ints(ln)
        if len(r) < 2:
            return []
        r[1] = r[0]
        rows.append(" ".join(map(str, r)))
    return [("column 2 replaced by column 1 (pairs of different symbols there are missed)", _join(rows))]


def _red_matmul(p: Problem, text: str) -> list[tuple[str, bytes]]:
    try:
        doc = json.loads(text)
        for term in doc["terms"]:
            def nonzero(x: Any) -> bool:
                return x not in (0, "0", [0, 0], ["0", "0"], "0/1")
            if all(any(nonzero(e) for row in m for e in row) for m in term):
                u = term[0]
                for row in u:
                    for c, e in enumerate(row):
                        if nonzero(e):
                            row[c] = 0
                            return [("one coefficient of a term set to 0", json.dumps(doc).encode())]
    except (ValueError, KeyError, TypeError):
        pass
    return []


RED: dict[str, Callable[[Problem, str], list[tuple[str, bytes]]]] = {
    "ramsey": _red_ramsey, "multiramsey": _red_multiramsey, "schur": _red_schur, "vdw": _red_vdw,
    "covering": _red_covering, "cw": _red_dup_first("word"), "sph": _red_sph, "kissing": _red_dup_first("vector"),
    "golomb": _red_golomb, "sortnet": _red_sortnet, "capset": _red_capset, "no3line": _red_no3line,
    "hadamard": _red_hadamard, "cwm": _red_cwm, "costas": _red_costas, "mols": _red_mols,
    "projplane": _red_projplane, "srg": _red_drop_edge(True), "cage": _red_drop_edge(False),
    "degdiam": _red_degdiam, "snake": _red_snake, "superperm": _red_superperm, "strongpow": _red_strongpow,
    "tree_unimodal": _red_tree, "lincode": _red_lincode, "ca": _red_ca, "matmul": _red_matmul,
}


def red_controls(p: Problem, data: bytes) -> list[tuple[str, bytes]]:
    """Broken copies of the submitted object, each built so that it must be refused."""
    kind = second_kind(p)
    if kind is None or kind not in RED:
        return []
    text = data.decode("utf-8", "replace") if kind == "matmul" else _text(data)
    try:
        return RED[kind](p, text)
    except (ValueError, IndexError):
        return []


# ------------------------------------------------------------------------------------------------- the claim


def literature_queries(p: Problem) -> list[LiteratureQuery]:
    title = p.raw["title"]
    keeper = (p.best_known.get("provenance") or {}).get("keeper") or ""
    qs = [title, f"{title} new bound"]
    short = re.split(r"[(,;]", keeper)[0].strip()
    if short:
        qs.append(f"{short}: {title}")
    note = "not searched (offline): run each query and add what it finds before the claim is sent"
    return [LiteratureQuery(query=q, backend="stub", results=[], note=note) for q in qs]


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-8:])[-1200:]


def run_second(checker: Checker, p: Problem, kind: str, data: bytes, timeout: int,
               claim: str | None) -> tuple[sandbox.RunResult, str, Fraction | None]:
    args = list(p.checker["args"]) + ([claim or "1"] if kind == "sph" else [])
    args = [str(checker.instance(a, p)) if a.startswith("instances/") else a for a in args]

    def argv(candidate: Path) -> list[str]:
        return [sys.executable, *PYTHON_FLAGS, str(SECOND), kind, *args, str(candidate)]
    run, out, err = checker.run_on(data, checker.candidate_suffix(p), timeout, argv)
    m = re.search(r"^RESULT (-?\d+)(?:/(\d+))?$", run.stdout, re.M)
    value = Fraction(int(m.group(1)), int(m.group(2) or 1)) if (m and run.exit_code == 0 and not run.limit_hit) \
        else None
    return run, _tail(out + ("\n" + err if err else "")), value


def run_claim(checker: Checker, problem_id: str, data: bytes, timeout_s: int | None = None) -> ClaimResult:
    bench = checker.bench
    p = find_problem(bench, problem_id)
    timeout = timeout_s or min(max(checker.default_timeout(p), CLAIM_MIN_TIMEOUT), checker.settings.max_timeout_s)
    if not 1 <= timeout <= checker.settings.max_timeout_s:
        raise CheckError(f"timeout_s must be between 1 and {checker.settings.max_timeout_s}.")
    notes: list[str] = []
    r1 = checker.check_data(p.id, data, timeout)
    ours = Fraction(r1.value) if r1.value is not None else None
    checks: list[ClaimCheck] = [ClaimCheck(
        kind="check", name="the benchmark's checker", program=p.checker["program"],
        passed=r1.verdict == "certified", as_expected=r1.verdict == "certified", verdict=r1.verdict, value=r1.value,
        seconds=r1.checker.seconds, output_tail=r1.reason or r1.checker.output_tail[-600:])]
    kind = second_kind(p)
    if kind is not None:
        run, tail, v2 = run_second(checker, p, kind, data, timeout, r1.value)
        agree = v2 is not None and ours is not None and v2 == ours
        verdict2 = ("no_verdict" if run.limit_hit or run.exit_code not in (0, 1) else
                    "certified" if run.exit_code == 0 else "not_certified")
        if v2 is not None and ours is not None and v2 != ours:
            notes.append(f"the two checkers disagree: {fraction_text(ours)} and {fraction_text(v2)}")
        checks.append(ClaimCheck(kind="check", name="the second checker (written apart from the benchmark's)",
                                 program=f"second_check.py {kind}", passed=agree, as_expected=agree,
                                 verdict=verdict2, value=fraction_text(v2) if v2 is not None else None,
                                 seconds=run.seconds, output_tail=checker.limit_reason(run, timeout)
                                 if run.limit_hit else tail))
    else:
        notes.append(f"no second checker for {p.checker['program']} yet: the pipeline needs two separately written "
                     "programs, so this claim cannot be verified here (second checkers exist for: "
                     + ", ".join(second_kinds()) + ")")
    reds = red_controls(p, data)
    if kind is not None and not reds:
        notes.append("no red control could be built from this object (too small, or not in the problem's format)")
    for name, bad in reds:
        rr = checker.check_data(p.id, bad, timeout)
        worse = rr.value is not None and ours is not None and better(p.objective, ours, Fraction(rr.value))
        refused = rr.verdict == "not_certified" or (rr.verdict == "certified" and worse)
        checks.append(ClaimCheck(kind="red", name=name, program=p.checker["program"], passed=rr.verdict == "certified"
                                 and not worse, as_expected=refused, verdict=rr.verdict, value=rr.value,
                                 seconds=rr.checker.seconds,
                                 output_tail=rr.reason or rr.checker.output_tail[-400:]))
        if kind is not None:
            run, tail, v2 = run_second(checker, p, kind, bad, timeout, r1.value)
            refused2 = run.exit_code == 1 and not run.limit_hit
            checks.append(ClaimCheck(kind="red", name=name, program=f"second_check.py {kind}", passed=run.exit_code == 0,
                                     as_expected=refused2, verdict="no_verdict" if run.limit_hit or run.exit_code
                                     not in (0, 1) else "certified" if run.exit_code == 0 else "not_certified",
                                     value=fraction_text(v2) if v2 is not None else None, seconds=run.seconds,
                                     output_tail=checker.limit_reason(run, timeout) if run.limit_hit else tail))
    n_checkers = len({c.program for c in checks if c.kind == "check"})
    verified = (n_checkers >= 2 and bool(reds) and all(c.as_expected for c in checks))
    page = r1.comparisons[0] if r1.comparisons else None
    improves = bool(r1.improves_page_best)
    record = verified and improves
    prov = p.best_known.get("provenance") or {}
    keeper = KeeperOnFile(
        name=prov.get("keeper") or p.raw.get("page") or "the source named in the problem file",
        url=prov.get("url") or p.raw.get("page"), value=p.best_known["value"], exact=p.best_known.get("exact"),
        source=p.best_known["source"], read=p.as_of(), revision=prov.get("revision"), holder=prov.get("holder"),
        re_read="not done: offline. The pipeline re-reads the keeper's page the same day before a claim is sent; do "
                "that (and check the values in review) before calling this a record.")
    ref = p.best_known["value"]
    ours_text = (r1.value_decimal or r1.value) if r1.value and "/" in r1.value else (r1.value or "none")
    if record:
        verdict = (f"RECORD ({ours_text} vs listed {ref}; both checks OK, red controls all rejected; keeper value on "
                   f"file, {p.as_of()}; re-read the keeper today before sending)")
    elif not verified:
        why = ("only one checker for this problem" if n_checkers < 2 else
               "no red control" if not reds else "a check failed or a red control passed; see checks")
        verdict = f"NOT VERIFIED ({why})"
    else:
        verdict = f"NOT-A-RECORD ({ours_text} vs listed {ref}; keeper value on file, {p.as_of()})"
    lit = literature_queries(p)
    packet = build_packet(p, verdict, record, verified, checks, keeper, lit, r1.certificate_sha256, ours_text, ref)
    return ClaimResult(
        problem_id=p.id, verdict=verdict, record=record, verified=verified, value=r1.value,
        value_decimal=decimal_text(ours) if ours is not None else None, objective=p.objective,
        beats_keeper_value_on_file=improves if r1.verdict == "certified" else None,
        improves_verified_in_review=r1.improves_verified_in_review, keeper=keeper,
        comparisons=r1.comparisons, second_checker=f"second_check.py {kind}" if kind else None,
        red_controls=len(reds), checks=checks, literature=lit, notes=notes, packet=packet,
        certificate_sha256=r1.certificate_sha256, threshold=page.threshold if page else None,
        reproduce=r1.reproduce + (f"\n# second checker: python3 -I second_check.py {kind} "
                                  f"{' '.join(p.checker['args'])} CANDIDATE (in quantavane_mcp/independent/)"
                                  if kind else ""),
        data_as_of=r1.data_as_of)


def build_packet(p: Problem, verdict: str, record: bool, verified: bool, checks: list[ClaimCheck],
                 keeper: KeeperOnFile, lit: list[LiteratureQuery], digest: str, ours: str, ref: str) -> dict[str, str]:
    """The pipeline's packet files, as text (VERDICT, checks.txt, keeper.txt, literature.json, README.md)."""
    lines = [f"[{c.kind}] {c.name} ({c.program}): {'PASS' if c.passed else 'REFUSED'}"
             f"{'' if c.as_expected else '  <- NOT AS EXPECTED'}\n    " + c.output_tail.replace("\n", "\n    ")
             for c in checks]
    reds = [c for c in checks if c.kind == "red"]
    lines.append("SUMMARY checks: %s; red controls refused: %d of %d -> %s" % (
        ", ".join(f"{c.program}={'OK' if c.passed else 'FAIL'}" for c in checks if c.kind == "check"),
        sum(1 for c in reds if c.as_expected), len(reds), "VERIFIED" if verified else "NOT VERIFIED"))
    keeper_txt = (f"{keeper.url or keeper.name}\nvalue on file: {keeper.value} ({keeper.source}); {keeper.read}\n"
                  f"re-read: {keeper.re_read}\nours = {ours}\n")
    readme = [f"# {p.raw['title']}", "",
              f"Problem {p.id} of the Open Problems Benchmark. Object SHA-256 {digest}. Checked offline by "
              "quantavane-mcp's run_claim_checks; nothing posted or sent.", "",
              f"- Keeper: {keeper.name}: value on file {ref} ({keeper.read}). Ours: {ours}. Not re-read (offline).",
              f"- Literature: {len(lit)} queries recorded, not searched yet (stub); literature.json.", "",
              "## Checks (separately written programs)", ""]
    for i, c in enumerate((c for c in checks if c.kind == "check"), 1):
        readme.append(f"{i}. {c.name} ({c.program}): {'passed' if c.passed else 'FAILED'}.")
    if reds:
        readme.append("Red controls, each refused: " + "; ".join(
            f"{c.name} by {c.program} ({'refused' if c.as_expected else 'NOT refused'})" for c in reds) + ".")
    readme += ["", "Status: %s against the keeper's value on file; not submitted." % (
        "verified record" if record else ("NOT verified" if not verified else "NOT a record"))]
    return {"VERDICT": verdict + "\n", "checks.txt": "\n".join(lines) + "\n", "keeper.txt": keeper_txt,
            "literature.json": json.dumps([q.model_dump() for q in lit], indent=1) + "\n",
            "README.md": "\n".join(readme) + "\n"}
