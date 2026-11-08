"""Settings, read once from environment variables. Every limit has a safe default; none enables network access."""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ENV_PREFIX = "QUANTAVANE_MCP_"


class ConfigError(ValueError):
    """A setting has a value the server cannot use; the message names the variable."""


def _int(env: dict[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(ENV_PREFIX + name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{ENV_PREFIX}{name}={raw!r} is not an integer") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{ENV_PREFIX}{name}={value} is outside {lo}..{hi}")
    return value


def _path(env: dict[str, str], name: str) -> Path | None:
    raw = env.get(ENV_PREFIX + name)
    return Path(raw).expanduser() if raw and raw.strip() else None


def default_cache_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "quantavane-mcp"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "quantavane-mcp"


def default_roots() -> list[Path]:
    """Folders a certificate_path may point into when QUANTAVANE_MCP_ROOTS is unset: the working directory (unless it
    is the file system root or the home folder itself) and the temporary folders."""
    roots: list[Path] = []
    cwd = Path.cwd().resolve()
    if cwd != Path(cwd.anchor) and cwd != Path.home().resolve():
        roots.append(cwd)
    for t in (tempfile.gettempdir(), "/tmp"):
        p = Path(t)
        if p.is_dir():
            rp = p.resolve()
            if rp not in roots:
                roots.append(rp)
    return roots


@dataclass(frozen=True)
class Settings:
    timeout_s: int = 120              # default wall-clock limit of one check
    max_timeout_s: int = 900          # the largest timeout a caller may ask for
    memory_mb: int = 1024             # memory cap of one checker process
    max_bytes: int = 32 * 2**20       # largest certificate file accepted
    max_concurrent: int = 2           # checks running at once
    roots: tuple[Path, ...] = ()      # where certificate_path may point
    instances_dir: Path | None = None   # CVRPLIB instance files (fetched by the benchmark's fetch.sh)
    benchmark_dir: Path | None = None   # a local benchmark checkout used instead of the bundled copy
    cache_dir: Path = field(default_factory=default_cache_dir)
    cc: str | None = None             # C compiler for the Ramsey checker (default: cc, then gcc, then clang)
    gym: str | None = None            # "module:attribute" of a training-gym backend; unset = no gym tools
    allow_uncapped: bool = False      # run checkers where the memory cap cannot be enforced (not Linux or macOS)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        max_timeout = _int(env, "MAX_TIMEOUT_S", 900, 1, 86400)
        roots_raw = env.get(ENV_PREFIX + "ROOTS")
        if roots_raw and roots_raw.strip():
            roots = tuple(Path(p).expanduser().resolve() for p in roots_raw.split(os.pathsep) if p.strip())
        else:
            roots = tuple(default_roots())
        cache = _path(env, "CACHE") or default_cache_dir()
        return cls(
            timeout_s=min(_int(env, "TIMEOUT_S", 120, 1, 86400), max_timeout),
            max_timeout_s=max_timeout,
            memory_mb=_int(env, "MEMORY_MB", 1024, 64, 1 << 20),
            max_bytes=_int(env, "MAX_BYTES", 32 * 2**20, 1, 1 << 34),
            max_concurrent=_int(env, "MAX_CONCURRENT", 2, 1, 64),
            roots=roots,
            instances_dir=_path(env, "INSTANCES"),
            benchmark_dir=_path(env, "BENCHMARK_DIR"),
            cache_dir=cache,
            cc=(env.get(ENV_PREFIX + "CC") or "").strip() or None,
            gym=(env.get(ENV_PREFIX + "GYM") or "").strip() or None,
            allow_uncapped=(env.get(ENV_PREFIX + "ALLOW_UNCAPPED", "").strip() == "1"),
        )
