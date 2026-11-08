"""Set resource limits on this process, then replace it with the command (POSIX). Standard library only; run as

    python -I -B _trampoline.py LIMITS_JSON -- PROGRAM ARG...

LIMITS_JSON maps resource names (RLIMIT_CPU, RLIMIT_AS, ...) to a soft limit or [soft, hard]. A limit is never raised
above the current hard limit. If a limit cannot be set the command is not run and the exit status is 125, so a check
never runs with less protection than reported. The limits survive exec, so they bind the command itself."""
import json
import os
import resource
import sys


def main() -> None:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        sys.stderr.write("usage: _trampoline.py LIMITS_JSON -- PROGRAM ARG...\n")
        os._exit(125)
    limits = json.loads(sys.argv[1])
    argv = sys.argv[3:]
    for name, value in limits.items():
        kind = getattr(resource, name)
        soft, hard = value if isinstance(value, list) else (value, value)
        _, cur_hard = resource.getrlimit(kind)
        if cur_hard != resource.RLIM_INFINITY:
            hard = min(hard, cur_hard)
            soft = min(soft, hard)
        try:
            resource.setrlimit(kind, (soft, hard))
        except (ValueError, OSError) as e:
            sys.stderr.write(f"quantavane-sandbox: cannot set {name}: {e}\n")
            os._exit(125)
    try:
        os.execv(argv[0], argv)
    except OSError as e:
        sys.stderr.write(f"quantavane-sandbox: cannot run {os.path.basename(argv[0])}: {e.strerror}\n")
        os._exit(126)


if __name__ == "__main__":
    main()
