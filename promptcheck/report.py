"""Terminal reporting via Rich."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .runner import ModelRun, SuiteRun

console = Console()


def _status(passed: bool, error: str | None) -> Text:
    if error:
        return Text("ERROR", style="bold yellow")
    return Text("PASS", style="bold green") if passed else Text("FAIL", style="bold red")


def render_model_run(mr: ModelRun) -> Table:
    table = Table(
        title=f"[bold]{mr.model_ref}[/]  —  {mr.pass_count}/{mr.total} passed",
        title_justify="left",
        expand=True,
        header_style="bold",
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("Test", overflow="ellipsis", max_width=32)
    table.add_column("Result", width=6)
    table.add_column("Detail", overflow="fold")
    table.add_column("ms", justify="right", width=6)

    for r in mr.results:
        if r.error:
            # Collapse multi-line API error bodies to a compact one-liner.
            compact = " ".join(r.error.split())
            if len(compact) > 90:
                compact = compact[:90] + "…"
            detail = f"[yellow]{compact}[/]"
        elif r.passed:
            detail = f"[dim]→ {r.output.strip()[:60]}[/]"
        else:
            fails = [a for a in r.assertion_results if not a.passed]
            detail = "; ".join(f"[red]{a.assertion}[/]: {a.reason}" for a in fails)
        table.add_row(
            str(r.test_index),
            r.test_label,
            _status(r.passed, r.error),
            detail,
            str(r.latency_ms or "-"),
        )
    return table


def render_suite_run(suite_run: SuiteRun) -> None:
    console.print()
    console.rule(f"[bold cyan]{suite_run.suite.name}[/]")
    if suite_run.suite.description:
        console.print(f"[dim]{suite_run.suite.description}[/]")
    for mr in suite_run.model_runs:
        console.print()
        console.print(render_model_run(mr))


def _cell(passed: bool, error: str | None) -> str:
    if error:
        return "[yellow]ERR[/]"
    return "[green]PASS[/]" if passed else "[red]FAIL[/]"


def render_compare_matrix(suite_run: SuiteRun) -> None:
    """Side-by-side matrix: tests as rows, models as columns. Rows where models
    disagree are marked, so 'Model A passes what Model B fails' pops out."""
    suite = suite_run.suite
    models = [mr.model_ref for mr in suite_run.model_runs]
    # index results by (model_ref, test_index)
    grid: dict[tuple[str, int], object] = {}
    for mr in suite_run.model_runs:
        for r in mr.results:
            grid[(mr.model_ref, r.test_index)] = r

    console.print()
    console.rule(f"[bold cyan]compare · {suite.name}[/]")

    table = Table(expand=True, header_style="bold")
    table.add_column("#", justify="right", width=3)
    table.add_column("Test", overflow="ellipsis", max_width=28)
    for m in models:
        table.add_column(m.split("/")[-1], justify="center")
    table.add_column("", width=3)  # divergence marker

    n_tests = len(suite.tests)
    divergent = 0
    for i in range(n_tests):
        cells = []
        outcomes = []
        for m in models:
            r = grid.get((m, i))
            if r is None:
                cells.append("-")
                outcomes.append(None)
            else:
                cells.append(_cell(r.passed, r.error))
                outcomes.append(None if r.error else r.passed)
        real = [o for o in outcomes if o is not None]
        disagree = len(set(real)) > 1
        if disagree:
            divergent += 1
        marker = "[bold yellow]≠[/]" if disagree else ""
        label = suite.tests[i].label
        table.add_row(str(i), label, *cells, marker)

    console.print(table)
    # per-model totals
    totals = "   ".join(
        f"{mr.model_ref.split('/')[-1]}: {mr.pass_count}/{mr.total}"
        for mr in suite_run.model_runs
    )
    console.print(f"[dim]{totals}[/]")
    if divergent:
        console.print(
            f"[yellow]⚠ {divergent} test(s) where models disagree (≠)[/] — "
            "these are the decisions a model switch would change."
        )
    else:
        console.print("[green]Models agree on every test.[/]")


_SPARK = "▁▂▃▄▅▆▇█"


def _sparkline(rates: list[float]) -> str:
    """Turn a list of 0..1 pass rates into a unicode sparkline."""
    if not rates:
        return ""
    out = []
    for r in rates:
        idx = min(len(_SPARK) - 1, max(0, round(r * (len(_SPARK) - 1))))
        out.append(_SPARK[idx])
    return "".join(out)


def render_watch(diffs: list) -> bool:
    """Render drift diffs. Returns True if clean (no regressions)."""
    console.print()
    console.rule("[bold cyan]watch · drift vs. baseline[/]")
    clean = True

    for d in diffs:
        model = d.model_ref.split("/")[-1]

        if d.seeded:
            console.print(
                Panel(
                    f"No baseline existed — pinned this run "
                    f"([green]{d.current_pass}/{d.current_total}[/]) as the baseline.\n"
                    f"[dim]Future `watch` runs will compare against it.[/]",
                    title=f"[bold]{model}[/] · baseline established",
                    border_style="blue",
                )
            )
            continue

        lines: list[str] = []
        delta = d.current_pass - (d.baseline_pass or 0)
        arrow = "→"
        rate_str = (
            f"{d.baseline_pass}/{d.current_total} {arrow} "
            f"{d.current_pass}/{d.current_total}"
        )
        if delta < 0:
            lines.append(f"[red]Pass rate dropped:[/] {rate_str}  ({delta})")
        elif delta > 0:
            lines.append(f"[green]Pass rate improved:[/] {rate_str}  (+{delta})")
        else:
            lines.append(f"Pass rate steady: {rate_str}")

        if d.version_changed:
            lines.append(
                f"[yellow]⚠ model version changed:[/] "
                f"{d.baseline_version} {arrow} {d.current_version}"
            )

        if d.regressions:
            clean = False
            lines.append(f"\n[bold red]REGRESSIONS ({len(d.regressions)}):[/]")
            for idx, label in d.regressions:
                lines.append(f"  [red]✗[/] #{idx} {label}  (passed in baseline, fails now)")

        if d.improvements:
            lines.append(f"\n[green]Improvements ({len(d.improvements)}):[/]")
            for idx, label in d.improvements:
                lines.append(f"  [green]✓[/] #{idx} {label}  (failed in baseline, passes now)")

        border = "red" if d.regressions else ("yellow" if d.version_changed else "green")
        title = f"[bold]{model}[/] · " + (
            "[red]REGRESSED[/]" if d.regressions else "[green]OK[/]"
        )
        console.print(Panel("\n".join(lines), title=title, border_style=border))

    if clean:
        console.print("[green]✓ No regressions vs. baseline.[/]")
    else:
        console.print("[bold red]✗ Regressions detected — see above.[/]")
    return clean


def watch_markdown(suite_name: str, diffs: list) -> str:
    """Plain-markdown summary of drift, suitable for a GitHub issue body."""
    lines = [f"## PromptCheck drift · `{suite_name}`", ""]
    any_regression = False
    any_version_change = False
    for d in diffs:
        if d.seeded:
            lines.append(
                f"- **{d.model_ref}** — baseline established "
                f"({d.current_pass}/{d.current_total})."
            )
            continue
        delta = d.current_pass - (d.baseline_pass or 0)
        status = "🔴 REGRESSED" if d.regressions else "🟢 OK"
        lines.append(
            f"### {d.model_ref} — {status}\n"
            f"- Pass rate: {d.baseline_pass}/{d.current_total} → "
            f"{d.current_pass}/{d.current_total} ({delta:+d})"
        )
        if d.version_changed:
            any_version_change = True
            lines.append(
                f"- ⚠ **model version changed:** "
                f"`{d.baseline_version}` → `{d.current_version}`"
            )
        if d.regressions:
            any_regression = True
            lines.append("- **Regressions (passed in baseline, fail now):**")
            for idx, label in d.regressions:
                lines.append(f"  - ✗ #{idx} {label}")
        if d.improvements:
            lines.append("- Improvements:")
            for idx, label in d.improvements:
                lines.append(f"  - ✓ #{idx} {label}")
        lines.append("")

    header = []
    if any_regression:
        header.append("**Regressions detected.**")
    if any_version_change:
        header.append("**Model version changed.**")
    if header:
        lines.insert(1, " ".join(header) + "\n")
    return "\n".join(lines)


def render_history(suite_name: str, per_model: dict) -> None:
    """per_model: {model_ref: (list[RunRow], baseline_run_id)}"""
    console.print()
    console.rule(f"[bold cyan]history · {suite_name}[/]")
    for model_ref, (runs, baseline_id) in per_model.items():
        console.print()
        console.print(f"[bold]{model_ref}[/]")
        if not runs:
            console.print("  [dim]no runs recorded[/]")
            continue
        rates = [(r.pass_count / r.total_count if r.total_count else 0) for r in runs]
        spark = _sparkline(rates)
        console.print(f"  pass-rate trend: [cyan]{spark}[/]")
        table = Table(box=None, pad_edge=False, show_edge=False)
        table.add_column("when", style="dim")
        table.add_column("pass", justify="right")
        table.add_column("version", style="dim")
        table.add_column("", width=10)
        for r in runs:
            marker = "[blue]← baseline[/]" if r.id == baseline_id else ""
            ok = r.pass_count == r.total_count
            style = "green" if ok else "red"
            table.add_row(
                r.started_at[:19].replace("T", " "),
                f"[{style}]{r.pass_count}/{r.total_count}[/]",
                r.model_version,
                marker,
            )
        console.print(table)


def render_summary(runs: list[SuiteRun]) -> bool:
    """Print an overall summary. Returns True if everything passed."""
    console.print()
    console.rule("[bold]Summary[/]")
    all_pass = True
    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Suite")
    table.add_column("Model")
    table.add_column("Pass rate", justify="right")
    for sr in runs:
        for mr in sr.model_runs:
            rate = f"{mr.pass_count}/{mr.total}"
            ok = mr.pass_count == mr.total
            all_pass = all_pass and ok
            style = "green" if ok else "red"
            table.add_row(sr.suite.name, mr.model_ref, f"[{style}]{rate}[/]")
    console.print(table)
    return all_pass
