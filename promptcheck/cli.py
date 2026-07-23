"""PromptCheck command-line interface."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

# Windows terminals often default to a legacy codepage (cp1252) that can't
# encode the Unicode used in reports. Force UTF-8 so output never crashes.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from . import __version__
from . import store
from .config import SuiteError, discover_suites, load_suite
from .drift import diff_against_baseline
from .report import (
    render_compare_matrix,
    render_history,
    render_suite_run,
    render_summary,
    render_watch,
    render_watch_verdict,
    watch_markdown,
)
from .runner import run_suite
from .store import connect, save_run

app = typer.Typer(
    add_completion=False,
    help="Regression monitoring for AI prompts. Write test cases, run them "
    "against any model, catch drift before your users do.",
    no_args_is_help=True,
)
console = Console()

load_dotenv()  # pick up .env from cwd

_SAMPLE = """\
name: refund-email-classifier
description: Classifies inbound support emails into refund | bug | question.
prompt: |
  You are a support-triage assistant. Classify the email below into exactly
  one of these labels: refund, bug, question.
  Reply with ONLY the single lowercase label and nothing else.

  Email:
  {{ input }}

models:
  # Small, fast models with generous free daily limits — ideal for a test
  # tool that makes many calls. Swap in larger models when you need them.
  - gemini/gemini-flash-lite-latest
  - groq/llama-3.1-8b-instant

# Model that grades `llm_rubric` (fuzzy) assertions. Pin it and leave it fixed
# so the judge itself doesn't drift. Defaults to the first model if omitted.
judge: gemini/gemini-flash-lite-latest

defaults:
  temperature: 0
  max_tokens: 16

tests:
  - name: angry refund
    input: "This is unacceptable. I demand my money back immediately."
    assert:
      - type: equals
        value: refund

  - name: broken checkout
    input: "The checkout button does nothing when I click it on Safari."
    assert:
      - type: equals
        value: bug

  - name: general inquiry
    input: "Do you ship to Canada, and how long does delivery take?"
    assert:
      - type: equals
        value: question

  - name: polite refund
    input: "Hi, I'd like to return my order and get a refund please. Order #4821."
    assert:
      - type: equals
        value: refund

  - name: not-a-bug rant
    input: "Your prices are way too high compared to competitors!"
    assert:
      # Fuzzy check judged by another model — the label just shouldn't be 'bug'.
      - type: llm_rubric
        value: "The label is 'refund' or 'question', not 'bug'."
