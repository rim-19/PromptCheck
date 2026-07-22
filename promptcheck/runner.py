"""Runs a suite: fan out over (model x test), render the prompt, call the
provider, evaluate assertions. Async with a concurrency cap and simple retry."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

import httpx

from .assertions import AssertionResult, evaluate
from .config import Suite, TestCase
from .judge import judge_rubric
from .providers import ProviderError, get_provider
from .providers.base import RetryableProviderError

_PLACEHOLDER = re.compile(r"\{\{\s*input\s*\}\}")


def render_prompt(template: str, test_input: str) -> str:
    return _PLACEHOLDER.sub(lambda _: test_input, template)


@dataclass
class TestResult:
    model_ref: str
    test_index: int
    test_label: str
    input: str
    output: str
    passed: bool
    assertion_results: list[AssertionResult]
    latency_ms: int
    cost_usd: float
    model_version: str
    error: str | None = None


@dataclass
class ModelRun:
    model_ref: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)


@dataclass
class SuiteRun:
    suite: Suite
    model_runs: list[ModelRun]


async def _run_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    suite: Suite,
    model_ref: str,
    index: int,
    test: TestCase,
    retries: int = 3,
) -> TestResult:
    provider, model = get_provider(model_ref)
    prompt = render_prompt(suite.prompt, test.input)

    last_err: Exception | None = None
    gen = None
    async with sem:
        for attempt in range(retries + 1):
            try:
                gen = await provider.generate(
                    client,
                    model=model,
                    prompt=prompt,
                    temperature=suite.defaults.temperature,
                    max_tokens=suite.defaults.max_tokens,
                )
                break
            except RetryableProviderError as e:
                last_err = e
                if attempt < retries:
                    # Honor server Retry-After, else gentle exponential backoff.
                    # Bounded so a rate-limited run fails fast & honestly rather
                    # than appearing to hang on strict free tiers.
                    wait = e.retry_after if e.retry_after else 1.5 * (2**attempt)
                    await asyncio.sleep(min(wait, 12.0))
            except ProviderError as e:
                last_err = e
                break  # non-retryable (auth, bad model, safety block)

    if gen is None:
        return TestResult(
            model_ref=model_ref,
            test_index=index,
            test_label=test.label,
            input=test.input,
            output="",
            passed=False,
            assertion_results=[],
            latency_ms=0,
            cost_usd=0.0,
            model_version=model,
            error=str(last_err),
        )

    # Sync assertions evaluate inline; llm_rubric assertions call the judge.
    ar: list[AssertionResult] = []
    for a in test.assertions:
        if a.needs_judge:
            ar.append(await judge_rubric(client, sem, suite.judge_ref, a, gen.text))
        else:
            ar.append(evaluate(a, gen.text))
    passed = all(r.passed for r in ar)
    return TestResult(
        model_ref=model_ref,
        test_index=index,
        test_label=test.label,
        input=test.input,
        output=gen.text,
        passed=passed,
        assertion_results=ar,
        latency_ms=gen.latency_ms,
        cost_usd=gen.cost_usd,
        model_version=gen.model_version,
    )


async def run_suite(suite: Suite, concurrency: int = 3) -> SuiteRun:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        tasks = {
            model_ref: [
                _run_one(client, sem, suite, model_ref, i, t)
                for i, t in enumerate(suite.tests)
            ]
            for model_ref in suite.models
        }
        model_runs: list[ModelRun] = []
        for model_ref, coros in tasks.items():
            results = await asyncio.gather(*coros)
            model_runs.append(ModelRun(model_ref=model_ref, results=list(results)))
    return SuiteRun(suite=suite, model_runs=model_runs)
