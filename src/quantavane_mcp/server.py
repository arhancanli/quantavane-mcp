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
from .config import ConfigError, Settings
from .data import Benchmark, DataError, Problem, Store, sha256_file
from .exact import parse_value
from .models import (
    BestKnown,
    CheckerInfo,
    CheckResult,
    CitationResult,
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
- list_problems / get_problem: 117 open problems (Tao's optimization constants, Ramsey lower bounds, spherical codes,
  covering designs, vehicle routing, constant weight codes) with the best known value, its source and when it was read.
- check_candidate: runs the benchmark's own checker on your certificate, sandboxed. Only verdict "certified" proves a
  value; a value counts as a new best only when improves_page_best is true. Put large certificates in a file and pass
  certificate_path.
- compare_to_record: is a value better than the best known? (Exact comparison; it proves nothing by itself.)
- search_results: Quantavane's verified results by table, cell or date. get_replay: our replay of a pull request in the
  optimization constants repository. cite: BibTeX and citation text.
Report values exactly as the tools give them; never round a bound in your favour."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
FamilyName = Literal["constant", "ramsey", "spherical-code", "covering-design", "vehicle-routing",
                     "constant-weight-code"]
ProblemId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]*$",
                                 description="A problem id from list_problems, such as '1c-lower', 'ramsey-5-15', "
                                             "'sphere-d3-n952', 'covering-17-7-4-6', 'cvrp-antwerp1' or 'cw-34-6-5'")]

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
        refs = [ReferenceCertificate(file=r.file, uri=f"quantavane://refs/{r.file}", description=r.description,
                                     expected=r.expected) for r in bench.references.get(p.id, [])]
        if p.objective == "maximize":
            rule = "a certified value larger than the best known one (exactly) improves the problem"
        else:
            rule = "a certified value smaller than the best known one (exactly) improves the problem"
        if not p.best_known.get("exact"):
            rule += ("; the best known value is known only as printed, so it must be beaten by more than one unit in "
                     "its last printed digit")
        return ProblemDetail(
            id=p.id, title=p.raw["title"], family=p.family, page=p.raw["page"], statement=p.raw["statement"],
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
            data_as_of=checker.data_as_of(p))

    # ----------------------------------------------------------------------------------------------- tools

    @tool("list_problems", "List open problems")
    def list_problems(
        family: Annotated[FamilyName | None, Field(description="Only this family")] = None,
        query: Annotated[str | None, Field(max_length=100, description=(
            "Words that must all appear in the id or title, such as 'R(5' or 'autocorrelation'"))] = None,
        limit: Annotated[int, Field(ge=1, le=200, description="Problems per page")] = 50,
        offset: Annotated[int, Field(ge=0, description="Index of the first problem to return")] = 0,
    ) -> ProblemList:
        """List the open problems of the Open Problems Benchmark (v1, 117 problems), one line each: id, title,
        family, objective, the best known value on its source page and the best verified value still in review.
        Use get_problem for the statement, the certificate format and the sources."""
        words = [w.lower() for w in (query or "").split()]
        rows = [p for p in bench.problems.values() if (family is None or p.family == family)
                and all(w in (p.id + " " + p.raw["title"]).lower() for w in words)]
        page = rows[offset:offset + limit]
        more = offset + len(page) < len(rows)
        counts: dict[str, int] = {}
        for p in bench.problems.values():
            counts[p.family] = counts.get(p.family, 0) + 1
        return ProblemList(total=len(rows), count=len(page), offset=offset, has_more=more,
                           next_offset=offset + len(page) if more else None, problems=[_summary(p) for p in page],
                           families=dict(sorted(counts.items())), data_as_of=bench.describe())

    @tool("get_problem", "Get one problem")
    def get_problem(problem_id: ProblemId) -> ProblemDetail:
        """Everything about one problem: the statement, the objective, the best known value with its source and when
        it was read, the verified values in review, the certificate format, the exact checker (and how to run it
        yourself), the improvement rule and our reference certificates (as resource URIs)."""
        try:
            return detail(find_problem(bench, problem_id))
        except CheckError as e:
            raise _fail(e) from None

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

        done = anyio.Event()

        async def tick() -> None:   # progress every 5 s, so clients that support it keep waiting
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
                result, error = await anyio.to_thread.run_sync(job)
            finally:
                done.set()
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
            "counts": {"problems": len(bench.problems), "results": len(store.open_data.records),
                       "replay_sections": len(store.replays.sections)},
            "limits": {"timeout_s": settings.timeout_s, "max_timeout_s": settings.max_timeout_s,
                       "memory_mb": settings.memory_mb, "memory_cap": sandbox.memory_cap_mode(),
                       "max_bytes": settings.max_bytes, "inline_chars": MAX_INLINE_CHARS,
                       "max_concurrent": settings.max_concurrent},
            "certificate_path_roots": [str(r) for r in settings.roots],
            "licence": "code, benchmark files and replay index MIT; verified results CC BY 4.0 (LICENSE-DATA.md)",
            "update": "uvx --refresh quantavane-mcp, or pip install -U quantavane-mcp",
        }, indent=1)

    @mcp.resource("quantavane://benchmark/readme", name="benchmark-readme", title="Open Problems Benchmark README",
                  mime_type="text/markdown")
    def benchmark_readme() -> str:
        """The benchmark's README: the problems, the checkers and how to submit."""
        return (bench.root / "README.md").read_text("utf-8")

    @mcp.resource("quantavane://problems", name="problems", title="Problem index", mime_type="text/markdown")
    def problems_index() -> str:
        """Every problem id with its title and best known value."""
        lines = ["| id | title | objective | best known |", "| --- | --- | --- | --- |"]
        lines += [f"| {p.id} | {p.raw['title']} | {p.objective} | {p.best_known['value']} |"
                  for p in bench.problems.values()]
        return "\n".join(lines) + "\n"

    @mcp.resource("quantavane://problems/{problem_id}", name="problem", title="Problem file",
                  mime_type="application/json")
    def problem_file(problem_id: str) -> str:
        """The problem's JSON file as the benchmark publishes it."""
        try:
            return json.dumps(find_problem(bench, problem_id).raw, indent=1, ensure_ascii=False)
        except CheckError as e:
            raise ValueError(str(e)) from None

    @mcp.resource("quantavane://checkers", name="checkers", title="The exact checkers", mime_type="text/markdown")
    def checkers_index() -> str:
        """The benchmark's checkers: what each checks and which problems use it."""
        users: dict[str, list[str]] = {}
        for p in bench.problems.values():
            users.setdefault(p.checker["program"], []).append(p.id)
        out = ["# The exact checkers", "",
               "Quantavane's own code (MIT), standard library only (the Ramsey checker is C). Each prints its exact "
               "result and exits 0 only for a valid certificate. Resources: quantavane://checkers/NAME (documentation) "
               "and quantavane://checkers/NAME/source.", ""]
        for f in sorted(bench.checkers_dir.iterdir()):
            if f.suffix in (".py", ".c"):
                doc = checker_doc(f).split("\n\n")[0].replace("\n", " ")
                name = f.stem if f.suffix == ".c" else f.name
                used = users.get(name, [])
                out.append(f"- **{f.name}**: {doc[:300]}" + (f" Used by {len(used)} problem(s)." if used else ""))
        return "\n".join(out) + "\n"

    def checker_file(program: str) -> Path:
        name = program if program.endswith((".py", ".c")) else program + ".c"
        path = bench.checkers_dir / name
        if not re.fullmatch(r"[\w.\-]+", name) or not path.is_file():
            raise ValueError(f"No checker {program!r}; quantavane://checkers lists them.")
        return path

    @mcp.resource("quantavane://checkers/{program}", name="checker-docs", title="Checker documentation",
                  mime_type="text/markdown")
    def checker_docs(program: str) -> str:
        """A checker's documentation, its SHA-256 and the problems that use it."""
        path = checker_file(program)
        used = [p.id for p in bench.problems.values()
                if p.checker["program"] in (path.name, path.stem)]
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

    @mcp.completion()
    async def complete(ref: Any, argument: Any, context: Any) -> Completion | None:
        name, prefix = getattr(argument, "name", ""), (getattr(argument, "value", "") or "").lower()
        if name == "problem_id":
            pool = list(bench.problems)
        elif name == "program":
            pool = sorted(f.name for f in bench.checkers_dir.iterdir() if f.suffix in (".py", ".c"))
        elif name == "filename":
            pool = sorted(r.file for rs in bench.references.values() for r in rs)
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
    try:
        server = build_server(settings)
    except (DataError, gym.GymError) as e:
        print(f"quantavane-mcp: {e}", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
