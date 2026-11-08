"""Run a program under limits: no shell, an argument list, a fresh empty working folder, a minimal environment, stdin
closed, its own process group, a wall-clock timeout, a CPU-time limit, files limited to 0 bytes (RLIMIT_FSIZE), a
file-descriptor limit and a memory cap.

The memory cap is RLIMIT_AS plus sampling of the resident size on Linux, and sampling of the physical footprint (every
20 ms, through libproc) on macOS, where RLIMIT_AS cannot be set; the whole process group is killed when it is passed
(a very fast allocation can overshoot between two samples before the kill). On other platforms the cap cannot be
enforced and run() refuses unless allow_uncapped is set."""
from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import signal
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

TRAMPOLINE = str(Path(__file__).resolve().parent / "_trampoline.py")
POLL_S = 0.02
EXIT_SANDBOX = 125


class SandboxUnavailable(RuntimeError):
    """The limits cannot be enforced on this platform."""


@dataclass(frozen=True)
class Limits:
    timeout_s: float
    memory_mb: int
    fsize_bytes: int = 0          # largest file the program may write (0: none)
    nofile: int = 64              # open file descriptors
    max_output_bytes: int = 1 << 20


@dataclass
class RunResult:
    exit_code: int | None
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    memory_exceeded: bool = False
    peak_memory_mb: float | None = None
    signal_name: str | None = None
    sandbox_error: str | None = None

    @property
    def limit_hit(self) -> str | None:
        if self.timed_out:
            return "timeout"
        if self.memory_exceeded:
            return "memory"
        if self.signal_name == "SIGXCPU":
            return "cpu-time"
        if self.sandbox_error:
            return "sandbox"
        return None


# ------------------------------------------------------------------------------------------------ memory sampling

_libproc = None
if sys.platform == "darwin":
    try:
        _libproc = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib", use_errno=True)
        _libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        _libproc.proc_pid_rusage.restype = ctypes.c_int
    except (OSError, AttributeError):
        _libproc = None


def memory_bytes(pid: int) -> int | None:
    """The process's memory now: physical footprint on macOS, resident size on Linux; None if unknown."""
    if _libproc is not None:
        buf = ctypes.create_string_buffer(512)            # rusage_info_v0 is 96 bytes
        if _libproc.proc_pid_rusage(pid, 0, buf) != 0:    # flavor 0 = RUSAGE_INFO_V0
            return None
        resident, footprint = struct.unpack_from("<QQ", buf.raw, 64)
        return max(resident, footprint)
    if sys.platform.startswith("linux"):
        try:
            with open(f"/proc/{pid}/status", "rb") as f:
                for line in f:
                    if line.startswith(b"VmRSS:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            return None
    return None


def memory_cap_mode() -> str | None:
    """How the memory cap is enforced here, or None when it cannot be."""
    if sys.platform.startswith("linux"):
        return "RLIMIT_AS and resident-size sampling"
    if sys.platform == "darwin" and _libproc is not None:
        return "physical-footprint sampling every 20 ms (macOS)"
    return None


# ------------------------------------------------------------------------------------------------ running


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _signal_name(code: int | None) -> str | None:
    if code is None or code >= 0:
        return None
    try:
        return signal.Signals(-code).name
    except ValueError:
        return f"signal {-code}"


def run(argv: list[str], *, cwd: str | Path, limits: Limits, env: dict[str, str] | None = None,
        allow_uncapped: bool = False) -> RunResult:
    """Run argv (a list; never through a shell) in cwd under limits."""
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
        raise TypeError("argv must be a non-empty list of strings")
    mode = memory_cap_mode()
    posix = os.name == "posix"
    if mode is None and not allow_uncapped:
        raise SandboxUnavailable(
            f"the memory cap cannot be enforced on {sys.platform}; run on Linux or macOS (or WSL), or set "
            "QUANTAVANE_MCP_ALLOW_UNCAPPED=1 to run with the timeout and size limits only")
    child_env = {"PATH": "/usr/bin:/bin"} if env is None else dict(env)
    if posix:
        rl = {
            "RLIMIT_CPU": [int(limits.timeout_s) + 2, int(limits.timeout_s) + 7],
            "RLIMIT_FSIZE": limits.fsize_bytes,
            "RLIMIT_NOFILE": limits.nofile,
            "RLIMIT_CORE": 0,
        }
        if sys.platform.startswith("linux"):
            rl["RLIMIT_AS"] = limits.memory_mb * 2**20
        cmd = [sys.executable, "-I", "-B", TRAMPOLINE, json.dumps(rl), "--", *argv]
    else:
        cmd = list(argv)
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=posix, close_fds=True)
    cap = limits.memory_mb * 2**20
    state: dict[str, int] = {"peak": 0, "exceeded": 0}
    done = threading.Event()

    def watch() -> None:
        while not done.wait(POLL_S):
            used = memory_bytes(proc.pid)
            if used is None:
                continue
            state["peak"] = max(state["peak"], used)
            if used > cap and proc.returncode is None:
                state["exceeded"] = 1
                _kill_group(proc)
                return

    watcher = threading.Thread(target=watch, name="quantavane-memory-watch", daemon=True)
    if mode is not None:
        watcher.start()
    timed_out = False
    try:
        out, err = proc.communicate(timeout=limits.timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        out, err = proc.communicate()
    except BaseException:
        _kill_group(proc)
        proc.wait()
        raise
    finally:
        done.set()
    if watcher.is_alive():
        watcher.join(1)
    seconds = time.monotonic() - t0
    out_s = out[-limits.max_output_bytes:].decode("utf-8", "replace")
    err_s = err[-limits.max_output_bytes:].decode("utf-8", "replace")
    sandbox_error = None
    if proc.returncode == EXIT_SANDBOX and "quantavane-sandbox:" in err_s:
        sandbox_error = err_s.strip().splitlines()[-1]
    last = err_s.strip().splitlines()[-1] if err_s.strip() else ""
    if proc.returncode not in (0, None) and last.startswith("MemoryError"):
        state["exceeded"] = 1         # an allocation refused (RLIMIT_AS, or the system): no verdict, not invalid
    return RunResult(
        exit_code=proc.returncode, stdout=out_s, stderr=err_s, seconds=round(seconds, 3), timed_out=timed_out,
        memory_exceeded=bool(state["exceeded"]),
        peak_memory_mb=round(state["peak"] / 2**20, 1) if state["peak"] else None,
        signal_name=_signal_name(proc.returncode), sandbox_error=sandbox_error)
