"""The sandbox itself: timeouts, the memory cap, no shell, a minimal environment, no file writes."""
import sys

import pytest

from quantavane_mcp import sandbox

PY = sys.executable


def run(tmp_path, code, *args, timeout=20, memory=256):
    return sandbox.run([PY, "-I", "-c", code, *args], cwd=tmp_path, limits=sandbox.Limits(timeout_s=timeout,
                                                                                          memory_mb=memory))


def test_ordinary_run(tmp_path):
    r = run(tmp_path, "print('hi')")
    assert r.exit_code == 0 and r.stdout.strip() == "hi" and r.limit_hit is None


def test_exit_status_is_kept(tmp_path):
    r = run(tmp_path, "import sys; sys.exit(3)")
    assert r.exit_code == 3 and r.limit_hit is None


def test_timeout_kills_the_process(tmp_path):
    r = run(tmp_path, "import time; time.sleep(60)", timeout=1)
    assert r.timed_out and r.limit_hit == "timeout" and r.seconds < 30


@pytest.mark.skipif(sandbox.memory_cap_mode() is None, reason="no memory cap on this platform")
def test_memory_cap_kills_the_process(tmp_path):
    r = run(tmp_path, "b = bytearray(900 * 2**20); import time; time.sleep(20)", memory=128)
    assert r.memory_exceeded and r.limit_hit == "memory"


def test_no_shell_interpolation(tmp_path):
    r = run(tmp_path, "import sys; print(sys.argv[1:])", "$(touch pwned)", "; touch pwned2", "`id`")
    assert "$(touch pwned)" in r.stdout and "`id`" in r.stdout
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()


def test_environment_is_minimal(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTAVANE_SECRET_FOR_TEST", "s3cret")
    r = run(tmp_path, "import os; print(sorted(os.environ)); print(os.environ.get('HOME'))")
    assert "QUANTAVANE_SECRET_FOR_TEST" not in r.stdout and "s3cret" not in r.stdout
    assert r.stdout.strip().splitlines()[-1] == "None"


def test_files_cannot_grow(tmp_path):
    r = run(tmp_path, "f = open('x.bin', 'wb'); f.write(b'x' * 100000); f.flush()")
    assert r.exit_code != 0
    assert not (tmp_path / "x.bin").exists() or (tmp_path / "x.bin").stat().st_size == 0


def test_stdin_is_closed(tmp_path):
    r = run(tmp_path, "import sys; print(repr(sys.stdin.read()))")
    assert r.stdout.strip() == "''"


def test_argv_must_be_a_list_of_strings(tmp_path):
    with pytest.raises(TypeError):
        sandbox.run("echo hi", cwd=tmp_path, limits=sandbox.Limits(timeout_s=5, memory_mb=64))
    with pytest.raises(TypeError):
        sandbox.run([], cwd=tmp_path, limits=sandbox.Limits(timeout_s=5, memory_mb=64))
