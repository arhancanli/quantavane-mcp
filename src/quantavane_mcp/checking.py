"""check_candidate and compare_to_record: the public benchmark's own checkers, run in the sandbox and read exactly as
the benchmark's obb.py reads them, so a verdict here is the verdict there."""
from __future__ import annotations

import difflib
import hashlib
import os
import platform
import re
import shutil
import sys
import tempfile
import threading
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import sandbox
from .config import Settings
from .data import Benchmark, Problem, Store, sha256_file
from .exact import better, decimal_text, fraction_text, threshold
from .models import CheckerRun, CheckResult, CompareResult, Comparison, LimitsInfo, ReferenceValue

MAX_INLINE_CHARS = 4_000_000
RAMSEY_MAXV = 2048                  # MAXV in ramsey_check.c
RAMSEY_FGETS = RAMSEY_MAXV + 8 - 1  # characters one fgets call reads into its row buffer
PYTHON_FLAGS = ["-I", "-B", "-X", "utf8", "-X", "int_max_str_digits=0"]

EXACTNESS = {
    "bound": "exact rational (big-integer arithmetic)",
    "c68": "exact rational: the bound whose hypotheses the checker proves",
    "c42": "exact rational: the bound the checker proves in outward-rounded interval arithmetic",
    "c59": "exact rational: the radius r for which the checker proves K_2 < r",
    "c16": "decimal: the lower end of a rigorous enclosure",
    "ramsey": "integer: the number of vertices n",
    "spherical": "decimal: the largest cosine, computed in 50-digit arithmetic and printed to 20 decimals",
    "blocks": "integer: the number of blocks",
    "cvrp": "integer: the total cost, every distance rounded exactly in integers",
    "words": "integer: the number of code words",
}


class CheckError(Exception):
    """A request the caller can fix: the message says how."""


def big_int(text: str) -> int:
    """int(text) without Python's limit on long decimal strings (exact)."""
    return int(Decimal(text))


def value_from_output(kind: str, exit_code: int | None, stdout: str, stderr: str) -> Fraction | None:
    """The exact value a checker proved, read as obb.py's run_checker reads it; None when nothing was proved."""
    if kind == "ramsey":
        m = re.search(r"^n (\d+) red_K\d+ none blue_K\d+ none", stdout, re.M)
        return Fraction(big_int(m.group(1))) if exit_code == 0 and m else None
    text = stdout + stderr
    if exit_code != 0:
        return None
    fraction_patterns = {
        "bound": r"bound = (\d+)/(\d+)",
        "c68": r"RESULT C68 >= (\d+)/(\d+) = \S+: all hypotheses hold",
        "c42": r"RESULT C42 <= (\d+)/(\d+): PASS",
        "c59": r"RESULT K_2 < (\d+)/(\d+): PASS",
    }
    if kind in fraction_patterns:
        m = re.search(fraction_patterns[kind], text)
        return Fraction(big_int(m.group(1)), big_int(m.group(2))) if m else None
    if kind == "spherical":
        m = re.search(r"max_cos (-?\d+\.\d+)", text)
        return Fraction(m.group(1)) if m else None
    if kind == "c16":
        m = re.search(r"RESULT C16 >= (\d+\.\d+)", text)
        return Fraction(m.group(1)) if m else None
    integer_patterns = {"blocks": r"^blocks (\d+)$", "cvrp": r"^cost (\d+)$", "words": r"^words (\d+)$"}
    if kind in integer_patterns:
        m = re.search(integer_patterns[kind], text, re.M)
        return Fraction(big_int(m.group(1))) if m else None
    raise ValueError("unknown value kind " + kind)


def ramsey_precheck(data: bytes) -> str | None:
    """Reject, without running it, a matrix whose rows ramsey_check.c could not hold: a run of more than 2048 0/1
    characters in what one fgets call reads. No valid certificate has one (n <= 2048), and the C checker would reject
    the file anyway, after writing past its matrix for widths 2049 to 2055."""
    pieces = data.split(b"\n")
    for i, piece in enumerate(pieces):
        line = piece + (b"\n" if i < len(pieces) - 1 else b"")
        for start in range(0, max(len(line), 1), RAMSEY_FGETS):
            chunk = line[start:start + RAMSEY_FGETS]
            run = len(chunk) - len(chunk.lstrip(b"01"))
            if run > RAMSEY_MAXV:
                return (f"line {i + 1} has a row of {run} 0/1 characters; the checker reads at most {RAMSEY_MAXV} "
                        "vertices (n <= 2048), so this is not a valid colouring")
    return None


