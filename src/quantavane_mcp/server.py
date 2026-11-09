"""The Quantavane MCP server (FastMCP, stdio): open problems with exact checkers, verified results, replays, citations.

It never opens a network connection. Everything it answers comes from the data bundled with it (or a local benchmark
checkout), with the commits and dates it was read at; see the resource quantavane://about."""
import argparse
import ast
import functools
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import Completion, ToolAnnotations
from pydantic import Field

from . import __version__, gym, sandbox
from .checking import (
    EXACTNESS,
    MAX_INLINE_CHARS,
    Checker,
    CheckError,
    find_problem,
    obb_verdicts,
    score_meaning,
    standalone_command,
)
from .citations import CiteError, cite
from .claims import run_claim, second_kind, second_kinds
from .config import ConfigError, Settings
from .data import Benchmark, DataError, Problem, Store, sha256_file
from .exact import parse_value
from .models import (
    BestKnown,
    CheckerInfo,
    CheckResult,
    CitationResult,
    ClaimResult,
    CollectionEntry,
    CollectionList,
    CollectionProblem,
    CollectionSummary,
    CompareResult,
    GymEnvironments,
    GymVerdict,
    ProblemDetail,
    ProblemList,
    ProblemSummary,
    ReferenceCertificate,
    ReferenceValue,
    ReplayResult,
    SearchResult,
)
from .replays import ReplayError
from .replays import find as find_replay
from .search import SearchError, search

INSTRUCTIONS = """\
Quantavane's open problems, each with an exact checker, plus our verified results, replays and citations. Offline.
- list_problems / get_problem: 149,372 open problems: 395 single problems (Tao's optimization constants, Ramsey numbers,
  cages, kissing numbers, sorting networks, Hadamard matrices, matrix multiplication and more) and 148,977 cells of six
  families read from their keepers' tables (covering designs, spherical codes, linear codes, covering arrays, constant
  weight codes, project scheduling), each with the best known value, its source and when it was read. Family cells are
  listed with family= (and params= or sample=).
- list_collection / get_collection_problem: Quantavane Prestige 100 (one hundred famous open problems, such as R(5,5),
  the kissing numbers and 3 x 3 matrix multiplication, with their keepers' records) and the Quantavane Originals (new
  problems of ours, each with its own checker, novelty check and our first value).
- check_candidate: runs the benchmark's own checker on your certificate, sandboxed. Only verdict "certified" proves a
  value; a value counts as a new best only when improves_page_best is true. Put large certificates in a file and pass
  certificate_path.
- run_claim_checks: Quantavane's claim pipeline on an object: two separately written checkers, red controls (broken
  copies that must be refused) and the keeper's value on file; says RECORD, NOT-A-RECORD or NOT VERIFIED.
- compare_to_record: is a value better than the best known? (Exact comparison; it proves nothing by itself.)
- search_results: Quantavane's verified results by table, cell or date. get_replay: our replay of a pull request in the
  optimization constants repository. cite: BibTeX and citation text.
Report values exactly as the tools give them; never round a bound in your favour."""

BENCHMARK_URL = "https://github.com/arhancanli/quantavane-benchmark"
COLLECTION_FIELDS = ("field", "status", "context", "references", "novelty", "first_values", "baseline")
COLLECTION_ABOUT = {
    "prestige100": "one hundred famous open problems in which one checked object settles the score, each a single "
                   "problem of the benchmark, with its keeper's record, its history and our replayed certificates",
    "originals": "new open problems of ours, each with a novelty check written down before it was added, an exact "
                 "checker of ours and our first value",
}

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ProblemId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]*$",
                                 description="A problem id from list_problems: a single problem such as '1c-lower', "
                                             "'ramsey-5-15' or 'cvrp-antwerp1', or a family cell such as "
                                             "'covering-7-3-2-3', 'sphere-d4-n30', 'code-q2-n32-k14', 'ca-2-5-3', "
                                             "'cw-20-6-5' or 'rcpsp-j120-51'")]

FAMILY_HINTS = {
    "ramsey": "Circulant and block-circulant colourings, then local search on edge colours, are the usual starts; the "
              "checker looks for a red K_s and a blue K_t exactly (Bron-Kerbosch, n <= 2048).",
    "spherical-code": "Start from the reference code and push the largest cosine down (energy or minimax descent, "
                      "then polishing); the score is the largest cosine in 50-digit arithmetic.",
    "covering-design": "Start from the reference design and search for one with fewer blocks (local search, "
                       "symmetric constructions); the checker searches exactly for an uncovered subset.",
    "constant-weight-code": "Orbits of a permutation group of the positions plus greedy completion are the usual "
                            "start; the checker compares every pair of words through their shared positions.",
    "vehicle-routing": "Start from the reference solution and improve it with local search; costs are Euclidean "
                       "distances rounded exactly in integers. The checker needs the CVRPLIB instance file.",
    "constant": "The certificate proves an analytic bound; read the checker's documentation for the exact format and "
                "the method before building one.",
    "originals": "A new problem of ours: read its context, first values and novelty check (get_problem), then the "
                 "checker's documentation; the best known value is our own first value, there to be beaten.",
}


def _fail(e: Exception) -> ToolError:
    return ToolError(str(e))


def _summary(p: Problem) -> ProblemSummary:
    vp = p.verified_pending
    return ProblemSummary(id=p.id, title=p.raw["title"], family=p.family, objective=p.objective,
                          best_known=p.best_known["value"], verified_in_review=vp[0]["value"] if vp else None)


def checker_doc(path: Path) -> str:
    """A checker's own documentation: the module docstring (read with the ast parser, never run) or the C header."""
    text = path.read_text("utf-8")
    if path.suffix == ".py":
        return ast.get_docstring(ast.parse(text)) or ""
    m = re.match(r"\s*/\*(.*?)\*/", text, re.S)
    return re.sub(r"(?m)^ {0,3}", "", m.group(1)).strip() if m else ""


