"""Dashboard read queries (no FastAPI needed — tests the query layer directly)."""

import pytest

from promptcheck import store
from promptcheck.assertions import AssertionResult
from promptcheck.config import Assertion, Suite, TestCase
from promptcheck.runner import ModelRun, SuiteRun, TestResult
from promptcheck.server import queries

MODEL = "groq/llama-3.1-8b-instant"


def _suite_run(pass_flags, version="v1"):
    suite = Suite(
        name="s",
        prompt="Do {{ input }}",
        models=[MODEL],
        tests=[
            TestCase(input=f"i{i}", **{"assert": [Assertion(type="equals", value="x")]})
            for i in range(len(pass_flags))
        ],
    )
    results = [
        TestResult(
            model_ref=MODEL,
            test_index=i,
            test_label=f"t{i}",
            input=f"i{i}",
            output="x" if p else "y",
            passed=p,
            assertion_results=[AssertionResult(p, "r", "equals('x')")],
            latency_ms=5,
            cost_usd=0.0,
            model_version=version,
        )
        for i, p in enumerate(pass_flags)
    ]
    return SuiteRun(suite=suite, model_runs=[ModelRun(model_ref=MODEL, results=results)])


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "h.db"
    conn = store.connect(path)
    base_id = store.save_run(conn, _suite_run([True, True]))[0]
    store.set_baseline(conn, "s", MODEL, base_id)
    store.save_run(conn, _suite_run([True, False], version="v2"))  # a regression run
    conn.close()
    return path


def test_list_suites(db):
    conn = queries.open_db(db)
    suites = queries.list_suites(conn)
    assert len(suites) == 1
    assert suites[0]["name"] == "s"
    assert suites[0]["total_runs"] == 2


def test_suite_detail_marks_baseline(db):
    conn = queries.open_db(db)
    detail = queries.suite_detail(conn, "s")
    runs = detail["models"][0]["runs"]
    assert len(runs) == 2
    assert runs[0]["is_baseline"] is True
    assert runs[1]["is_baseline"] is False


def test_run_diff_reports_regression(db):
    conn = queries.open_db(db)
    detail = queries.suite_detail(conn, "s")
    ids = [r["id"] for r in detail["models"][0]["runs"]]
    diff = queries.run_diff(conn, ids[0], ids[1])
    assert diff["regressions"] == 1
    assert diff["version_changed"] is True
    regressed = [t for t in diff["tests"] if t["change"] == "regressed"]
    assert len(regressed) == 1
