"""The data bundled with the server (or a local benchmark checkout), loaded lazily and checked against MANIFEST.json."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, cast

DATA_DIR = Path(__file__).resolve().parent / "data"

# checker value kind -> problem family
FAMILIES = {
    "bound": "constant", "c68": "constant", "c42": "constant", "c59": "constant", "c16": "constant",
    "ramsey": "ramsey", "spherical": "spherical-code", "blocks": "covering-design", "cvrp": "vehicle-routing",
    "words": "constant-weight-code",
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
        return FAMILIES.get(self.kind, "other")

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

    def reference_file(self, name: str) -> Path | None:
        if not re.fullmatch(r"[\w.\-]+", name) or name.startswith("."):
            return None
        p = self.refs_dir / name
        return p if p.is_file() else None

    def describe(self) -> str:
        commit = (self.meta.get("commit") or "")[:7]
        if self.bundled:
            return f"bundled copy of {self.meta['repository']} at {commit} ({self.meta['commit_date'][:10]})"
        return f"local checkout {self.root}" + (f" at {commit}" if commit else "")


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
