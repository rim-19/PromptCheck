"""LLM-as-judge for `llm_rubric` assertions.

Fuzzy checks ("is the output roughly correct?") are graded by a model instead
of a string match. Because a judge is itself non-deterministic, we make it as
reproducible as possible:

* the judge model is **pinned** (suite.judge, fixed by the user),
* it always runs at **temperature 0**,
* it is asked for a strict JSON verdict, and
* the judge's exact model version is recorded on every result, so a drifting
  judge is itself visible in history.
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from .assertions import AssertionResult
from .config import Assertion
from .providers import ProviderError, get_provider
from .providers.base import RetryableProviderError

_JUDGE_MAX_TOKENS = 200
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_PROMPT = """You are a strict evaluator grading the output of another AI system.

Grading criterion:
{criterion}

AI output to grade:
\"\"\"
{output}
\"\"\"

Decide whether the output satisfies the criterion. Be strict but fair.
Respond with ONLY a compact JSON object and nothing else, in this exact form:
{{"pass": true or false, "reason": "<one short sentence>"}}"""


def _parse_verdict(text: str) -> tuple[bool | None, str]:
    """Extract {"pass":..., "reason":...} from a judge response. Lenient about
    code fences / surrounding prose. Returns (None, msg) if unparseable."""
    m = _JSON_RE.search(text)
    if not m:
        return None, f"judge returned no JSON: {text[:80]!r}"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, f"judge returned invalid JSON: {text[:80]!r}"
    if "pass" not in data:
        return None, f"judge JSON missing 'pass': {text[:80]!r}"
    return bool(data["pass"]), str(data.get("reason", "")).strip()


async def judge_rubric(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    judge_ref: str,
    assertion: Assertion,
    output: str,
    retries: int = 3,
) -> AssertionResult:
    provider, model = get_provider(judge_ref)
    prompt = _PROMPT.format(criterion=assertion.value, output=output)
    desc = assertion.describe()

    last_err: Exception | None = None
    gen = None
    async with sem:
        for attempt in range(retries + 1):
            try:
                gen = await provider.generate(
                    client,
                    model=model,
                    prompt=prompt,
                    temperature=0.0,  # always deterministic, regardless of suite defaults
                    max_tokens=_JUDGE_MAX_TOKENS,
                )
                break
            except RetryableProviderError as e:
                last_err = e
                if attempt < retries:
                    wait = e.retry_after if e.retry_after else 1.5 * (2**attempt)
                    await asyncio.sleep(min(wait, 12.0))
            except ProviderError as e:
                last_err = e
                break

    if gen is None:
        return AssertionResult(
            passed=False,
            reason=f"judge error: {last_err}",
            assertion=desc,
            judge_model=model,
        )

    passed, reason = _parse_verdict(gen.text)
    if passed is None:
        # Unparseable verdict = fail closed, but say why.
        return AssertionResult(
            passed=False, reason=reason, assertion=desc, judge_model=gen.model_version
        )
    return AssertionResult(
        passed=passed,
        reason=f"judge: {reason}" if reason else "judged",
        assertion=desc,
        judge_model=gen.model_version,
    )
