"""The data bundled with the server (or a local benchmark checkout), loaded lazily and checked against MANIFEST.json."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
import re
import subprocess
import threading
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, cast

DATA_DIR = Path(__file__).resolve().parent / "data"

# checker value kind -> problem family
FAMILIES = {
    "bound": "constant", "c68": "constant", "c42": "constant", "c59": "constant", "c16": "constant",
    "ramsey": "ramsey", "spherical": "spherical-code", "blocks": "covering-design", "cvrp": "vehicle-routing",
    "words": "constant-weight-code", "result": "other",
}
FAMILY_NAMES = sorted(set(FAMILIES.values()))

_READ_DATE = re.compile(r"read (\d{1,2} [A-Z][a-z]+ \d{4}(?: \d{1,2}:\d{2} UTC)?|\d{4}-\d{2}-\d{2})")
_PAGE_COMMIT = re.compile(r"\(main ([0-9a-f]{7,40})\)")


class DataError(RuntimeError):
    """The bundled data is missing or does not match its manifest."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class Manifest:
    sources: dict[str, Any]
    files: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> Manifest:
        path = data_dir / "MANIFEST.json"
        if not path.is_file():
            raise DataError(f"{path} is missing: the package data is incomplete; reinstall quantavane-mcp")
        d = json.loads(path.read_text("utf-8"))
        return cls(sources=d["sources"], files=d["files"])

    def verify(self, data_dir: Path = DATA_DIR, only: str | None = None) -> list[str]:
        """Files whose SHA-256 differs from the manifest (or that are missing); [] when all match."""
        bad = []
        for rel, info in self.files.items():
            if only and not rel.startswith(only):
                continue
            p = data_dir / rel
            if not p.is_file() or sha256_file(p) != info["sha256"]:
                bad.append(rel)
        return bad


@dataclass(frozen=True)
class Reference:
    file: str
    path: Path
    expected: list[str]
    ours: bool

    @property
    def description(self) -> str:
        if self.ours:
            return ("Quantavane's own result, the best known entry of its source table when the problem file was "
                    "written")
        if self.file.startswith("classic_"):
            return ("a classical construction built by Quantavane's code (credited in its first line and in the "
                    "problem file); it shows the format and exercises the checker")
        return "a parameter file describing another author's construction (see the problem's sources)"


@dataclass(frozen=True)
class Problem:
    raw: dict[str, Any]
    file_date: str | None

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def objective(self) -> Literal["maximize", "minimize"]:
        return cast(Literal["maximize", "minimize"], self.raw["objective"])

    @property
    def checker(self) -> dict[str, Any]:
        return self.raw["checker"]

    @property
    def kind(self) -> str:
        return self.raw["checker"]["value"]

    @property
    def family(self) -> str:
        return str(self.raw.get("family") or FAMILIES.get(self.kind, "other"))

    @property
    def best_known(self) -> dict[str, Any]:
        return self.raw["best_known"]

    @property
    def verified_pending(self) -> list[dict[str, Any]]:
        return self.raw.get("verified_pending") or []

    @property
    def claimed_pending(self) -> list[dict[str, Any]]:
        return self.raw.get("claimed_pending") or []

    def read_date(self) -> str | None:
        m = _READ_DATE.search(self.best_known.get("source", ""))
        return m.group(1) if m else None

    def page_commit(self) -> str | None:
        m = _PAGE_COMMIT.search(self.best_known.get("source", ""))
        return m.group(1) if m else None

    def as_of(self) -> str:
        """When the best known value was read: the date the source states, else the page commit it names, plus the
        date the problem file was written."""
        parts = []
        if self.read_date():
            parts.append(f"read {self.read_date()}")
        elif self.page_commit():
            parts.append(f"as on the page at main {self.page_commit()}")
        if self.file_date:
            parts.append(f"problem file of {self.file_date}")
        return "; ".join(parts) or "date not stated"


def _parse_fetch_sh(text: str) -> dict[str, dict[str, str]]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^slow (\S+\.vrp) (\S+) ([0-9a-f]{64})$", line.strip())
        if m:
            out[m.group(1)] = {"url": m.group(2), "sha256": m.group(3)}
    return out