def score_meaning(p: Problem) -> str:
    args = p.checker["args"]
    if p.kind == "ramsey":
        s, t = args
        return (f"n, the size of a two-colouring of K_n with no red K_{s} and no blue K_{t}; it proves "
                f"R({s},{t}) >= n + 1 (larger is better)")
    if p.kind == "spherical":
        d, n = args
        return f"the largest cosine between two of the {n} points on the sphere in R^{d} (smaller is better)"
    if p.kind == "blocks":
        return "the number of blocks of a valid covering design (fewer is better)"
    if p.kind == "cvrp":
        return "the total length of the routes, depot to depot (smaller is better)"
    if p.kind == "words":
        return "the number of words of a valid constant weight code (more is better)"
    side = "lower" if p.objective == "maximize" else "upper"
    return f"a certified {side} bound: {p.raw['title']}"


def standalone_command(p: Problem) -> str:
    c = p.checker
    if p.kind == "ramsey":
        return f"cc -O3 -o ramsey_check checkers/ramsey_check.c && ./ramsey_check {' '.join(c['args'])} FILE"
    if p.kind == "spherical":
        return f"python3 -I checkers/{c['program']} FILE {' '.join(c['args'])}"
    return " ".join(["python3 -I", f"checkers/{c['program']}", *c["args"], "FILE"])


def find_problem(bench: Benchmark, problem_id: str) -> Problem:
    p = bench.problems.get(problem_id.strip())
    if p is None:
        close = difflib.get_close_matches(problem_id.strip().lower(), list(bench.problems), n=5, cutoff=0.6)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise CheckError(f"Unknown problem {problem_id!r}.{hint} list_problems gives every id.")
    return p


def comparisons_for(p: Problem, value: Fraction) -> list[Comparison]:
    out = [Comparison(reference="page best", value=p.best_known["value"],
                      threshold=fraction_text(threshold(p.objective, p.best_known)), source=p.best_known["source"],
                      improves=better(p.objective, value, threshold(p.objective, p.best_known)))]
    for v in p.verified_pending:
        t = threshold(p.objective, v)
        out.append(Comparison(reference="verified in review", value=v["value"], threshold=fraction_text(t),
                              source=v["source"], improves=better(p.objective, value, t)))
    return out


def obb_verdicts(result: CheckResult) -> list[str]:
    """The verdicts obb.py prints for the same check (page best, then each verified value in review), as test.sh
    lists them: IMPROVES, does not improve, or NOT CERTIFIED."""
    if result.verdict != "certified":
        return ["NOT CERTIFIED"] if result.verdict == "not_certified" else ["NO VERDICT"]
    return ["IMPROVES" if c.improves else "does not improve" for c in result.comparisons]


def _verified_flag(comps: list[Comparison]) -> bool | None:
    verified = [c for c in comps if c.reference == "verified in review"]
    return all(c.improves for c in verified) if verified else None


def _last_line(text: str) -> str:
    lines = [x.strip() for x in text.strip().splitlines() if x.strip()]
    return lines[-1] if lines else ""


