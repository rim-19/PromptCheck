"""Schema loading and validation."""

import pytest

from promptcheck.config import SuiteError, load_suite

VALID = """
name: t
prompt: "Label this: {{ input }}"
models: [groq/llama-3.1-8b-instant]
tests:
  - input: hi
    assert:
      - type: equals
        value: refund
"""


def _write(tmp_path, text):
    p = tmp_path / "suite.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_valid_suite(tmp_path):
    s = load_suite(_write(tmp_path, VALID))
    assert s.name == "t"
    assert s.models == ["groq/llama-3.1-8b-instant"]
    assert len(s.tests) == 1
    # `assert` maps to the aliased field
    assert s.tests[0].assertions[0].type == "equals"


def test_rejects_prompt_without_placeholder(tmp_path):
    bad = VALID.replace("Label this: {{ input }}", "Label this.")
    with pytest.raises(SuiteError):
        load_suite(_write(tmp_path, bad))


def test_rejects_empty_models(tmp_path):
    bad = VALID.replace("models: [groq/llama-3.1-8b-instant]", "models: []")
    with pytest.raises(SuiteError):
        load_suite(_write(tmp_path, bad))


def test_missing_file():
    with pytest.raises(SuiteError):
        load_suite("does/not/exist.yaml")


def test_judge_defaults_to_first_model(tmp_path):
    s = load_suite(_write(tmp_path, VALID))
    assert s.judge_ref == "groq/llama-3.1-8b-instant"
    assert s.uses_judge is False  # no llm_rubric in this suite