def build_server(settings: Settings | None = None, store: Store | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    store = store or Store(benchmark=Benchmark(settings.benchmark_dir))
    checker = Checker(store, settings)
    bench = store.benchmark
    mcp = FastMCP("quantavane", instructions=INSTRUCTIONS, website_url="https://quantavane.com", log_level="WARNING")

    def tool(name: str, title: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a read-only tool whose description is its docstring on one line."""
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            return mcp.tool(name=name, title=title, description=" ".join((fn.__doc__ or "").split()),
                            annotations=READ_ONLY)(fn)
        return register

    def detail(p: Problem) -> ProblemDetail:
        c = p.checker
        refs = [ReferenceCertificate(file=r.file, uri=r.resource_uri, description=r.description,
                                     expected=r.expected) for r in bench.references.get(p.id, [])]
        if p.objective == "maximize":
            rule = "a certified value larger than the best known one (exactly) improves the problem"
        else:
            rule = "a certified value smaller than the best known one (exactly) improves the problem"
        if not p.best_known.get("exact"):
            rule += ("; the best known value is known only as printed, so it must be beaten by more than one unit in "
                     "its last printed digit")
        return ProblemDetail(
            id=p.id, title=p.raw["title"], family=p.family, page=p.raw.get("page") or page_url(p),
            statement=p.raw["statement"],
            objective=p.objective, submission=p.raw["submission"],
            checker=CheckerInfo(program=c["program"], args=c["args"], value_kind=p.kind, exactness=EXACTNESS[p.kind],
                                score_meaning=score_meaning(p), standalone=standalone_command(p),
                                docs_uri=f"quantavane://checkers/{c['program']}",
                                source_uri=f"quantavane://checkers/{c['program']}/source"),
            best_known=BestKnown(value=p.best_known["value"], exact=p.best_known.get("exact"),
                                 source=p.best_known["source"], read=p.as_of()),
            verified_in_review=[ReferenceValue(value=v["value"], exact=v.get("exact"), source=v["source"])
                                for v in p.verified_pending],
            claimed_not_replayed=[ReferenceValue(value=v["value"], exact=v.get("exact"), source=v["source"])
                                  for v in p.claimed_pending],
            improvement_rule=rule, reference_certificates=refs, instance=checker.instance_status(p),
            params=p.raw.get("params") or _cell_params(p), bound=p.raw.get("bound"),
            provenance=p.best_known.get("provenance"), quantavane_record=bool(p.raw.get("quantavane_record")),
            added=str(p.raw["added"]) if p.raw.get("added") else None, collection=p.collection,
            collection_info={k: p.raw[k] for k in COLLECTION_FIELDS if k in p.raw} or None,
            second_checker=second_kind(p), data_as_of=checker.data_as_of(p))

    def page_url(p: Problem) -> str:
        if p.collection:
            return f"{BENCHMARK_URL}/blob/main/collections/{p.collection}/problems/{p.id}.md"
        return BENCHMARK_URL

    def _cell_params(p: Problem) -> dict[str, Any] | None:
        fam = bench.families.get(p.family)
        if fam is None or p.id not in bench.cells(p.family):
            return None
        return dict(json.loads(bench.cells(p.family)[p.id])["params"])

    family_names = tuple(bench.family_counts()) or ("constant",)
    FamilyName = Literal[family_names]  # type: ignore[valid-type]  # the benchmark's own families, as an enum

    # ----------------------------------------------------------------------------------------------- tools

    @tool("list_problems", "List open problems")
    def list_problems(
        family: Annotated[FamilyName | None, Field(description=(  # type: ignore[valid-type]
            "Only this family. Without it the list holds the single problems; the six families of cells "
            "(covering-design, spherical-code, linear-code, covering-array, constant-weight-code, "
            "project-scheduling) are listed only by family"))] = None,
        params: Annotated[dict[str, str | int] | None, Field(description=(
            "Family cells whose parameters equal these, such as {\"v\": 13, \"t\": 3} for covering designs, "
            "{\"q\": 2, \"n\": 32} for linear codes, {\"d\": 4} for spherical codes or {\"set\": \"J120\"} for "
            "scheduling"))] = None,
        query: Annotated[str | None, Field(max_length=100, description=(
            "Words that must all appear in the id or title, such as 'R(5' or 'autocorrelation'"))] = None,
        sample: Annotated[int | None, Field(ge=1, le=1000, description=(
            "Draw this many cells of the family at random instead (needs family), exactly as "
            "`obb.py sample FAMILY N SEED` draws them"))] = None,
        seed: Annotated[int, Field(ge=0, description="Seed of the draw")] = 0,
        limit: Annotated[int, Field(ge=1, le=200, description="Problems per page")] = 50,
        offset: Annotated[int, Field(ge=0, description="Index of the first problem to return")] = 0,
    ) -> ProblemList:
        """List the open problems of the Open Problems Benchmark (v2.1: 149,372 problems, 395 single problems and
        148,977 cells of six families), one line each: id, title, family, objective, the best known value on its
        source page and the best verified value in review. Filter by family, by a family's parameters or by words;
        or draw a random sample of a family's cells. get_problem gives a problem (or cell) in full. The collections
        (Prestige 100, the Originals) are listed by list_collection."""
        if sample is not None and family not in bench.families:
            raise ToolError(f"sample draws cells of a family: give family, one of {', '.join(bench.families)}.")
        note = None
        if sample is not None:
            assert family is not None
            ids = bench.sample(family, sample, seed)
            note = f"{len(ids)} cells of {family} drawn at random with seed {seed} (as obb.py sample)"
        elif family is not None:
            ids = bench.family_problems(family)
        else:
            ids = list(bench.problems)
        if params:
            want = {k: str(v) for k, v in params.items()}
            if family not in bench.families:
                raise ToolError("params filter the cells of a family: give family too.")
            cells = bench.cells(family)

            def matches(pid: str) -> bool:
                line = cells.get(pid)
                if line is None:
                    return False
                have = json.loads(line)["params"]
                return all(str(have.get(k)) == v for k, v in want.items())
            ids = [pid for pid in ids if matches(pid)]
        words = [w.lower() for w in (query or "").split()]
        if words:
            ids = [pid for pid in ids if all(w in (pid + " " + find_problem(bench, pid).raw["title"]).lower()
                                             for w in words)]
        page_ids = ids[offset:offset + limit]
        more = offset + len(page_ids) < len(ids)
        return ProblemList(total=len(ids), count=len(page_ids), offset=offset, has_more=more,
                           next_offset=offset + len(page_ids) if more else None,
                           problems=[_summary(find_problem(bench, pid)) for pid in page_ids],
                           families=bench.family_counts(), total_problems=bench.total_problems(), note=note,
                           data_as_of=bench.describe())

    @tool("get_problem", "Get one problem")
    def get_problem(problem_id: ProblemId) -> ProblemDetail:
        """Everything about one problem (a single problem, a family cell or one of the Quantavane Originals): the
        statement, the objective, the best known value with its source and when it was read, the verified values in
        review, the certificate format, the exact checker (and how to run it yourself), the improvement rule, our
        reference certificates (as resource URIs) and, for the Originals, the context, novelty check and first
        values."""
        try:
            return detail(find_problem(bench, problem_id))
        except CheckError as e:
            raise _fail(e) from None

    async def with_progress(ctx: Context, limit: int, job: Callable[[], Any]) -> Any:
        """Run job in a worker thread, reporting progress every 5 s to clients that ask for it."""
        done = anyio.Event()

        async def tick() -> None:
            t0 = time.monotonic()
            while not done.is_set():
                with anyio.move_on_after(5):
                    await done.wait()
                if not done.is_set():
                    try:
                        await ctx.report_progress(min(time.monotonic() - t0, limit), limit, "checking")
                    except Exception:   # a client that cannot take progress still gets the result
                        return

        async with anyio.create_task_group() as tg:
            tg.start_soon(tick)
            try:
                return await anyio.to_thread.run_sync(job)
            finally:
                done.set()

    @tool("check_candidate", "Check a certificate exactly")
    async def check_candidate(
        problem_id: ProblemId,
        ctx: Context,
        certificate: Annotated[str | None, Field(max_length=MAX_INLINE_CHARS, description=(
            "The certificate file's text, in the problem's format (get_problem gives it). Give this or "
            "certificate_path, not both"))] = None,
        certificate_path: Annotated[str | None, Field(max_length=4096, description=(
            "Path of a local certificate file, inside the folders the server allows (its working folder and the "
            "temporary folders, or QUANTAVANE_MCP_ROOTS)"))] = None,
        timeout_s: Annotated[int | None, Field(ge=1, le=86400, description=(
            "Wall-clock limit in seconds (default 120; the largest is set by QUANTAVANE_MCP_MAX_TIMEOUT_S, 900 by "
            "default). Some constant checkers need a minute or more"))] = None,
    ) -> CheckResult:
        """Run the benchmark's own exact checker on a certificate and return its verdict and exact score, never a
        guess. The checker runs offline in a sandbox (no shell, argument list only, empty working folder, minimal
        environment, timeout, CPU-time and memory caps, no file writes). verdict: certified (the value is proved),
        not_certified (the certificate is invalid; reason says why) or no_verdict (a limit stopped it; nothing was
        proved). A certified value improves the problem only when improves_page_best is true; comparisons also give
        the verified values still in review. The same check reruns with the public benchmark: see reproduce."""
        limit = timeout_s or settings.timeout_s

        def job() -> tuple[CheckResult | None, Exception | None]:
            try:
                return checker.check(problem_id, certificate=certificate, certificate_path=certificate_path,
                                     timeout_s=timeout_s), None
            except Exception as e:  # reported below as a tool error, never as a verdict
                return None, e
        result, error = await with_progress(ctx, limit, job)
        if isinstance(error, CheckError):
            raise _fail(error)
        if error is not None:
            what = f"{type(error).__name__}: {checker.clean(str(error))}"
            raise ToolError(f"Internal error ({what}); nothing was proved. Please report it with the problem id and "
                            "the certificate's size.")
        assert result is not None
        return result

    collection_names = tuple(bench.collections) or ("originals",)
    CollectionName = Literal[collection_names]  # type: ignore[valid-type]

    def collection_entry(name: str, e: dict[str, Any]) -> CollectionEntry:
        quant = e.get("quantavane")
        ours = bool(quant.get("holds_record")) if isinstance(quant, dict) else (
            "Quantavane" in str(e.get("holder") or "") if name == "originals" else False)
        return CollectionEntry(
            id=str(e["id"]), title=str(e.get("headline") or e.get("title") or e.get("name") or e["id"]),
            slot=e.get("slot"), family=e.get("family"), field=e.get("field"), objective=e.get("objective"),
            record=e.get("record") or e.get("best_known"), holders=e.get("holders") or e.get("holder"),
            status=e.get("status"), flagship=e.get("flagship"), quantavane=ours)

    def summaries() -> list[CollectionSummary]:
        return [CollectionSummary(name=n, title=c.title, problems=len(c.entries),
                                  about=COLLECTION_ABOUT.get(n, c.title)) for n, c in bench.collections.items()]

    @tool("list_collection", "List a collection of our own")
    def list_collection(
        collection: Annotated[CollectionName, Field(description=(  # type: ignore[valid-type]
            "prestige100: Quantavane Prestige 100, famous open problems with their keepers' records; originals: the "
            "Quantavane Originals, new problems of ours"))],
        query: Annotated[str | None, Field(max_length=100, description=(
            "Words that must all appear in the id, title, family, field or record, such as 'R(5' or 'kissing'"))] = None,
        group: Annotated[str | None, Field(max_length=80, description=(
            "Only this family (Prestige 100, such as 'Ramsey numbers' or 'Kissing numbers') or field (Originals, "
            "such as 'Physics' or 'Number theory'), matched without case"))] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Problems per page")] = 50,
        offset: Annotated[int, Field(ge=0, description="Index of the first problem to return")] = 0,
    ) -> CollectionList:
        """List a collection of our own, one line per problem: Quantavane Prestige 100 (slot, problem, family, the
        record as its keeper lists it and who holds it) or the Quantavane Originals (field, title, our best known value,
        status). get_collection_problem gives one in full; check_candidate and run_claim_checks take the ids."""
        c = bench.collections.get(collection)
        if c is None:
            raise ToolError(f"No collection {collection!r}; collections: {', '.join(bench.collections)}.")
        entries = [collection_entry(collection, e) for e in c.entries]
        if group:
            g = group.strip().lower()
            entries = [e for e in entries if g in (e.family or e.field or "").lower()]
        words = [w.lower() for w in (query or "").split()]
        if words:
            entries = [e for e in entries if all(w in " ".join(str(x) for x in (e.id, e.title, e.family, e.field,
                                                                                 e.record) if x).lower()
                                                 for w in words)]
        page = entries[offset:offset + limit]
        more = offset + len(page) < len(entries)
        return CollectionList(total=len(entries), count=len(page), offset=offset, has_more=more,
                              next_offset=offset + len(page) if more else None, collection=collection,
                              title=c.title, entries=page, collections=summaries(), data_as_of=bench.describe())

    @tool("get_collection_problem", "Get one problem of a collection")
    def get_collection_problem(
        collection: Annotated[CollectionName, Field(description="prestige100 or originals")],  # type: ignore[valid-type]
        problem: Annotated[str, Field(min_length=1, max_length=64, description=(
            "The problem id (such as 'ramsey-5-5' or 'qr-sumfree') or, for Prestige 100, its slot number (1 to 100)"))],
    ) -> CollectionProblem:
        """One problem of a collection in full. Prestige 100: the record and its holders, the bound on the other side,
        what would beat it, the keeper with the date and version read, the history of the bounds, why it matters, the
        certificate format, the checker and the leaderboard of certificates we replayed. Originals: the statement,
        context, novelty check, exact first values, references and our best known value."""
        c = bench.collections.get(collection)
        if c is None:
            raise ToolError(f"No collection {collection!r}; collections: {', '.join(bench.collections)}.")
        e = c.entry(problem)
        if e is None:
            raise ToolError(f"No problem {problem!r} in {collection}; list_collection gives the ids"
                            + (" and slots." if collection == "prestige100" else "."))
        pid = str(e["id"])
        full = dict(c.problems[pid].raw) if pid in c.problems else dict(e)
        try:
            p = find_problem(bench, pid)
            how = (f'check_candidate(problem_id="{pid}", certificate_path=...) checks a certificate exactly; '
                   f'run_claim_checks(problem_id="{pid}", ...) runs the claim pipeline; by hand, in a benchmark '
                   f"checkout: {standalone_command(p)}")
        except CheckError:
            how = "this problem has no checker in the bundled benchmark"
        return CollectionProblem(collection=collection, id=pid, title=str(e.get("headline") or e.get("title") or pid),
                                 entry=full, leaderboard=c.board(pid), page_uri=f"quantavane://collections/"
                                 f"{collection}/{pid}", check_with=how, data_as_of=bench.describe())

    @tool("run_claim_checks", "Run the claim pipeline's checks")
    async def run_claim_checks(
        problem_id: ProblemId,
        ctx: Context,
        certificate: Annotated[str | None, Field(max_length=MAX_INLINE_CHARS, description=(
            "The object's file text, in the problem's format. Give this or certificate_path, not both"))] = None,
        certificate_path: Annotated[str | None, Field(max_length=4096, description=(
            "Path of a local certificate file, inside the folders the server allows"))] = None,
        timeout_s: Annotated[int | None, Field(ge=1, le=86400, description=(
            "Wall-clock limit of each program run (default 600, or the problem's default if larger; at most "
            "QUANTAVANE_MCP_MAX_TIMEOUT_S). A large Ramsey colouring takes the second checker a few minutes"))] = None,
    ) -> ClaimResult:
        """Quantavane's claim pipeline on one object, offline: the benchmark's checker and a second checker written
        apart from it must both pass it with the same exact value, red controls (copies of the object broken so that
        they must fail) must be refused by both, and the value must strictly beat the keeper's value on file. Says
        RECORD, NOT-A-RECORD or NOT VERIFIED, with every check, the keeper's value and when it was read, the
        literature queries to run, and the pipeline's packet as text. A RECORD here still needs the keeper's page
        re-read the same day before it is sent (offline, the server cannot); nothing is written or sent."""
        limit = timeout_s or 600

        def job() -> tuple[ClaimResult | None, Exception | None]:
            try:
                data = checker.read_certificate(certificate, certificate_path)
                return run_claim(checker, problem_id, data, timeout_s), None
            except Exception as e:  # reported below as a tool error, never as a verdict
                return None, e
        result, error = await with_progress(ctx, limit, job)
        if isinstance(error, CheckError):
            raise _fail(error)
        if error is not None:
            what = f"{type(error).__name__}: {checker.clean(str(error))}"
            raise ToolError(f"Internal error ({what}); nothing was proved. Please report it with the problem id and "
                            "the certificate's size.")
        assert result is not None
        return result

    @tool("compare_to_record", "Compare a value with the best known")
    def compare_to_record(
        problem_id: ProblemId,
        value: Annotated[str, Field(min_length=1, max_length=4000, description=(
            "The value, exactly: an integer ('283'), a decimal ('0.41036') or a fraction ('54/125'). For Ramsey "
            "problems give n, the number of vertices of the colouring"))],
    ) -> CompareResult:
        """Is this value a new best for the problem? Compares it exactly with the best known value on the source page
        and with the verified values still in review, from the bundled data, and says when that value was read. It
        proves nothing about any object: check_candidate does that."""
        try:
            return checker.compare(problem_id, parse_value(value))
        except (CheckError, ValueError) as e:
            raise _fail(e) from None

    @tool("search_results", "Search Quantavane's verified results")
    def search_results(
        query: Annotated[str | None, Field(max_length=200, description="Words that must all appear (name, "
                                                                          "table, construction)")] = None,
        table: Annotated[str | None, Field(max_length=100, description=(
            "The table or area: spherical-codes, coverings (Covering Repository), covering-arrays (ca-tools), "
            "codes or quantum-codes (codetables.de), constant-weight (Brouwer), ramsey (Radziszowski), routing "
            "(CVRPLIB), scheduling, prime-gaps"))] = None,
        cell: Annotated[str | None, Field(max_length=100, description=(
            "One cell: CAN(t,k,v), C(v,k,t) or C(v,k,t,m), A(n,d,w), R(s,t), [n,k] over GF(q), [[n,k]]_q, "
            "d22-n119 (spherical code), 'gap 376428', or a name such as Leuven2"))] = None,
        date_from: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")] = None,
        date_to: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")] = None,
        date_field: Annotated[Literal["found", "status_date", "either"], Field(description=(
            "Which date the range applies to: when found, when listed or sent, or either"))] = "either",
        status: Annotated[Literal["listed", "sent", "queued"] | None, Field(description=(
            "listed: in the table (verified); sent: with the table's keeper; queued: in the next batch"))] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> SearchResult:
        """Search Quantavane's verified results (the open data, CC BY 4.0) by table, cell, words or date: each result
        with our value, the value before it, its status in the table, dates, the table and the certificate link, plus
        citation info. A covering array cell CAN(t,k,v) also returns the ca-tools entry where our family gives the
        smallest known size."""
        try:
            return search(store.open_data, query=query, table=table, cell=cell, date_from=date_from, date_to=date_to,
                          date_field=date_field, status=status, limit=limit, offset=offset)
        except SearchError as e:
            raise _fail(e) from None

    @tool("get_replay", "Get our replay of a certificate")
    def get_replay(
        pr: Annotated[int | None, Field(ge=1, le=100000, description=(
            "A pull request number of github.com/teorth/optimizationproblems, such as 292"))] = None,
        row: Annotated[str | None, Field(max_length=80, description=(
            "A row of a constant page: the constant and the row's reference key, such as '1c Kos2026' or "
            "'42a Gri26'"))] = None,
        constant: Annotated[str | None, Field(max_length=10, description="A constant page id, such as '42a' or "
                                                                            "'C68'")] = None,
        limit: Annotated[int, Field(ge=1, le=10)] = 3,
    ) -> ReplayResult:
        """Our independent exact replay of a certificate submitted to the optimization constants repository (by pull
        request, row or constant): what was checked and the exact values, the matching table rows, our checking
        programs, and the shell commands that re-derive it from scratch. Also the row's class in our asterisk index."""
        try:
            return find_replay(store.replays, pr=pr, row=row, constant=constant, limit=limit)
        except ReplayError as e:
            raise _fail(e) from None

    @tool("cite", "Cite")
    def cite_tool(
        target: Annotated[Literal["benchmark", "problem", "result", "dataset", "replay", "server"], Field(
            description="What to cite")],
        id: Annotated[str | None, Field(max_length=200, description=(
            "problem: a problem id; result: a slug from search_results; replay: a pull request number or a row "
            "such as '1c Kos2026'; not needed for benchmark, dataset or server"))] = None,
        format: Annotated[Literal["bibtex", "text", "both"], Field(description="Output format")] = "both",
    ) -> CitationResult:
        """BibTeX and plain citation text (and CITATION.cff for the benchmark, the dataset and this server) for a
        problem, a result, the benchmark, the open dataset, a replay or this server. Citing a problem also names the
        source of its best known value, which should be cited too."""
        try:
            return cite(store, target, id, format)
        except (CiteError, CheckError, ReplayError) as e:
            raise _fail(e) from None

    # ------------------------------------------------------------------------------------- the gym hook (opt-in)

    backend = gym.load_backend(settings.gym)
    if backend is not None:
        @tool("gym_environments", "List training-gym environments")
        def gym_environments() -> GymEnvironments:
            """The environments of the configured training gym, each around one of the benchmark's exact checkers."""
            return gym.environments(backend, settings.gym or "")

        @tool("gym_propose", "Propose an object to a gym environment")
        async def gym_propose(
            env_id: Annotated[str, Field(min_length=1, max_length=100, description="An id from gym_environments")],
            obj: Annotated[str, Field(min_length=1, max_length=gym.MAX_OBJECT_CHARS,
                                      description="The proposed object, in the environment's format")],
        ) -> GymVerdict:
            """Judge one proposed object with the gym's exact checker: the exact verdict and score."""
            try:
                return await anyio.to_thread.run_sync(
                    functools.partial(gym.propose, backend, env_id, obj, float(settings.max_timeout_s)))
            except gym.GymError as e:
                raise _fail(e) from None

    # ----------------------------------------------------------------------------------------------- resources

    @mcp.resource("quantavane://about", name="about", title="About this server and its data",
                  mime_type="application/json")
    def about() -> str:
        """Version, data sources with their commits and dates, counts, limits and how to update."""
        m = store.manifest
        return json.dumps({
            "server": {"name": "quantavane-mcp", "version": __version__},
            "network": "none: the server never opens a network connection",
            "benchmark": bench.describe(),
            "sources": m.sources,
            "counts": {"problems": bench.total_problems(), "single_problems": len(bench.problems),
                       "family_cells": sum(f["count"] for f in bench.families.values()),
                       "families": {n: f["count"] for n, f in bench.families.items()},
                       "results": len(store.open_data.records), "replay_sections": len(store.replays.sections),
                       "collections": {n: len(c.entries) for n, c in bench.collections.items()}},
            "claim_checks": {"second_checkers": second_kinds(),
                             "keeper": "the value on file (offline); re-read the keeper's page before sending a claim"},
            "limits": {"timeout_s": settings.timeout_s, "max_timeout_s": settings.max_timeout_s,
                       "memory_mb": settings.memory_mb, "memory_cap": sandbox.memory_cap_mode(),
                       "max_bytes": settings.max_bytes, "inline_chars": MAX_INLINE_CHARS,
                       "max_concurrent": settings.max_concurrent},
            "certificate_path_roots": [str(r) for r in settings.roots],
            "licence": "code, benchmark files and replay index MIT; Prestige 100 data and verified results CC BY 4.0 "
                       "(LICENSE-DATA.md)",
            "update": "uvx --refresh quantavane-mcp, or pip install -U quantavane-mcp",
            "benchmark_version": bench.meta.get("version"),
        }, indent=1)

    @mcp.resource("quantavane://benchmark/readme", name="benchmark-readme", title="Open Problems Benchmark README",
                  mime_type="text/markdown")
    def benchmark_readme() -> str:
        """The benchmark's README: the problems, the checkers and how to submit."""
        return (bench.root / "README.md").read_text("utf-8")

    @mcp.resource("quantavane://benchmark/changelog", name="benchmark-changelog",
                  title="Open Problems Benchmark changes", mime_type="text/markdown")
    def benchmark_changelog() -> str:
        """The benchmark's CHANGELOG: what each version added."""
        path = bench.root / "CHANGELOG.md"
        return path.read_text("utf-8") if path.is_file() else "No CHANGELOG.md in this benchmark copy.\n"

    @mcp.resource("quantavane://collections", name="collections", title="Collections of our own",
                  mime_type="text/markdown")
    def collections_index() -> str:
        """Prestige 100 and the Originals: what each holds and how to read them."""
        out = ["# Collections of our own", ""]
        for c in summaries():
            out.append(f"- **{c.name}** ({c.title}, {c.problems} problems): {c.about}. list_collection("
                       f"collection=\"{c.name}\"); README: quantavane://collections/{c.name}")
        return "\n".join(out) + "\n"

    @mcp.resource("quantavane://collections/{name}", name="collection-readme", title="Collection README",
                  mime_type="text/markdown")
    def collection_readme(name: str) -> str:
        """A collection's README."""
        c = bench.collections.get(name)
        if c is None:
            raise ValueError(f"No collection {name!r}; quantavane://collections lists them.")
        return c.readme

    @mcp.resource("quantavane://collections/{name}/{problem_id}", name="collection-page",
                  title="A collection problem's page", mime_type="text/markdown")
    def collection_page(name: str, problem_id: str) -> str:
        """The page of one problem of a collection (Markdown), by id or Prestige 100 slot."""
        c = bench.collections.get(name)
        page = c.page(problem_id) if c is not None else None
        if page is None:
            raise ValueError(f"No page {problem_id!r} in {name!r}; list_collection gives the ids.")
        return page

    @mcp.resource("quantavane://collections/{name}/refs/{filename}", name="collection-reference",
                  title="A collection's reference certificate", mime_type="text/plain")
    def collection_reference(name: str, filename: str) -> str:
        """One of a collection's reference certificates (the Originals: our first value's certificate)."""
        path = bench.reference_file(filename, collection=name)
        if path is None:
            raise ValueError(f"No reference certificate {filename!r} in {name!r}; get_problem lists each problem's.")
        return path.read_text("utf-8")

    @mcp.resource("quantavane://problems", name="problems", title="Problem index", mime_type="text/markdown")
    def problems_index() -> str:
        """Every single problem with its title and best known value, and each family with its number of cells."""
        lines = ["| id | title | objective | best known |", "| --- | --- | --- | --- |"]
        lines += [f"| {p.id} | {p.raw['title']} | {p.objective} | {p.best_known['value']} |"
                  for p in bench.problems.values()]
        lines += ["", "Families (their cells: list_problems with family=, or quantavane://families/NAME):", ""]
        lines += [f"- {name}: {fam['count']:,} cells ({fam['title']})" for name, fam in bench.families.items()]
        return "\n".join(lines) + "\n"

    @mcp.resource("quantavane://families", name="families", title="The problem families", mime_type="text/markdown")
    def families_index() -> str:
        """Each family: its cells, objective, checker, keeper and the date its table was read (obb.py families)."""
        out = ["# Problem families", ""]
        for name, fam in bench.families.items():
            out.append(f"- **{name}**: {fam['count']:,} cells, {fam['objective']}, checker "
                       f"{fam['checker']['program']}. {fam['keeper']}; read {fam['read']}; "
                       f"{fam.get('quantavane_records', 0)} held by Quantavane. "
                       f"Open cells: {fam.get('open_rule', '')}. Left out: {fam.get('left_out', '')}.")
        out.append("")
        out.append(f"{len(bench.families)} families, {sum(f['count'] for f in bench.families.values()):,} cells. "
                   "Only values are stored, with their sources; no keeper's file is included.")
        return "\n".join(out) + "\n"

    @mcp.resource("quantavane://families/{name}", name="family", title="Family definition",
                  mime_type="application/json")
    def family_file(name: str) -> str:
        """A family's definition (family.json): templates, checker, keeper, page, date read, open rule, left out."""
        fam = bench.families.get(name)
        if fam is None:
            raise ValueError(f"No family {name!r}; quantavane://families lists them.")
        return json.dumps(fam, indent=1, ensure_ascii=False)

    @mcp.resource("quantavane://problems/{problem_id}", name="problem", title="Problem file",
                  mime_type="application/json")
    def problem_file(problem_id: str) -> str:
        """The problem's JSON file as the benchmark publishes it."""
        try:
            return json.dumps(find_problem(bench, problem_id).raw, indent=1, ensure_ascii=False)
        except CheckError as e:
            raise ValueError(str(e)) from None

    def checker_files() -> list[Path]:
        """The benchmark's checkers, then the collections' own (collections/NAME/checkers/)."""
        files = sorted(f for f in bench.checkers_dir.iterdir() if f.suffix in (".py", ".c"))
        for c in bench.collections.values():
            d = c.root / "checkers"
            files += sorted(f for f in d.iterdir() if f.suffix == ".py") if d.is_dir() else []
        return files

    @mcp.resource("quantavane://checkers", name="checkers", title="The exact checkers", mime_type="text/markdown")
    def checkers_index() -> str:
        """The benchmark's checkers: what each checks and which problems use it."""
        users: dict[str, list[str]] = {}
        for p in list(bench.problems.values()) + list(bench.collection_problems.values()):
            users.setdefault(p.checker["program"].rsplit("/", 1)[-1], []).append(p.id)
        out = ["# The exact checkers", "",
               "Quantavane's own code (MIT), standard library only (the Ramsey checker is C). Each prints its exact "
               "result and exits 0 only for a valid certificate. Resources: quantavane://checkers/NAME (documentation) "
               "and quantavane://checkers/NAME/source.", ""]
        for f in checker_files():
            doc = checker_doc(f).split("\n\n")[0].replace("\n", " ")
            name = f.stem if f.suffix == ".c" else f.name
            used = users.get(name, [])
            where = "" if f.parent == bench.checkers_dir else f" ({f.parent.parent.name})"
            out.append(f"- **{f.name}**{where}: {doc[:300]}" + (f" Used by {len(used)} problem(s)." if used else ""))
        return "\n".join(out) + "\n"

    def checker_file(program: str) -> Path:
        name = program.rsplit("/", 1)[-1]
        name = name if name.endswith((".py", ".c")) else name + ".c"
        if re.fullmatch(r"[\w.\-]+", name):
            for f in checker_files():
                if f.name == name:
                    return f
        raise ValueError(f"No checker {program!r}; quantavane://checkers lists them.")

    @mcp.resource("quantavane://checkers/{program}", name="checker-docs", title="Checker documentation",
                  mime_type="text/markdown")
    def checker_docs(program: str) -> str:
        """A checker's documentation, its SHA-256 and the problems that use it."""
        path = checker_file(program)
        used = [p.id for p in list(bench.problems.values()) + list(bench.collection_problems.values())
                if p.checker["program"].rsplit("/", 1)[-1] in (path.name, path.stem)]
        return (f"# {path.name}\n\nSHA-256 {sha256_file(path)} ({bench.describe()})\n\n"
                f"Used by: {', '.join(used) if used else 'helper of another checker'}\n\n{checker_doc(path)}\n")

    @mcp.resource("quantavane://checkers/{program}/source", name="checker-source", title="Checker source",
                  mime_type="text/plain")
    def checker_source(program: str) -> str:
        """A checker's full source code."""
        return checker_file(program).read_text("utf-8")

    @mcp.resource("quantavane://refs/{filename}", name="reference-certificate", title="Reference certificate",
                  mime_type="text/plain")
    def reference_certificate(filename: str) -> str:
        """One of our reference certificates (get_problem lists them per problem)."""
        path = bench.reference_file(filename)
        if path is None:
            raise ValueError(f"No reference certificate {filename!r}; get_problem lists each problem's.")
        return path.read_text("utf-8")

    @mcp.resource("quantavane://open-data/readme", name="open-data-readme", title="Verified results: README",
                  mime_type="text/markdown")
    def open_data_readme() -> str:
        """The open dataset's README with its totals."""
        return store.open_data.readme + "\n\n## totals.json\n\n```json\n" + json.dumps(store.open_data.totals,
                                                                                       indent=1) + "\n```\n"

    # ----------------------------------------------------------------------------------------------- prompts

    @mcp.prompt(name="attack_problem", title="Attack an open problem")
    def attack_problem(problem_id: str) -> str:
        """Work on one open problem: its context, how to check candidates, and the honesty rules."""
        p = find_problem(bench, problem_id)
        refs = bench.references.get(p.id, [])
        vp = "; ".join(f"{v['value']} ({v['source']})" for v in p.verified_pending) or "none"
        uris = ", ".join("quantavane://refs/" + r.file for r in refs)
        ref_line = (f"Reference certificate (the best known entry): {uris}" if refs
                    else "No reference certificate is bundled.")
        read_ref = " and the reference certificate" if refs else ""
        return f"""You are working on the open problem {p.id}: {p.raw['title']}.

Statement: {p.raw['statement']}
Objective: {p.objective}. Best known: {p.best_known['value']} ({p.best_known['source']}; {p.as_of()}).
Verified values in review: {vp}.
Certificate format: {p.raw['submission']}
Checker: {p.checker['program']}; the score is {score_meaning(p)} ({EXACTNESS[p.kind]}).
{ref_line}

How to work:
1. Read the checker's documentation (quantavane://checkers/{p.checker['program']}){read_ref}.
2. {FAMILY_HINTS.get(p.family, '')}
3. Build candidates with your own code and write each one to a file.
4. Check every candidate with check_candidate(problem_id="{p.id}", certificate_path=...). Only verdict "certified"
   proves a value; "no_verdict" proves nothing.
5. A candidate improves the problem only when improves_page_best is true; say also whether it beats the values in
   review.
6. Report the exact value, the certificate's SHA-256 and the reproduce commands from the result. Never round a value
   in your favour, and never call a value a record unless check_candidate certified it and it improves the page best.
"""

    @mcp.prompt(name="verify_certificate", title="Verify a certificate")
    def verify_certificate(problem_id: str, certificate_path: str = "") -> str:
        """Check a certificate exactly and report the verdict with its evidence."""
        p = find_problem(bench, problem_id)
        where = f"the file {certificate_path}" if certificate_path else "the certificate I give you"
        arg = (f'certificate_path="{certificate_path}"' if certificate_path
               else "the certificate text (or a file path for a large one)")
        return f"""Verify {where} for the problem {p.id} ({p.raw['title']}).

1. Call get_problem("{p.id}") and confirm the certificate is in this format: {p.raw['submission']}
2. Call check_candidate with problem_id="{p.id}" and {arg}.
3. Report: the verdict, the exact value (value, and value_decimal for reading), each comparison (page best and values
   in review) with its exact threshold, the certificate's SHA-256, and the reproduce commands.
4. If the verdict is not_certified, quote the reason; if no_verdict, say which limit stopped it and that nothing was
   proved either way.
5. If it is certified and improves the page best, give cite(target="problem", id="{p.id}") and name the table's keeper
   from the problem's source as the place to report it.
"""

    @mcp.prompt(name="explain_replay", title="Explain a replay")
    def explain_replay(pr: str) -> str:
        """Explain our replay of a pull request in the optimization constants repository."""
        num = re.sub(r"\D", "", pr) or pr
        return f"""Explain Quantavane's replay of pull request #{num} of teorth/optimizationproblems.

1. Call get_replay(pr={num}).
2. Say what was replayed (the constant, the row, the certificate and its pinned commit), the exact values found and how
   they compare with the printed bounds, and what the replay does not check.
3. Give the re-derive commands exactly as the tool returns them, and cite it with cite(target="replay", id="{num}").
Quote every number exactly as the tool gives it.
"""

    @mcp.prompt(name="prepare_claim", title="Prepare a claim")
    def prepare_claim(problem_id: str, certificate_path: str = "") -> str:
        """Run the claim pipeline on an object and say what a claim still needs before it is sent."""
        p = find_problem(bench, problem_id)
        arg = f'certificate_path="{certificate_path}"' if certificate_path else "the certificate (a file path)"
        return f"""Prepare a claim for the problem {p.id} ({p.raw['title']}).

1. Call run_claim_checks with problem_id="{p.id}" and {arg}.
2. Report the verdict exactly (RECORD, NOT-A-RECORD or NOT VERIFIED), the exact value, the keeper's value on file and
   when it was read, and every check: the two checkers' values and each red control and whether it was refused.
3. If it is NOT VERIFIED, say which check failed or what is missing (a second checker, a red control).
4. If it is a RECORD: the keeper's page must be re-read today before anything is sent (the tool is offline); list the
   literature queries to run; name the keeper from keeper.name and keeper.url as the place to send it; and give
   cite(target="problem", id="{p.id}").
5. Never call it a record unless the verdict says RECORD, and never round a value in your favour.
"""

    @mcp.completion()
    async def complete(ref: Any, argument: Any, context: Any) -> Completion | None:
        name, prefix = getattr(argument, "name", ""), (getattr(argument, "value", "") or "").lower()
        if name == "problem_id":
            fam = bench.family_of(prefix)
            pool = list(bench.problems) + list(bench.collection_problems) + (list(bench.cells(fam)) if fam else [])
        elif name == "program":
            pool = sorted(f.name for f in checker_files())
        elif name == "filename":
            pool = sorted(r.file for rs in bench.references.values() for r in rs)
        elif name == "name":
            pool = list(bench.collections)
        else:
            return None
        hits = [x for x in pool if x.lower().startswith(prefix)]
        return Completion(values=hits[:100], total=len(hits), hasMore=len(hits) > 100)

    return mcp


# --------------------------------------------------------------------------------------------------- command line


def selftest(settings: Settings) -> int:
    """Check the bundled data against its manifest and run reference certificates through the sandboxed checkers."""
    store = Store(benchmark=Benchmark(settings.benchmark_dir))
    ok = True
    if store.benchmark.bundled:
        bad = store.manifest.verify()
        print(f"data: {len(store.manifest.files) - len(bad)}/{len(store.manifest.files)} files match MANIFEST.json"
              + (f"; differing: {', '.join(bad[:5])}" if bad else ""))
        ok &= not bad
    print(f"benchmark: {store.benchmark.describe()}; memory cap: {sandbox.memory_cap_mode() or 'not enforced'}")
    checker = Checker(store, settings)
    cases = [("covering-17-7-4-6", "ours_covering_17-7-4-6.txt"), ("cw-34-6-5", "ours_cw_34_6_5.txt"),
             ("sphere-d8-n119", "ours_sphere_d8_n119.txt"), ("16a-lower", "vid_c16_lower.json")]
    expected = {(r["problem"], r["file"]): r["expected"] for r in store.benchmark.meta.get("reference_expected", [])}
    for pid, fname in cases:
        path = store.benchmark.reference_file(fname)
        if path is None:
            print(f"  {pid}: reference {fname} missing")
            ok = False
            continue
        r = checker.check_data(pid, path.read_bytes())
        got = obb_verdicts(r)
        good = got == expected.get((pid, fname))
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {pid} {fname}: {r.verdict} {r.value or ''} {','.join(got)} "
              f"({r.checker.seconds:.1f} s)")
    pentagon = "".join("".join("1" if (j - i) % 5 in (1, 4) else "0" for j in range(5)) + "\n" for i in range(5))
    try:
        r = checker.check_data("ramsey-3-17", pentagon.encode())
        good = r.verdict == "certified" and r.value == "5"
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} ramsey-3-17 pentagon (C checker): {r.verdict} {r.value or ''}")
    except CheckError as e:
        print(f"  skip ramsey-3-17 (C checker): {e}")
    if "constant-weight-code" in store.benchmark.families:      # a family cell: A(8,6,4) >= 2, two disjoint words
        r = checker.check_data("cw-8-6-4", b"1 2 3 4\n5 6 7 8\n")
        good = r.verdict == "certified" and r.value == "2" and r.improves_page_best is False
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} cw-8-6-4 family cell: {r.verdict} {r.value or ''} "
              f"({store.benchmark.total_problems():,} problems in {len(store.benchmark.families)} families and "
              f"{len(store.benchmark.problems)} single problems)")
    originals = store.benchmark.collections.get("originals")
    if originals is not None and "qr-sumfree" in originals.problems:   # a collection problem and its own checker
        ref = store.benchmark.references["qr-sumfree"][0]
        r = checker.check_data("qr-sumfree", ref.path.read_bytes())
        good = r.verdict == "certified" and r.value == "174" and obb_verdicts(r) == ["does not improve"]
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} qr-sumfree (Originals, {len(originals.problems)} problems): "
              f"{r.verdict} {r.value or ''} {','.join(obb_verdicts(r))}")
    path = store.benchmark.reference_file("ours_covering_17-7-4-6.txt")
    if path is not None:                                                 # the claim pipeline, offline
        c = run_claim(checker, "covering-17-7-4-6", path.read_bytes())
        good = c.verified and not c.record and c.verdict.startswith("NOT-A-RECORD") and c.red_controls >= 1
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} claim checks on covering-17-7-4-6: {c.verdict.split(' (')[0]} "
              f"({sum(1 for x in c.checks if x.kind == 'check')} checkers, {c.red_controls} red control(s) refused)")
    print("selftest: " + ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quantavane-mcp", description="Quantavane MCP server (stdio). With no command "
                                 "it serves MCP over stdin and stdout.")
    ap.add_argument("--version", action="version", version=f"quantavane-mcp {__version__}")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("serve", help="serve MCP over stdio (the default)")
    sub.add_parser("selftest", help="check the bundled data and run reference certificates")
    pc = sub.add_parser("check", help="check one certificate file and print the result as JSON")
    pc.add_argument("problem_id")
    pc.add_argument("file")
    pc.add_argument("--timeout", type=int, default=None)
    pl = sub.add_parser("claim", help="run the claim pipeline's checks on one certificate file and print the result "
                                      "as JSON (exit 0 RECORD, 1 NOT-A-RECORD, 2 NOT VERIFIED or an error)")
    pl.add_argument("problem_id")
    pl.add_argument("file")
    pl.add_argument("--timeout", type=int, default=None)
    args = ap.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"quantavane-mcp: {e}", file=sys.stderr)
        return 2
    if args.command == "selftest":
        return selftest(settings)
    if args.command == "check":
        store = Store(benchmark=Benchmark(settings.benchmark_dir))
        try:
            data = Path(args.file).read_bytes()
            r = Checker(store, settings).check_data(args.problem_id, data, args.timeout)
        except (OSError, CheckError, DataError) as e:
            print(f"quantavane-mcp: {e}", file=sys.stderr)
            return 2
        print(r.model_dump_json(indent=1))
        return 0 if r.verdict == "certified" else 1 if r.verdict == "not_certified" else 2
    if args.command == "claim":
        store = Store(benchmark=Benchmark(settings.benchmark_dir))
        try:
            data = Path(args.file).read_bytes()
            c = run_claim(Checker(store, settings), args.problem_id, data, args.timeout)
        except (OSError, CheckError, DataError) as e:
            print(f"quantavane-mcp: {e}", file=sys.stderr)
            return 2
        print(c.model_dump_json(indent=1))
        return 0 if c.record else 1 if c.verified else 2
    try:
        server = build_server(settings)
    except (DataError, gym.GymError) as e:
        print(f"quantavane-mcp: {e}", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
