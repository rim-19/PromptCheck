"""Compare a fresh run against a pinned baseline and detect regressions.

A *regression* is a test that passed in the baseline but fails now. Improvements
(newly passing tests) are reported but never fail the check. A change in the
resolved model version is surfaced explicitly — that's the "a provider silently
shipped an update" signal this whole tool exists for.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import store
from .runner import ModelRun


@dataclass
class ModelDiff:
    model_ref: str
    seeded: bool  # no baseline existed; this run became the baseline
    current_pass: int
    current_total: int
    baseline_pass: int | None
    baseline_version: str | None
    current_version: str
    regressions: list[tuple[int, str]] = field(default_factory=list)  # (idx, label)
    improvements: list[tuple[int, str]] = field(default_factory=list)

    @property
    def version_changed(self) -> bool:
        return (
            self.baseline_version is not None
            and self.baseline_version != self.current_version
        )

    @property
    def has_regression(self) -> bool:
        return bool(self.regressions)


def diff_against_baseline(
    conn: sqlite3.Connection,
    suite_name: str,
    model_run: ModelRun,
    current_run_id: int,
    auto_seed: bool = True,
) -> ModelDiff:
    model_ref = model_run.model_ref
    current_version = model_run.results[0].model_version if model_run.results else ""
    baseline_id = store.get_baseline_run_id(conn, suite_name, model_ref)

    # First time we've ever watched this model: seed the baseline and pass.
    if baseline_id is None:
        if auto_seed:
            store.set_baseline(conn, suite_name, model_ref, current_run_id)
        return ModelDiff(
            model_ref=model_ref,
            seeded=True,
            current_pass=model_run.pass_count,
            current_total=model_run.total,
            baseline_pass=None,
            baseline_version=None,
            current_version=current_version,
        )

    base_status = store.run_test_status(conn, baseline_id)
    base_meta = store.get_run(conn, baseline_id)
    base_pass = base_meta.pass_count if base_meta else None
    base_version = base_meta.model_version if base_meta else None

    regressions: list[tuple[int, str]] = []
    improvements: list[tuple[int, str]] = []
    for r in model_run.results:
        base = base_status.get(r.test_index)
        if base is None:
            continue  # test didn't exist in baseline; ignore for drift
        was = base["passed"]
        now = r.passed
        if was and not now:
            regressions.append((r.test_index, r.test_label))
        elif not was and now:
            improvements.append((r.test_index, r.test_label))

    return ModelDiff(
        model_ref=model_ref,
        seeded=False,
        current_pass=model_run.pass_count,
        current_total=model_run.total,
        baseline_pass=base_pass,
        baseline_version=base_version,
        current_version=current_version,
        regressions=regressions,
        improvements=improvements,
    )