class Checker:
    """Runs the benchmark's checkers for the server; thread-safe."""

    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        self._slots = threading.BoundedSemaphore(settings.max_concurrent)
        self._compile_lock = threading.Lock()
        self._instance_ok: dict[tuple[str, int, float], str] = {}

    @property
    def bench(self) -> Benchmark:
        return self.store.benchmark

    # ------------------------------------------------------------------------------------------- inputs

    def read_certificate(self, certificate: str | None, certificate_path: str | None) -> bytes:
        if (certificate is None) == (certificate_path is None):
            raise CheckError("Give exactly one of certificate (the file's text) or certificate_path (a local file).")
        if certificate is not None:
            if len(certificate) > MAX_INLINE_CHARS:
                raise CheckError(f"The certificate text has {len(certificate):,} characters; inline certificates "
                                 f"are limited to {MAX_INLINE_CHARS:,}. Write it to a file and pass certificate_path.")
            data = certificate.encode("utf-8")
        else:
            assert certificate_path is not None
            path = self.allowed_path(certificate_path)
            with open(path, "rb") as f:
                data = f.read(self.settings.max_bytes + 1)
        if len(data) > self.settings.max_bytes:
            raise CheckError(f"The certificate is larger than {self.settings.max_bytes:,} bytes "
                             "(QUANTAVANE_MCP_MAX_BYTES).")
        if not data.strip():
            raise CheckError("The certificate is empty.")
        return data

    def allowed_path(self, raw: str) -> Path:
        roots = self.settings.roots
        try:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            path = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise CheckError(f"No such file: {raw}") from None
        inside = [r for r in roots if path == r or r in path.parents]
        if not inside:
            where = ", ".join(str(r) for r in roots) or "(none)"
            raise CheckError(f"certificate_path must be inside an allowed folder: {where}. Set QUANTAVANE_MCP_ROOTS "
                             "(folders separated by the path separator) in the server's environment to allow others.")
        rel = path.relative_to(inside[0])
        if any(part.startswith(".") for part in rel.parts):
            raise CheckError("Hidden files and folders (names starting with '.') are not read.")
        if not path.is_file():
            raise CheckError(f"Not a regular file: {raw}")
        if path.stat().st_size > self.settings.max_bytes:
            raise CheckError(f"{raw} is larger than {self.settings.max_bytes:,} bytes (QUANTAVANE_MCP_MAX_BYTES).")
        return path

    # ------------------------------------------------------------------------------------------- programs

    def verify_checkers(self) -> None:
        """The bundled checkers must be byte for byte those of the benchmark commit in the manifest."""
        if not self.bench.bundled:
            return
        bad = self.store.manifest.verify(self.bench.data_dir, only="benchmark/checkers/")
        if bad:
            raise CheckError("The bundled checkers differ from the benchmark release (" + ", ".join(bad) +
                             "); reinstall quantavane-mcp.")

    def ramsey_binary(self) -> Path:
        src = self.bench.checkers_dir / "ramsey_check.c"
        exe = self.settings.cache_dir / f"ramsey_check-{sha256_file(src)[:16]}-{platform.machine() or 'cpu'}"
        if exe.is_file():
            return exe
        with self._compile_lock:
            if exe.is_file():
                return exe
            cc = self.settings.cc
            cc = shutil.which(cc) if cc else (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang"))
            if not cc:
                raise CheckError("The Ramsey checker is C and needs a C compiler: install one (macOS: xcode-select "
                                 "--install; Debian or Ubuntu: apt install gcc), or set QUANTAVANE_MCP_CC.")
            self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = exe.with_name(f"{exe.name}.tmp{os.getpid()}")
            env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "DEVELOPER_DIR", "SDKROOT") if k in os.environ}
            r = sandbox.run([cc, "-O3", "-o", str(tmp), str(src)], cwd=self.settings.cache_dir, env=env,
                            limits=sandbox.Limits(timeout_s=300, memory_mb=max(self.settings.memory_mb, 1024),
                                                  fsize_bytes=64 * 2**20, nofile=256),
                            allow_uncapped=self.settings.allow_uncapped)
            if r.exit_code != 0 or not tmp.is_file():
                tmp.unlink(missing_ok=True)
                raise CheckError("Compiling ramsey_check.c failed: " + self.clean(_last_line(r.stderr + r.stdout)))
            os.chmod(tmp, 0o755)
            os.replace(tmp, exe)
        return exe

    def instance(self, arg: str) -> Path:
        """A CVRPLIB instance named by a checker argument (instances/NAME.vrp), from QUANTAVANE_MCP_INSTANCES or a
        local benchmark checkout, verified against the SHA-256 that fetch.sh pins. The server never downloads it."""
        name = Path(arg).name
        info = self.bench.meta.get("cvrplib_instances", {}).get(name)
        candidates = []
        if self.settings.instances_dir:
            candidates.append(self.settings.instances_dir / name)
        if not self.bench.bundled:
            candidates.append(self.bench.root / arg)
        for c in candidates:
            if c.is_file():
                st = c.stat()
                key = (str(c), st.st_size, st.st_mtime)
                digest = self._instance_ok.get(key) or sha256_file(c)
                if info and digest != info["sha256"]:
                    raise CheckError(f"{name} in {c.parent} does not match the SHA-256 pinned by the benchmark "
                                     f"({info['sha256'][:12]}...); fetch CVRPLIB's file again.")
                self._instance_ok[key] = digest
                return c
        url = f" from {info['url']}" if info else ""
        raise CheckError(f"This routing problem needs the CVRPLIB instance {name}, which is not bundled (third-party "
                         f"data) and is never downloaded by the server. Get it{url} (or run fetch.sh in a clone of "
                         "github.com/arhancanli/quantavane-benchmark), then set QUANTAVANE_MCP_INSTANCES to the folder "
                         "that holds it.")

    def instance_status(self, p: Problem) -> dict[str, str] | None:
        if p.kind != "cvrp":
            return None
        name = Path(p.checker["args"][0]).name
        info = self.bench.meta.get("cvrplib_instances", {}).get(name, {})
        try:
            where = str(self.instance(p.checker["args"][0]).parent)
        except CheckError:
            where = "not available: set QUANTAVANE_MCP_INSTANCES to a folder holding it"
        return {"file": name, "sha256": info.get("sha256", ""), "url": info.get("url", ""), "found": where}

    def argv(self, p: Problem, candidate: Path) -> list[str]:
        """The command obb.py runs for this problem (Python flags: isolated, no bytecode, UTF-8, no digit limit)."""
        c = p.checker
        args = [str(self.instance(a)) if a.startswith("instances/") else a for a in c["args"]]
        if p.kind == "ramsey":
            return [str(self.ramsey_binary()), *args, str(candidate)]
        program = str(self.bench.checkers_dir / c["program"])
        if p.kind == "spherical":
            return [sys.executable, *PYTHON_FLAGS, program, str(candidate), *args]
        return [sys.executable, *PYTHON_FLAGS, program, *args, str(candidate)]

    def clean(self, text: str, *extra: tuple[str, str]) -> str:
        """Remove local paths from checker output."""
        pairs = list(extra) + [(str(self.bench.checkers_dir), "checkers"), (str(self.settings.cache_dir), "<cache>"),
                               (str(Path.home()), "~")]
        for old, new in pairs:
            if old:
                text = text.replace(old, new)
        return text

    # ------------------------------------------------------------------------------------------- the check

    def limits_info(self, timeout_s: int) -> LimitsInfo:
        return LimitsInfo(timeout_s=timeout_s, memory_mb=self.settings.memory_mb,
                          memory_cap=sandbox.memory_cap_mode() or "not enforced on this platform",
                          max_bytes=self.settings.max_bytes)

    def data_as_of(self, p: Problem) -> str:
        return f"{self.bench.describe()}; best known value {p.as_of()}"

    def reproduce(self, p: Problem, digest: str) -> str:
        commit = (self.bench.meta.get("commit") or "")[:7]
        lines = ["git clone https://github.com/arhancanli/quantavane-benchmark && cd quantavane-benchmark"
                 + (f" && git checkout {commit}" if commit else "")]
        if p.kind == "cvrp":
            lines.append("./fetch.sh   # CVRPLIB instances, each checked against its SHA-256")
        lines.append(f"python3 -I obb.py check {p.id} CANDIDATE   # the file with SHA-256 {digest}")
        return "\n".join(lines)

    def check(self, problem_id: str, certificate: str | None = None, certificate_path: str | None = None,
              timeout_s: int | None = None) -> CheckResult:
        """Check a certificate given as text or as a path inside the allowed folders."""
        find_problem(self.bench, problem_id)
        return self.check_data(problem_id, self.read_certificate(certificate, certificate_path), timeout_s)

    def check_data(self, problem_id: str, data: bytes, timeout_s: int | None = None) -> CheckResult:
        """Check a certificate given as bytes (the command line and the gym hook use this directly)."""
        p = find_problem(self.bench, problem_id)
        timeout = self.settings.timeout_s if timeout_s is None else timeout_s
        if not 1 <= timeout <= self.settings.max_timeout_s:
            raise CheckError(f"timeout_s must be between 1 and {self.settings.max_timeout_s}.")
        if len(data) > self.settings.max_bytes:
            raise CheckError(f"The certificate is larger than {self.settings.max_bytes:,} bytes "
                             "(QUANTAVANE_MCP_MAX_BYTES).")
        digest = hashlib.sha256(data).hexdigest()
        base: dict[str, Any] = dict(
            problem_id=p.id, objective=p.objective, exactness=EXACTNESS[p.kind], score_meaning=score_meaning(p),
            certificate_sha256=digest, certificate_bytes=len(data), limits=self.limits_info(timeout),
            reproduce=self.reproduce(p, digest), data_as_of=self.data_as_of(p))
        program = p.checker["program"]
        if p.kind == "ramsey":
            why = ramsey_precheck(data)
            if why:
                return CheckResult(verdict="not_certified", reason=why, comparisons=[],
                                   checker=CheckerRun(program=program, exit_code=None, seconds=0.0,
                                                      output_tail="(not run: rejected before the check)"), **base)
        self.verify_checkers()
        if not self._slots.acquire(timeout=timeout):
            raise CheckError("Every check slot stayed busy for the whole timeout; try again "
                             "(QUANTAVANE_MCP_MAX_CONCURRENT sets the number of slots).")
        try:
            workdir = tempfile.mkdtemp(prefix="quantavane-check-")
            try:
                suffix = ".json" if p.raw["submission"].lstrip().upper().startswith("JSON") else \
                    ".sol" if p.kind == "cvrp" else ".txt"
                candidate = Path(workdir) / f"candidate{suffix}"
                candidate.write_bytes(data)
                argv = self.argv(p, candidate)
                run = sandbox.run(argv, cwd=workdir, limits=sandbox.Limits(timeout_s=timeout,
                                                                           memory_mb=self.settings.memory_mb),
                                  allow_uncapped=self.settings.allow_uncapped)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        except sandbox.SandboxUnavailable as e:
            raise CheckError(str(e)) from None
        finally:
            self._slots.release()
        swaps = ((str(candidate), "<candidate>"), (workdir, "<workdir>"))
        out = self.clean(run.stdout, *swaps)
        err = self.clean(run.stderr, *swaps)
        tail_lines = (out + ("\n" if out and err else "") + err).strip().splitlines()[-12:]
        tail = "\n".join(tail_lines)[-1500:]
        checker_run = CheckerRun(program=program, exit_code=run.exit_code, seconds=run.seconds,
                                 peak_memory_mb=run.peak_memory_mb, output_tail=tail)
        if run.limit_hit:
            reason = {
                "timeout": f"stopped at the {timeout} s timeout; nothing was proved (raise timeout_s, up to "
                           f"{self.settings.max_timeout_s}, or run the checker yourself: see reproduce)",
                "memory": f"stopped at the {self.settings.memory_mb} MB memory cap; nothing was proved "
                          "(QUANTAVANE_MCP_MEMORY_MB raises it)",
                "cpu-time": "stopped at the CPU-time limit; nothing was proved",
                "sandbox": f"the sandbox could not be set up: {run.sandbox_error}",
            }[run.limit_hit]
            return CheckResult(verdict="no_verdict", reason=reason, comparisons=[], checker=checker_run, **base)
        value = value_from_output(p.kind, run.exit_code, run.stdout, run.stderr)
        if value is None:
            return CheckResult(verdict="not_certified", reason=self.failure_reason(p, run.exit_code, out, err),
                               comparisons=[], checker=checker_run, **base)
        comps = comparisons_for(p, value)
        return CheckResult(verdict="certified", value=fraction_text(value), value_decimal=decimal_text(value),
                           improves_page_best=comps[0].improves, improves_verified_in_review=_verified_flag(comps),
                           comparisons=comps, checker=checker_run, **base)

    @staticmethod
    def failure_reason(p: Problem, exit_code: int | None, out: str, err: str) -> str:
        if p.kind == "ramsey":
            m = re.search(r"red_K(\d+) (none|found) blue_K(\d+) (none|found)", out)
            if exit_code == 1 and m:
                found = [f"a red K_{m.group(1)}" if m.group(2) == "found" else "",
                         f"a blue K_{m.group(3)}" if m.group(4) == "found" else ""]
                cliques = re.findall(r"^(red|blue): ([\d ]+)$", out, re.M)
                verts = "; ".join(f"{c} vertices {v.strip()}" for c, v in cliques)[:300]
                where = f" ({verts})" if verts else ""
                return "the colouring contains " + " and ".join(x for x in found if x) + where
            return "the file is not a valid matrix: " + (_last_line(err) or _last_line(out) or f"exit {exit_code}")
        line = _last_line(err) if exit_code != 0 and err.strip() else _last_line(out) or _last_line(err)
        if exit_code == 0:
            return "the checker finished without proving a value: " + (line or "no result line")[:400]
        return (line or f"the checker exited with status {exit_code}")[:400]

    # ------------------------------------------------------------------------------------------- compare

    def compare(self, problem_id: str, value: Fraction) -> CompareResult:
        p = find_problem(self.bench, problem_id)
        comps = comparisons_for(p, value)
        if p.kind == "ramsey":
            s, t = p.checker["args"]
            note = (f"For Ramsey problems the value is n, the number of vertices of the colouring: a colouring of K_n "
                    f"proves R({s},{t}) >= n + 1. ")
        else:
            note = ""
        note += ("A value is not a result: only check_candidate on its certificate proves it. Values are compared "
                 "exactly; a printed value whose exact original is unknown counts only when beaten by more than its "
                 "last printed digit.")
        return CompareResult(
            problem_id=p.id, objective=p.objective, value=fraction_text(value), value_decimal=decimal_text(value),
            improves_page_best=comps[0].improves, improves_verified_in_review=_verified_flag(comps), comparisons=comps,
            claimed_not_replayed=[ReferenceValue(value=c["value"], exact=c.get("exact"), source=c["source"])
                                  for c in p.claimed_pending],
            best_known_read=p.as_of(), note=note, data_as_of=self.data_as_of(p))