def _parse_test_sh(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ours: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = re.match(r'^t (\S+) (\S+) "([^"]*)"$', line.strip())
        if m:
            row = {"problem": m.group(1), "file": Path(m.group(2)).name,
                   "expected": [v for v in m.group(3).split(",") if v]}
            (ours if m.group(2).startswith("refs/") else others).append(row)
    return ours, others


class Benchmark:
    """The Open Problems Benchmark: the bundled copy (default) or a local checkout (QUANTAVANE_MCP_BENCHMARK_DIR)."""

    def __init__(self, root: Path | None = None, data_dir: Path = DATA_DIR):
        self.bundled = root is None
        self.data_dir = data_dir
        self.root = (data_dir / "benchmark") if root is None else Path(root).resolve()
        if not (self.root / "problems").is_dir():
            raise DataError(f"no problems/ folder in {self.root}")

    @cached_property
    def meta(self) -> dict[str, Any]:
        if self.bundled:
            return json.loads((self.root / "meta.json").read_text("utf-8"))
        meta: dict[str, Any] = {"repository": str(self.root), "commit": None, "commit_date": None,
                                "problem_file_dates": {}, "cvrplib_instances": {}, "reference_expected": [],
                                "external_expected": []}
        try:
            meta["commit"] = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True,
                                            text=True, timeout=10, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        if (self.root / "fetch.sh").is_file():
            meta["cvrplib_instances"] = _parse_fetch_sh((self.root / "fetch.sh").read_text("utf-8"))
        else:  # fall back on the hashes bundled with the server
            meta["cvrplib_instances"] = json.loads(
                (self.data_dir / "benchmark" / "meta.json").read_text("utf-8"))["cvrplib_instances"]
        if (self.root / "test.sh").is_file():
            meta["reference_expected"], meta["external_expected"] = _parse_test_sh(
                (self.root / "test.sh").read_text("utf-8"))
        version = self.root / "VERSION"
        meta["version"] = version.read_text("utf-8").strip() if version.is_file() else "1.0"
        index = self.root / "index.json"
        if index.is_file():
            idx = json.loads(index.read_text("utf-8"))
            meta["problems_total"], meta["by_family"] = idx.get("problems"), idx.get("by_family", {})
            meta["families"] = {s["family"]: {"cells": s["path"], "count": s["count"], "sha256": s["sha256"]}
                                for s in idx.get("shards", []) if s.get("kind") == "family"}
        return meta

    @cached_property
    def problems(self) -> dict[str, Problem]:
        dates = self.meta.get("problem_file_dates", {})
        out = {}
        for f in sorted((self.root / "problems").glob("*.json")):
            raw = json.loads(f.read_text("utf-8"))
            out[raw["id"]] = Problem(raw=raw, file_date=dates.get(raw["id"]))
        return out

    @property
    def checkers_dir(self) -> Path:
        return self.root / "checkers"

    @property
    def refs_dir(self) -> Path:
        return self.root / "refs"

    @cached_property
    def references(self) -> dict[str, list[Reference]]:
        out: dict[str, list[Reference]] = {}
        for row in self.meta.get("reference_expected", []):
            p = self.refs_dir / row["file"]
            if p.is_file():
                out.setdefault(row["problem"], []).append(
                    Reference(file=row["file"], path=p, expected=row["expected"], ours=row["file"].startswith("ours_")))
        return out

    # ------------------------------------------------------------------------------------------- families

    @cached_property
    def families(self) -> dict[str, dict[str, Any]]:
        """Family definitions (families/NAME/family.json), by name; their cells load only when asked for."""
        out = {}
        for name in sorted(self.meta.get("families", {})):
            path = self.root / "families" / name / "family.json"
            if path.is_file():
                out[name] = json.loads(path.read_text("utf-8"))
        return out

    def cells(self, name: str) -> dict[str, str]:
        """A family's cells as {id: its line of cells.jsonl}, in file order; read once, then kept."""
        with self._cells_lock:
            if name not in self._cells:
                shard = self.meta["families"][name]
                path = self.root / shard["cells"]
                raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
                lines = [x for x in raw.decode("utf-8").splitlines() if x.strip()]
                self._cells[name] = {json.loads(x)["id"]: x for x in lines}
            return self._cells[name]

    @cached_property
    def _cells(self) -> dict[str, dict[str, str]]:
        return {}

    @cached_property
    def _cells_lock(self) -> threading.Lock:
        return threading.Lock()

    def family_of(self, pid: str) -> str | None:
        for name, fam in self.families.items():
            if any(pid.startswith(x) for x in fam.get("id_prefixes", [])):
                return name
        return None

    def find(self, pid: str) -> Problem | None:
        """A single problem or a family cell (written out as obb.py's materialize writes it), or None."""
        if pid in self.problems:
            return self.problems[pid]
        name = self.family_of(pid)
        if name is None:
            return None
        line = self.cells(name).get(pid)
        if line is None:
            return None
        return Problem(raw=materialize(self.families[name], json.loads(line)), file_date=None)

    def family_problems(self, name: str) -> list[str]:
        """Every problem id of a family: its single problems first, then its cells (as obb.py list FAMILY)."""
        singles = [pid for pid, p in self.problems.items() if p.family == name]
        cells = list(self.cells(name)) if name in self.families else []
        return singles + cells

    def sample(self, name: str, n: int = 10, seed: int = 0) -> list[str]:
        """n cell ids of a family drawn as obb.py sample FAMILY N SEED draws them."""
        ids = list(self.cells(name))
        return random.Random(seed).sample(ids, min(n, len(ids)))

    def total_problems(self) -> int:
        return int(self.meta.get("problems_total") or len(self.problems))

    def family_counts(self) -> dict[str, int]:
        counts = dict(self.meta.get("by_family") or {})
        if not counts:
            for p in self.problems.values():
                counts[p.family] = counts.get(p.family, 0) + 1
        return dict(sorted(counts.items()))

    def reference_file(self, name: str) -> Path | None:
        if not re.fullmatch(r"[\w.\-]+", name) or name.startswith("."):
            return None
        p = self.refs_dir / name
        return p if p.is_file() else None

    def describe(self) -> str:
        commit = (self.meta.get("commit") or "")[:7]
        version = f"v{self.meta.get('version')} " if self.meta.get("version") else ""
        if self.bundled:
            return f"bundled copy of {self.meta['repository']} {version}at {commit} ({self.meta['commit_date'][:10]})"
        return f"local checkout {self.root}" + (f" at {commit}" if commit else "")


def _fill(template: Any, values: dict[str, Any]) -> Any:
    if isinstance(template, list):
        return [_fill(t, values) for t in template]
    return template.format(**values)


def materialize(fam: dict[str, Any], cell: dict[str, Any]) -> dict[str, Any]:
    """The problem a family cell stands for, written out like a problem file: obb.py's materialize, line for line."""
    values = dict(cell["params"])
    tpl = dict(fam["template"])
    tpl.update(fam.get("variants", {}).get(cell.get("variant", ""), {}))
    holder = cell.get("holder") or fam["holder_unknown"]
    ours = bool(cell.get("quantavane_record"))
    read = cell.get("read", fam["read"])
    title = _fill(tpl["title"], values)
    values.update(best=cell["best"], holder=holder, title=title)
    best_known: dict[str, Any] = {
        "value": cell["best"],
        "source": f"{fam['keeper']}, {title}: {cell['best']} ({holder}); read {read}",
        "kind": "table entry",
        "provenance": {"keeper": fam["keeper"], "url": _fill(fam.get("cell_url") or fam["page"], values),
                       "read": read, "revision": fam["revision"], "holder": holder, "quantavane": ours},
    }
    if fam.get("exact_values", True):
        best_known["exact"] = cell["best"]
    p: dict[str, Any] = {
        "id": cell["id"], "family": fam["family"], "title": title, "page": fam["page"],
        "statement": _fill(tpl["statement"], values) + " " + _fill(fam["best_text"], values),
        "objective": fam["objective"], "submission": _fill(tpl["submission"], values),
        "checker": {"program": fam["checker"]["program"],
                    "args": _fill(tpl.get("args", fam["checker"].get("args", [])), values),
                    "value": fam["checker"]["value"]},
        "best_known": best_known, "verified_pending": [], "score": fam["score"], "added": fam["added"],
    }
    if "bound" in cell:
        p["bound"] = {"value": cell["bound"], "kind": fam["bound_kind"], "source": fam["bound_source"]}
    if ours:
        p["quantavane_record"] = True
        p["quantavane_note"] = "our object is the best known entry of the source table"
    return p


class OpenData:
    """The verified-results open data (Kaggle dataset arhancanli12/quantavane-verified-results), as bundled."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.dir = data_dir / "open_data"

    @cached_property
    def records(self) -> list[dict[str, Any]]:
        return json.loads((self.dir / "records.json").read_text("utf-8"))["records"]

    @cached_property
    def totals(self) -> dict[str, Any]:
        return json.loads((self.dir / "totals.json").read_text("utf-8"))

    @cached_property
    def readme(self) -> str:
        return (self.dir / "README.md").read_text("utf-8")

    @cached_property
    def covering_array_runs(self) -> list[tuple[int, int, int, int, int, int, int, str]]:
        """(t, v, k_from, k_to, N, previous_N, family_rows_k, source), sorted as in the source file."""
        with open(self.dir / "covering_array_entries_runs.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["t", "v", "k_from", "k_to", "N", "previous_N", "family_rows_k", "source"], rows[0]
        return [(int(t), int(v), int(k0), int(k1), int(n), int(p), int(fk), src)
                for t, v, k0, k1, n, p, fk, src in rows[1:]]

    @cached_property
    def catools_rows(self) -> list[dict[str, str]]:
        with open(self.dir / "covering_arrays_catools_rows.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def expand_covering_array_csv(self) -> bytes:
        """covering_array_entries.csv as published, rebuilt from the runs (used to prove the runs are lossless)."""
        import io
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(["t", "v", "k", "N", "previous_N", "family_rows_k", "source"])
        for t, v, k0, k1, n, p, fk, src in self.covering_array_runs:
            for k in range(k0, k1 + 1):
                w.writerow([t, v, k, n, p, fk, src])
        return buf.getvalue().encode("utf-8")


class ReplayIndex:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.path = data_dir / "replays" / "index.json"

    @cached_property
    def index(self) -> dict[str, Any]:
        return json.loads(self.path.read_text("utf-8"))

    @property
    def sections(self) -> list[dict[str, Any]]:
        return self.index["sections"]


@dataclass
class Store:
    """Everything the tools read, created once per server."""
    benchmark: Benchmark
    open_data: OpenData = field(default_factory=OpenData)
    replays: ReplayIndex = field(default_factory=ReplayIndex)

    @cached_property
    def manifest(self) -> Manifest:
        return Manifest.load(self.benchmark.data_dir)
