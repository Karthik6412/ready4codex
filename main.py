from __future__ import annotations

import argparse
import asyncio
import sys

from agents.engineer_agent import run_engineer_agent
from agents.pm_agent import run_pm_agent
from agents.synthesis_agent import run_synthesis_agent
from github_repo import GitHubRepoClient, GitHubRepoError
from repo_analysis import analyze_repository
from reporting import save_report


try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None
    Table = None


async def run_readiness(
    repo_url: str, feature: str, output_dir: str
) -> tuple[object, str, dict[str, str]]:
    client = GitHubRepoClient()
    snapshot = client.fetch(repo_url)
    analysis = analyze_repository(snapshot, feature)

    pm_run, engineer_run = await asyncio.gather(
        run_pm_agent(feature, analysis),
        run_engineer_agent(feature, analysis),
    )

    synthesis_run = await run_synthesis_agent(
        snapshot,
        feature,
        analysis,
        pm_run.output,
        engineer_run.output,
    )
    report = synthesis_run.report
    report_path = save_report(report, output_dir)
    modes = {
        "PM Agent": pm_run.mode,
        "Engineer Agent": engineer_run.mode,
        "Synthesis Agent": synthesis_run.mode,
    }
    return report, str(report_path), modes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ready4codex",
        description="Evaluate whether a feature request is ready for agentic implementation.",
    )
    parser.add_argument("--repo", required=True, help="Public GitHub repo URL or owner/repo.")
    parser.add_argument("--feature", required=True, help="Plain-English feature request.")
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory where Markdown readiness reports are saved.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        report, report_path, modes = asyncio.run(
            run_readiness(args.repo, args.feature, args.output_dir)
        )
    except GitHubRepoError as exc:
        _print_error(str(exc))
        return 2
    except KeyboardInterrupt:
        _print_error("Interrupted.")
        return 130

    _print_summary(report, report_path, modes)
    return 0


def _print_summary(report: object, report_path: str, modes: dict[str, str]) -> None:
    if Console and Table:
        console = Console()
        table = Table(title="READY4CODEX REPORT")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Repository", str(report.repository))
        table.add_row("Feature", str(report.feature))
        table.add_row("ARS", f"{report.score} / 100")
        table.add_row("Verdict", str(report.verdict))
        for agent, mode in modes.items():
            table.add_row(agent, mode)
        table.add_row("Saved Report", report_path)
        console.print(table)
        return

    print("READY4CODEX REPORT")
    print(f"Repository: {report.repository}")
    print(f"Feature: {report.feature}")
    print(f"ARS: {report.score} / 100")
    print(f"Verdict: {report.verdict}")
    for agent, mode in modes.items():
        print(f"{agent}: {mode}")
    print(f"Saved Report: {report_path}")


def _print_error(message: str) -> None:
    if Console:
        Console(stderr=True).print(f"[red]Error:[/red] {message}")
    else:
        print(f"Error: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
