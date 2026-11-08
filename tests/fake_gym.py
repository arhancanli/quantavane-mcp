"""A stand-in for a training gym's backend: it judges a proposed object with the same sandboxed checker as
check_candidate, so the hook can be tested without a gym."""
from fractions import Fraction

from quantavane_mcp.checking import Checker
from quantavane_mcp.config import Settings
from quantavane_mcp.data import Benchmark, Store


class Backend:
    def __init__(self):
        self.checker = Checker(Store(benchmark=Benchmark()), Settings(timeout_s=60))

    def environments(self):
        return [{"id": "cw-34-6-5", "problem_id": "cw-34-6-5", "description": "constant weight codes A(34,6,5)"},
                {"id": "float-env", "problem_id": None, "description": "returns an inexact score (for the test)"}]

    def propose(self, env_id, obj):
        if env_id == "float-env":
            return {"verdict": "pass", "score": 0.5}
        r = self.checker.check_data(env_id, obj.encode())
        return {"verdict": "pass" if r.verdict == "certified" else "fail",
                "score": Fraction(r.value) if r.value else None, "sha256": r.certificate_sha256}


backend = Backend
