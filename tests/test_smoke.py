from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.engineer_agent import run_engineer_agent
from agents.pm_agent import run_pm_agent
from agents.synthesis_agent import run_synthesis_agent
from github_repo import RepoFile, RepoSnapshot
from repo_analysis import analyze_repository
from reporting import save_report


def _fallback_report_for(feature: str):
    original_api_key = os.environ.pop("OPENAI_API_KEY", None)
    snapshot = RepoSnapshot(
        full_name="demo/app",
        default_branch="main",
        description="Demo app",
        html_url="https://github.com/demo/app",
        tree_paths=[
            "README.md",
            "app/main.py",
            "requirements.txt",
        ],
        files=[
            RepoFile("README.md", "FastAPI app"),
            RepoFile("requirements.txt", "fastapi\n"),
            RepoFile("app/main.py", "from fastapi import FastAPI"),
        ],
    )
    analysis = analyze_repository(snapshot, feature)

    async def run_agents():
        return await asyncio.gather(
            run_pm_agent(feature, analysis),
            run_engineer_agent(feature, analysis),
        )

    try:
        pm_run, engineer_run = asyncio.run(run_agents())
        synthesis_run = asyncio.run(
            run_synthesis_agent(snapshot, feature, analysis, pm_run.output, engineer_run.output)
        )
    finally:
        if original_api_key is not None:
            os.environ["OPENAI_API_KEY"] = original_api_key

    return synthesis_run.report


def test_smoke_report_generation() -> None:
    original_api_key = os.environ.pop("OPENAI_API_KEY", None)
    snapshot = RepoSnapshot(
        full_name="demo/app",
        default_branch="main",
        description="Demo FastAPI app",
        html_url="https://github.com/demo/app",
        tree_paths=[
            "README.md",
            "app/main.py",
            "app/models.py",
            "tests/test_main.py",
            "requirements.txt",
        ],
        files=[
            RepoFile("README.md", "FastAPI app"),
            RepoFile("requirements.txt", "fastapi\npytest\n"),
            RepoFile("app/main.py", "from fastapi import FastAPI"),
            RepoFile("tests/test_main.py", "def test_ok(): pass"),
        ],
    )
    feature = "Add email notifications when users join projects"
    analysis = analyze_repository(snapshot, feature)

    async def run_agents():
        return await asyncio.gather(
            run_pm_agent(feature, analysis),
            run_engineer_agent(feature, analysis),
        )

    try:
        pm_run, engineer_run = asyncio.run(run_agents())
        synthesis_run = asyncio.run(
            run_synthesis_agent(snapshot, feature, analysis, pm_run.output, engineer_run.output)
        )
    finally:
        if original_api_key is not None:
            os.environ["OPENAI_API_KEY"] = original_api_key

    report = synthesis_run.report

    with tempfile.TemporaryDirectory() as directory:
        report_path = save_report(report, directory)

    assert pm_run.mode == "fallback mode"
    assert engineer_run.mode == "fallback mode"
    assert synthesis_run.mode == "fallback mode"
    assert report.repository == "demo/app"
    assert 0 <= report.score <= 100
    assert report.verdict in {"READY", "NEEDS WORK", "NOT READY"}
    assert report_path.name.endswith(".md")


def test_feature_specific_scoring_examples() -> None:
    reset_report = _fallback_report_for(
        "Add a reset button that clears selected filters when clicked"
    )
    assert 85 <= reset_report.score <= 95
    assert reset_report.verdict == "READY"
    assert reset_report.repo_health_warnings
    assert not any("test framework" in risk.lower() for risk in reset_report.engineering_risks)

    dashboard_reset_report = _fallback_report_for(
        "Add a reset button to the dashboard that clears all filters and returns the phase slider to default position 0-90"
    )
    assert 75 <= dashboard_reset_report.score <= 90
    assert dashboard_reset_report.verdict == "READY"
    assert dashboard_reset_report.testability_analysis["testability_score"] >= 70
    false_positive_terms = ("unsaved", "animation", "alert", "accessibility", "confirmation")
    blocker_text = " ".join(
        dashboard_reset_report.product_gaps + dashboard_reset_report.engineering_risks
    ).lower()
    assert not any(term in blocker_text for term in false_positive_terms)

    intensity_report = _fallback_report_for("Compare player intensity")
    assert 50 <= intensity_report.score <= 65
    assert intensity_report.verdict == "NEEDS WORK"

    ml_report = _fallback_report_for("Add ML predictions")
    assert 25 <= ml_report.score <= 40
    assert ml_report.verdict == "NOT READY"


if __name__ == "__main__":
    test_smoke_report_generation()
    test_feature_specific_scoring_examples()
    print("smoke test passed")
