"""Assertion evaluation."""

import pytest

from promptcheck.assertions import evaluate
from promptcheck.config import Assertion


def _a(type_, value, ignore_case=True):
    return Assertion(type=type_, value=value, ignore_case=ignore_case)


def test_equals_ignores_case_and_whitespace():
    assert evaluate(_a("equals", "refund"), "  Refund  ").passed


def test_equals_fails_on_mismatch():
    r = evaluate(_a("equals", "refund"), "question")
    assert not r.passed
    assert "expected" in r.reason


def test_equals_case_sensitive():
    assert not evaluate(_a("equals", "refund", ignore_case=False), "Refund").passed


def test_contains():
    assert evaluate(_a("contains", "cat"), "concatenate").passed
    assert not evaluate(_a("contains", "dog"), "concatenate").passed


def test_not_contains():
    assert evaluate(_a("not_contains", "bug"), "this is a refund").passed
    assert not evaluate(_a("not_contains", "bug"), "this is a bug").passed


def test_regex():
    assert evaluate(_a("regex", r"^\d{3}$"), "123").passed
    assert not evaluate(_a("regex", r"^\d{3}$"), "12a").passed


def test_llm_rubric_not_evaluated_here():
    with pytest.raises(ValueError):
        evaluate(_a("llm_rubric", "criterion"), "output")
