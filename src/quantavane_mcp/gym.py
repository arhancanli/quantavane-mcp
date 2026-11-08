"""The hook for a training gym (gym-style environments around the same exact checkers): off by default, and the gym is
never imported unless QUANTAVANE_MCP_GYM names it.

A backend is an object (or a zero-argument callable that returns one) with two methods:

    environments() -> iterable of {"id": str, "problem_id": str | None, "description": str}
    propose(env_id: str, obj: str) -> {"verdict": str, "score": str | int | Fraction | None, ...}

propose judges one proposed object with the same exact checkers as the benchmark and returns the exact verdict and
score; other keys are passed back as details. With QUANTAVANE_MCP_GYM=package.module:attribute set, the server adds
two tools, gym_environments and gym_propose; with it unset (the default) it adds none."""
from __future__ import annotations

import concurrent.futures
import importlib
from fractions import Fraction
from typing import Any

from .exact import fraction_text, parse_value
from .models import GymEnvironment, GymEnvironments, GymVerdict

MAX_OBJECT_CHARS = 4_000_000
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="quantavane-gym")


class GymError(RuntimeError):
    """The gym backend is missing, malformed, or returned something that is not exact."""


def load_backend(spec: str | None) -> Any | None:
    if not spec:
        return None
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise GymError(f"QUANTAVANE_MCP_GYM={spec!r} must look like package.module:attribute")
    try:
        obj = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as e:
        raise GymError(f"QUANTAVANE_MCP_GYM={spec!r} cannot be loaded: {e}") from None
    if isinstance(obj, type) or (callable(obj) and not hasattr(obj, "propose")):   # a class or a factory
        try:
            obj = obj()
        except Exception as e:
            raise GymError(f"QUANTAVANE_MCP_GYM={spec!r} could not be created: {e}") from None
    for method in ("environments", "propose"):
        if not callable(getattr(obj, method, None)):
            raise GymError(f"the gym backend {spec!r} has no {method}() method")
    return obj


def environments(backend: Any, spec: str) -> GymEnvironments:
    envs = []
    for e in backend.environments():
        envs.append(GymEnvironment(id=str(e["id"]), problem_id=e.get("problem_id"),
                                   description=str(e.get("description", ""))))
    return GymEnvironments(backend=spec, environments=envs)


def _exact_score(score: Any) -> str | None:
    if score is None:
        return None
    if isinstance(score, bool) or isinstance(score, float):
        raise GymError("the gym returned an inexact score (a float); scores must be integers, fractions or decimal "
                       "strings")
    if isinstance(score, (int, Fraction)):
        return fraction_text(Fraction(score))
    return fraction_text(parse_value(str(score)))


def propose(backend: Any, env_id: str, obj: str, timeout_s: float) -> GymVerdict:
    if len(obj) > MAX_OBJECT_CHARS:
        raise GymError(f"the object has {len(obj):,} characters; at most {MAX_OBJECT_CHARS:,} are accepted")
    future = _pool.submit(backend.propose, env_id, obj)
    try:
        out = future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        return GymVerdict(env_id=env_id, verdict="no_verdict", score=None,
                          details={"reason": f"the gym did not answer within {timeout_s} s; nothing was proved"})
    except Exception as e:
        raise GymError(f"the gym failed ({type(e).__name__}: {e}); nothing was proved") from None
    if not isinstance(out, dict) or "verdict" not in out:
        raise GymError("the gym's propose() must return a dict with a 'verdict'")
    details = {str(k): str(v)[:500] for k, v in out.items() if k not in ("verdict", "score")}
    return GymVerdict(env_id=env_id, verdict=str(out["verdict"]), score=_exact_score(out.get("score")), details=details)