"""


@app.command()
def version() -> None:
    """Print the PromptCheck version."""
    console.print(f"promptcheck {__version__}")


@app.command()
def init(
    path: Path = typer.Option(
        Path("examples/refund_classifier.yaml"),
        "--path",
        "-p",
        help="Where to write the sample suite.",
    ),
) -> None:
    """Scaffold a sample test suite to get started."""
    if path.exists():
        console.print(f"[yellow]Refusing to overwrite existing file:[/] {path}")
        raise typer.Exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SAMPLE, encoding="utf-8")
    console.print(f"[green]Created[/] {path}")
    console.print(f"Now run:  [bold]promptcheck run {path}[/]")


@app.command()
def run(
    target: str = typer.Argument(
        "examples",
        help="A suite file, a directory of suites, or a glob.",
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", min=1, max=20),
    no_store: bool = typer.Option(
        False, "--no-store", help="Do not persist results to the local history DB."
    ),
    db: Path = typer.Option(
        Path(".promptcheck/history.db"), "--db", help="Path to the history DB."
    ),
) -> None:
    """Run one or more test suites and report pass/fail."""
    suite_files = discover_suites(target)
    if not suite_files:
        console.print(f"[red]No suite files (*.yaml) found at:[/] {target}")
        raise typer.Exit(1)

    conn = None if no_store else connect(db)
    all_runs = []
    try:
        for f in suite_files:
            try:
                suite = load_suite(f)
            except SuiteError as e:
                console.print(f"[red]Skipping invalid suite[/] {f}:\n{e}")
                continue
            suite_run = asyncio.run(run_suite(suite, concurrency=concurrency))
            render_suite_run(suite_run)
            if conn is not None:
                save_run(conn, suite_run)
            all_runs.append(suite_run)
    finally:
        if conn is not None:
            conn.close()

    if not all_runs:
        raise typer.Exit(1)

    all_pass = render_summary(all_runs)
    if conn is not None:
        console.print(f"\n[dim]Results saved to {db}[/]")
    # Non-zero exit on any failure so CI / cron can gate on it.
    raise typer.Exit(0 if all_pass else 1)


@app.command()
def compare(
    target: str = typer.Argument(
        ..., help="Suite file, directory, or glob to compare across models."
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", min=1, max=20),
) -> None:
    """Run suites across all their models and show a side-by-side matrix,
    highlighting the tests where models disagree."""
    suites = _load_many(target)
    compared = 0
    for suite in suites:
        if len(suite.models) < 2:
            console.print(
                f"[dim]Skipping '{suite.name}' — compare needs 2+ models, "
                f"it has {len(suite.models)}.[/]"
            )
            continue
        suite_run = asyncio.run(run_suite(suite, concurrency=concurrency))
        render_compare_matrix(suite_run)
        compared += 1
    if compared == 0:
        console.print("[yellow]No suites with 2+ models to compare.[/]")
        raise typer.Exit(1)


def _load_many(target: str) -> list:
    """Resolve a file, directory, or glob into a list of loaded suites.

    Invalid suites are reported and skipped; exits if nothing loads.
    """
    suite_files = discover_suites(target)
    if not suite_files:
        console.print(f"[red]No suite files (*.yaml) found at:[/] {target}")
        raise typer.Exit(1)
    suites = []
    for f in suite_files:
        try:
            suites.append(load_suite(f))
        except SuiteError as e:
            console.print(f"[red]Skipping invalid suite[/] {f}:\n{e}")
    if not suites:
        console.print("[red]No valid suites to run.[/]")
        raise typer.Exit(1)
    return suites


baseline_app = typer.Typer(help="Manage drift baselines.", no_args_is_help=True)
app.add_typer(baseline_app, name="baseline")


@baseline_app.command("set")
def baseline_set(
    target: str = typer.Argument(
        ..., help="Suite file, directory, or glob to baseline."
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", min=1, max=20),
    db: Path = typer.Option(Path(".promptcheck/history.db"), "--db"),
) -> None:
    """Run suites now and pin each result as the baseline for its models."""
    suites = _load_many(target)
    conn = connect(db)
    try:
        for suite in suites:
            suite_run = asyncio.run(run_suite(suite, concurrency=concurrency))
            render_suite_run(suite_run)
            run_ids = save_run(conn, suite_run)
            for mr, run_id in zip(suite_run.model_runs, run_ids):
                store.set_baseline(conn, suite.name, mr.model_ref, run_id)
                console.print(
                    f"[blue]baseline set[/] {suite.name} · {mr.model_ref} "
                    f"→ {mr.pass_count}/{mr.total} (run #{run_id})"
                )
    finally:
        conn.close()


@baseline_app.command("show")
def baseline_show(
    target: str = typer.Argument(..., help="Suite file, directory, or glob."),
    db: Path = typer.Option(Path(".promptcheck/history.db"), "--db"),
) -> None:
    """Show the current baseline for each model in each suite."""
    suites = _load_many(target)
    conn = connect(db)
    try:
        for suite in suites:
            console.print(f"\n[bold]{suite.name}[/]")
            any_found = False
            for model_ref in suite.models:
                run_id = store.get_baseline_run_id(conn, suite.name, model_ref)
                if run_id is None:
                    console.print(f"  [dim]{model_ref}: no baseline[/]")
                    continue
                any_found = True
                run = store.get_run(conn, run_id)
                console.print(
                    f"  [blue]{model_ref}[/]: run #{run_id} · "
                    f"{run.pass_count}/{run.total_count} · {run.model_version} · "
                    f"{run.started_at[:19].replace('T', ' ')}"
                )
            if not any_found:
                console.print(
                    f"  [yellow]No baselines yet.[/] Run: "
                    f"[bold]promptcheck baseline set {target}[/]"
                )
    finally:
        conn.close()


@app.command()
def watch(
    target: str = typer.Argument(
        ..., help="Suite file, directory, or glob to check for drift."
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", min=1, max=20),
    db: Path = typer.Option(Path(".promptcheck/history.db"), "--db"),
    summary_file: Path = typer.Option(
        None,
        "--summary-file",
        help="Write a plain-markdown drift summary here (for CI / issue bodies).",
    ),
) -> None:
    """Run suites and compare each against its baseline. Exits non-zero if any
    test regressed (passed in the baseline, fails now). Seeds a baseline on
    first run. Accepts a file, a directory, or a glob."""
    suites = _load_many(target)
    all_clean = True
    sections: list[str] = []

    conn = connect(db)
    try:
        for suite in suites:
            suite_run = asyncio.run(run_suite(suite, concurrency=concurrency))
            run_ids = save_run(conn, suite_run)
            diffs = [
                diff_against_baseline(conn, suite.name, mr, run_id)
                for mr, run_id in zip(suite_run.model_runs, run_ids)
            ]
            if not render_watch(suite.name, diffs):
                all_clean = False
            sections.append(watch_markdown(suite.name, diffs))
    finally:
        conn.close()

    render_watch_verdict(all_clean, len(suites))
    if summary_file:
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
    raise typer.Exit(0 if all_clean else 1)


@app.command()
def serve(
    db: Path = typer.Option(Path(".promptcheck/history.db"), "--db"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", "-p"),
) -> None:
    """Launch the dashboard (FastAPI + built React frontend) over the history DB."""
    try:
        import uvicorn

        from .server.app import create_app
    except ImportError:
        console.print(
            "[red]Server extras not installed.[/] Run: "
            "[bold]pip install -e \".[server]\"[/]"
        )
        raise typer.Exit(1)

    application = create_app(db)
    console.print(f"[green]PromptCheck dashboard[/] → http://{host}:{port}")
    console.print(f"[dim]Reading {db}[/]")
    uvicorn.run(application, host=host, port=port, log_level="warning")


@app.command()
def history(
    target: str = typer.Argument(..., help="Suite file, directory, or glob."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max runs per model."),
    db: Path = typer.Option(Path(".promptcheck/history.db"), "--db"),
) -> None:
    """Show pass-rate history over time for each model in each suite."""
    suites = _load_many(target)
    conn = connect(db)
    try:
        for suite in suites:
            models = suite.models or store.models_for_suite(conn, suite.name)
            per_model = {}
            for model_ref in models:
                runs = store.list_runs(conn, suite.name, model_ref, limit=limit)
                baseline_id = store.get_baseline_run_id(conn, suite.name, model_ref)
                per_model[model_ref] = (runs, baseline_id)
            render_history(suite.name, per_model)
    finally:
        conn.close()


if __name__ == "__main__":
    app()
