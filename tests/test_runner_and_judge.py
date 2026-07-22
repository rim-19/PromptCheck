"""Pure helpers in runner and judge (no network)."""

from promptcheck.judge import _parse_verdict
from promptcheck.runner import render_prompt


def test_render_prompt_substitutes_input():
    assert render_prompt("A {{ input }} B", "X") == "A X B"


def test_render_prompt_handles_spacing_variants():
    assert render_prompt("{{input}}", "hi") == "hi"
    assert render_prompt("{{   input   }}", "hi") == "hi"


def test_render_prompt_replaces_all_occurrences():
    assert render_prompt("{{ input }}-{{ input }}", "x") == "x-x"


def test_parse_verdict_clean_json():
    passed, reason = _parse_verdict('{"pass": true, "reason": "ok"}')
    assert passed is True and reason == "ok"


def test_parse_verdict_with_code_fence():
    passed, _ = _parse_verdict('```json\n{"pass": false, "reason": "no"}\n```')
    assert passed is False


def test_parse_verdict_with_surrounding_prose():
    passed, _ = _parse_verdict('Sure! {"pass": true, "reason": "good"} done')
    assert passed is True


def test_parse_verdict_unparseable():
    passed, reason = _parse_verdict("I think it is fine")
    assert passed is None
    assert "no JSON" in reason or "invalid" in reason


def test_parse_verdict_missing_pass_key():
    passed, _ = _parse_verdict('{"reason": "hmm"}')
    assert passed is None
