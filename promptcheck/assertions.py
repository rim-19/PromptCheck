"""Assertion evaluation. Each assertion checks a model output and returns a
pass/fail with a human-readable reason."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Assertion


@dataclass
class AssertionResult:
    passed: bool
    reason: str
    assertion: str  # describe() of the source assertion
    judge_model: str | None = None  # judge version, for model-judged assertions
    # True when the assertion couldn't be evaluated at all (e.g. the judge call
    # failed). Distinct from a genuine failed check — see drift.py.
    errored: bool = False


def evaluate(assertion: Assertion, output: str) -> AssertionResult:
    a = assertion
    out = output
    val = a.value
    if a.ignore_case:
        out_cmp = output.lower()
        val_cmp = val.lower()
    else:
        out_cmp = output
        val_cmp = val

    desc = a.describe()

    if a.type == "llm_rubric":
        # Model-judged; evaluated asynchronously in judge.py, never here.
        raise ValueError("llm_rubric must be evaluated via the judge, not evaluate()")

    if a.type == "equals":
        passed = out_cmp.strip() == val_cmp.strip()
        reason = "matched exactly" if passed else f"expected {val!r}, got {output.strip()!r}"

    elif a.type == "contains":
        passed = val_cmp in out_cmp
        reason = f"found {val!r}" if passed else f"did not contain {val!r}"

    elif a.type == "not_contains":
        passed = val_cmp not in out_cmp
        reason = f"correctly absent {val!r}" if passed else f"unexpectedly contained {val!r}"

    elif a.type == "regex":
        flags = re.IGNORECASE if a.ignore_case else 0
        passed = re.search(val, out, flags) is not None
        reason = f"matched /{val}/" if passed else f"no match for /{val}/"

    else:  # pragma: no cover - schema prevents this
        passed = False
        reason = f"unknown assertion type {a.type!r}"

    return AssertionResult(passed=passed, reason=reason, assertion=desc)
