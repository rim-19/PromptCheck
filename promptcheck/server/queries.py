"""Read-only aggregation queries for the dashboard API.

These read the same SQLite history DB the CLI writes, so the dashboard is always
in sync with `run` / `watch` results — no separate ingestion step.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def open_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def list_suites(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT suite_name,
               COUNT(*)          AS total_runs,
               COUNT(DISTINCT model_ref) AS model_count,
               MAX(started_at)   AS last_run_at
        FROM runs GROUP BY suite_name ORDER BY last_run_at DESC
        """
    ).fetchall()
    out = []
    for r in rows:
        models = [
            m["model_ref"]
            for m in conn.execute(
                "SELECT DISTINCT model_ref FROM runs WHERE suite_name=?",
                (r["suite_name"],),
            )
        ]
        out.append(
            {
                "name": r["suite_name"],
                "total_runs": r["total_runs"],
                "models": models,
                "last_run_at": r["last_run_at"],
            }
        )
    return out


def _baseline_map(conn: sqlite3.Connection, suite_name: str) -> dict[str, int]:
    return {
        row["model_ref"]: row["run_id"]
        for row in conn.execute(
            "SELECT model_ref, run_id FROM baselines WHERE suite_name=?",
            (suite_name,),
        )
    }


def suite_detail(conn: sqlite3.Connection, name: str) -> dict | None:
    models = [
        r["model_ref"]
        for r in conn.execute(
            "SELECT DISTINCT model_ref FROM runs WHERE suite_name=?", (name,)
        )
    ]
    if not models:
        return None
    baselines = _baseline_map(conn, name)
    model_blocks = []
    for m in models:
        runs = [
            {
                "id": row["id"],
                "started_at": row["started_at"],
                "pass_count": row["pass_count"],
                "total_count": row["total_count"],
                "pass_rate": (
                    row["pass_count"] / row["total_count"]
                    if row["total_count"]
                    else 0
                ),
                "model_version": row["model_version"],
                "is_baseline": row["id"] == baselines.get(m),
            }
            for row in conn.execute(
                "SELECT id, started_at, pass_count, total_count, model_version "
                "FROM runs WHERE suite_name=? AND model_ref=? ORDER BY id ASC",
                (name, m),
            )
        ]
        model_blocks.append(
            {"model_ref": m, "baseline_run_id": baselines.get(m), "runs": runs}
        )
    return {"name": name, "models": model_blocks}


def _results_for(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT test_index, test_label, input, output, passed, latency_ms, "
        "cost_usd, error, assertions_json FROM results WHERE run_id=? "
        "ORDER BY test_index ASC",
        (run_id,),
    ).fetchall()
    out = []
    for r in rows:
        try:
            assertions = json.loads(r["assertions_json"] or "[]")
        except json.JSONDecodeError:
            assertions = []
        out.append(
            {
                "test_index": r["test_index"],
                "test_label": r["test_label"],
                "input": r["input"],
                "output": r["output"],
                "passed": bool(r["passed"]),
                "latency_ms": r["latency_ms"],
                "cost_usd": r["cost_usd"],
                "error": r["error"],
                "assertions": assertions,
            }
        )
    return out


def run_detail(conn: sqlite3.Connection, run_id: int) -> dict | None:
    r = conn.execute(
        "SELECT id, suite_name, source_path, model_ref, model_version, "
        "started_at, pass_count, total_count FROM runs WHERE id=?",
        (run_id,),
    ).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "suite_name": r["suite_name"],
        "model_ref": r["model_ref"],
        "model_version": r["model_version"],
        "started_at": r["started_at"],
        "pass_count": r["pass_count"],
        "total_count": r["total_count"],
        "results": _results_for(conn, run_id),
    }


def run_diff(conn: sqlite3.Connection, base_id: int, cur_id: int) -> dict | None:
    base = run_detail(conn, base_id)
    cur = run_detail(conn, cur_id)
    if base is None or cur is None:
        return None
    base_by_idx = {r["test_index"]: r for r in base["results"]}
    tests = []
    regressions = improvements = 0
    for cr in cur["results"]:
        br = base_by_idx.get(cr["test_index"])
        was = br["passed"] if br else None
        now = cr["passed"]
        change = "same"
        if was is True and now is False:
            change = "regressed"
            regressions += 1
        elif was is False and now is True:
            change = "improved"
            improvements += 1
        elif was is None:
            change = "new"
        tests.append(
            {
                "test_index": cr["test_index"],
                "test_label": cr["test_label"],
                "baseline_passed": was,
                "current_passed": now,
                "change": change,
                "baseline_output": br["output"] if br else None,
                "current_output": cr["output"],
            }
        )
    return {
        "base_run": {
            "id": base["id"],
            "model_version": base["model_version"],
            "pass_count": base["pass_count"],
            "total_count": base["total_count"],
        },
        "current_run": {
            "id": cur["id"],
            "model_version": cur["model_version"],
            "pass_count": cur["pass_count"],
            "total_count": cur["total_count"],
        },
        "version_changed": base["model_version"] != cur["model_version"],
        "regressions": regressions,
        "improvements": improvements,
        "tests": tests,
    }
