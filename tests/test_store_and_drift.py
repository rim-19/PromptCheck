"""Store persistence and drift comparison, against a temp SQLite DB."""

import pytest

from promptcheck import store
from promptcheck.assertions import AssertionResult
from promptcheck.config import Assertion, Suite, TestCase
from promptcheck.drift import diff_against_baseline
from promptcheck.runner import ModelRun, SuiteRun, TestResult

MODEL = "groq/llama-3.1-8b-instant"


def _suite():
    return Suite(
        name="s",
        prompt="Classify {{ input }}",
        models=[MODEL],
        tests=[
            TestCase(input="a", **{"assert": [Assertion(type="equals", value="refund")]}),
            TestCase(input="b", **{"assert": [Assertion(type="equals", value="bug")]}),
        ],
    )


def _result(idx, passed, version="v1"):
    return TestResult(
        model_ref=MODEL,
        test_index=idx,
        test_label=f"t{idx}",
        input=f"in{idx}",
        output="refund" if passed else "wrong",
        passed=passed,
        assertion_results=[AssertionResult(passed, "r", "equals('x')")],
        latency_ms=10,
        cost_usd=0.0,
        model_version=version,
    )


def _suite_run(pass_flags, version="v1"):
    results = [_result(i, p, version) for i, p in enumerate(pass_flags)]
    return SuiteRun(suite=_suite(), model_runs=[ModelRun(model_ref=MODEL, results=results)])


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "h.db")
    yield c
    c.close()


def test_save_and_query(conn):
    run_ids = store.save_run(conn, _suite_run([True, True]))
    assert len(run_ids) == 1
    latest = store.latest_run(conn, "s", MODEL)
    assert latest.pass_count == 2 and latest.total_count == 2
    status = store.run_test_status(conn, run_ids[0])
    assert status[0]["passed"] and status[1]["passed"]


def test_baseline_set_and_get(conn):
    rid = store.save_run(conn, _suite_run([True, True]))[0]
    store.set_baseline(conn, "s", MODEL, rid)
    assert store.get_baseline_run_id(conn, "s", MODEL) == rid


def test_drift_seeds_on_first_watch(conn):
    sr = _suite_run([True, True])
    rid = store.save_run(conn, sr)[0]
    d = diff_against_baseline(conn, "s", sr.model_runs[0], rid)
    assert d.seeded is True
    assert d.has_regression is False
    # baseline was auto-created
    assert store.get_baseline_run_id(conn, "s", MODEL) == rid


def test_drift_detects_regression(conn):
    base = _suite_run([True, True])
    base_id = store.save_run(conn, base)[0]
    store.set_baseline(conn, "s", MODEL, base_id)

    now = _suite_run([True, False])  # test #1 regressed
    now_id = store.save_run(conn, now)[0]
    d = diff_against_baseline(conn, "s", now.model_runs[0], now_id)
    assert d.has_regression is True
    assert [idx for idx, _ in d.regressions] == [1]
    assert d.improvements == []


def test_drift_detects_improvement_not_regression(conn):
    base = _suite_run([True, False])
    base_id = store.save_run(conn, base)[0]
    store.set_baseline(conn, "s", MODEL, base_id)

    now = _suite_run([True, True])  # test #1 now passes
    now_id = store.save_run(conn, now)[0]
    d = diff_against_baseline(conn, "s", now.model_runs[0], now_id)
    assert d.has_regression is False
    assert [idx for idx, _ in d.improvements] == [1]


def test_drift_flags_version_change(conn):
    base = _suite_run([True, True], version="v1")
    base_id = store.save_run(conn, base)[0]
    store.set_baseline(conn, "s", MODEL, base_id)

    now = _suite_run([True, True], version="v2")
    now_id = store.save_run(conn, now)[0]
    d = diff_against_baseline(conn, "s", now.model_runs[0], now_id)
    assert d.version_changed is True
    assert d.has_regression is False
