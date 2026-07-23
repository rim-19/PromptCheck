"""SQLite persistence. One local DB (default .promptcheck/history.db) holds
every run and result, so later phases (history, drift, dashboard) read the
same source of truth.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .runner import SuiteRun

DEFAULT_DB = Path(".promptcheck/history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_name TEXT NOT NULL,
    source_path TEXT,
    model_ref TEXT NOT NULL,
    model_version TEXT,
    started_at TEXT NOT NULL,
    pass_count INTEGER NOT NULL,
    total_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    test_index INTEGER NOT NULL,
    test_label TEXT,
    input TEXT,
    output TEXT,
    passed INTEGER NOT NULL,
    latency_ms INTEGER,
    cost_usd REAL,
    error TEXT,
    assertions_json TEXT
);
CREATE TABLE IF NOT EXISTS baselines (
    suite_name TEXT NOT NULL,
    model_ref TEXT NOT NULL,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    set_at TEXT NOT NULL,
    PRIMARY KEY (suite_name, model_ref)
);
CREATE INDEX IF NOT EXISTS idx_runs_suite ON runs(suite_name, started_at);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
"""


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(_SCHEMA)
    return conn


def save_run(conn: sqlite3.Connection, suite_run: SuiteRun) -> list[int]:
    """Persist a SuiteRun as one `runs` row per model. Returns the run ids."""
    now = datetime.now(timezone.utc).isoformat()
    suite = suite_run.suite
    run_ids: list[int] = []
    for mr in suite_run.model_runs:
        version = mr.results[0].model_version if mr.results else ""
        cur = conn.execute(
            "INSERT INTO runs (suite_name, source_path, model_ref, model_version, "
            "started_at, pass_count, total_count) VALUES (?,?,?,?,?,?,?)",
            (
                suite.name,
                suite.source_path,
                mr.model_ref,
                version,
                now,
                mr.pass_count,
                mr.total,
            ),
        )
        run_id = cur.lastrowid
        run_ids.append(run_id)
        for r in mr.results:
            conn.execute(
                "INSERT INTO results (run_id, test_index, test_label, input, output, "
                "passed, latency_ms, cost_usd, error, assertions_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    r.test_index,
                    r.test_label,
                    r.input,
                    r.output,
                    int(r.passed),
                    r.latency_ms,
                    r.cost_usd,
                    r.error,
                    json.dumps(
                        [
                            {
                                "assertion": a.assertion,
                                "passed": a.passed,
                                "reason": a.reason,
                                "judge_model": a.judge_model,
                                "errored": a.errored,
                            }
                            for a in r.assertion_results
                        ]
                    ),
                ),
            )
    conn.commit()
    return run_ids


@dataclass
class RunRow:
    id: int
    suite_name: str
    model_ref: str
    model_version: str
    started_at: str
    pass_count: int
    total_count: int


def _row_to_run(row: tuple) -> RunRow:
    return RunRow(*row)


_RUN_COLS = "id, suite_name, model_ref, model_version, started_at, pass_count, total_count"


def latest_run(
    conn: sqlite3.Connection, suite_name: str, model_ref: str
) -> RunRow | None:
    row = conn.execute(
        f"SELECT {_RUN_COLS} FROM runs WHERE suite_name=? AND model_ref=? "
        "ORDER BY id DESC LIMIT 1",
        (suite_name, model_ref),
    ).fetchone()
    return _row_to_run(row) if row else None


def get_run(conn: sqlite3.Connection, run_id: int) -> RunRow | None:
    row = conn.execute(
        f"SELECT {_RUN_COLS} FROM runs WHERE id=?", (run_id,)
    ).fetchone()
    return _row_to_run(row) if row else None


def list_runs(
    conn: sqlite3.Connection, suite_name: str, model_ref: str, limit: int = 20
) -> list[RunRow]:
    rows = conn.execute(
        f"SELECT {_RUN_COLS} FROM runs WHERE suite_name=? AND model_ref=? "
        "ORDER BY id ASC LIMIT ?",
        (suite_name, model_ref, limit),
    ).fetchall()
    return [_row_to_run(r) for r in rows]


def run_test_status(conn: sqlite3.Connection, run_id: int) -> dict[int, dict]:
    """Return {test_index: {passed, label, output, error, errored}} for a run.

    `errored` is True when the result couldn't be evaluated at all — either the
    model call failed or a judged assertion failed to get a verdict.
    """
    rows = conn.execute(
        "SELECT test_index, test_label, passed, output, error, assertions_json "
        "FROM results WHERE run_id=?",
        (run_id,),
    ).fetchall()
    out_map = {}
    for idx, label, p, out, err, aj in rows:
        try:
            assertions = json.loads(aj or "[]")
        except json.JSONDecodeError:
            assertions = []
        judge_errored = any(a.get("errored") for a in assertions)
        out_map[idx] = {
            "passed": bool(p),
            "label": label,
            "output": out,
            "error": err,
            "errored": bool(err) or judge_errored,
        }
    return out_map


def models_for_suite(conn: sqlite3.Connection, suite_name: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT model_ref FROM runs WHERE suite_name=?", (suite_name,)
    ).fetchall()
    return [r[0] for r in rows]


# --- baselines -----------------------------------------------------------

def set_baseline(
    conn: sqlite3.Connection, suite_name: str, model_ref: str, run_id: int
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO baselines (suite_name, model_ref, run_id, set_at) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(suite_name, model_ref) DO UPDATE SET run_id=?, set_at=?",
        (suite_name, model_ref, run_id, now, run_id, now),
    )
    conn.commit()


def get_baseline_run_id(
    conn: sqlite3.Connection, suite_name: str, model_ref: str
) -> int | None:
    row = conn.execute(
        "SELECT run_id FROM baselines WHERE suite_name=? AND model_ref=?",
        (suite_name, model_ref),
    ).fetchone()
    return row[0] if row else None
