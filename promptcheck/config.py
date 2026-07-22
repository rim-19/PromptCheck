"""Test-suite schema and YAML loading.

A suite is a single YAML file describing one prompt, the models to run it
against, shared defaults, and a list of test cases (input + assertions).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

AssertionType = Literal[
    "equals", "contains", "not_contains", "regex", "llm_rubric"
]

#: Assertion types that require a model call (an LLM judge) to evaluate.
MODEL_JUDGED = {"llm_rubric"}


class Assertion(BaseModel):
    """A single check applied to a model's output for one test case."""

    model_config = ConfigDict(extra="forbid")

    type: AssertionType
    value: str
    ignore_case: bool = True

    def describe(self) -> str:
        return f"{self.type}({self.value!r})"

    @property
    def needs_judge(self) -> bool:
        return self.type in MODEL_JUDGED


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    input: str
    name: str | None = None
    # `assert` is a Python keyword, so we expose it via alias.
    assertions: list[Assertion] = Field(alias="assert", min_length=1)

    @property
    def label(self) -> str:
        return self.name or (self.input[:40] + ("…" if len(self.input) > 40 else ""))


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0
    max_tokens: int = 512


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    prompt: str
    models: list[str] = Field(min_length=1)
    defaults: Defaults = Field(default_factory=Defaults)
    tests: list[TestCase] = Field(min_length=1)

    # Model used to grade `llm_rubric` assertions. Pin this and leave it fixed
    # so the judge itself doesn't drift. Defaults to the first model under test.
    judge: str | None = None

    # Set by the loader so results can reference their origin file.
    source_path: str = ""

    @property
    def judge_ref(self) -> str:
        return self.judge or self.models[0]

    @property
    def uses_judge(self) -> bool:
        return any(a.needs_judge for t in self.tests for a in t.assertions)

    @field_validator("prompt")
    @classmethod
    def _prompt_has_input_placeholder(cls, v: str) -> str:
        if "{{" not in v or "input" not in v:
            raise ValueError(
                "prompt must contain the '{{ input }}' placeholder so each test "
                "case can be substituted in."
            )
        return v


class SuiteError(Exception):
    """Raised when a suite file is missing or fails validation."""


def load_suite(path: str | Path) -> Suite:
    p = Path(path)
    if not p.exists():
        raise SuiteError(f"Suite file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SuiteError(f"{p}: invalid YAML — {e}") from e
    if not isinstance(raw, dict):
        raise SuiteError(f"{p}: top level must be a mapping, got {type(raw).__name__}")
    try:
        suite = Suite(**raw)
    except ValidationError as e:
        raise SuiteError(f"{p}: {e}") from e
    suite.source_path = str(p)
    return suite


def discover_suites(target: str | Path) -> list[Path]:
    """Resolve a path or glob-ish target into a list of suite files.

    - a file  -> [that file]
    - a dir   -> all *.yaml / *.yml under it (recursive)
    """
    p = Path(target)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(
            q for q in p.rglob("*") if q.suffix.lower() in (".yaml", ".yml")
        )
    # Fall back to treating it as a glob pattern relative to cwd.
    matches = sorted(Path(".").glob(str(target)))
    return [m for m in matches if m.suffix.lower() in (".yaml", ".yml")]
