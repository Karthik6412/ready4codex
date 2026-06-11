from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from agents.synthesis_agent import ReadinessReport


def render_markdown(report: ReadinessReport) -> str:
    lines = [
        "# READY4CODEX REPORT",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Repository",
        "",
        report.repository,
        "",
        "## Feature",
        "",
        report.feature,
        "",
        "## Agentic Readiness Score (ARS)",
        "",
        f"{report.score} / 100",
        "",
        "## Verdict",
        "",
        report.verdict,
        "",
        "## Product Gaps",
        "",
        _markdown_list(report.product_gaps),
        "",
        "## Engineering Risks",
        "",
        _markdown_list(report.engineering_risks),
        "",
        "## Repo Health Warnings",
        "",
        _markdown_list(report.repo_health_warnings),
        "",
        "## Architecture Fit Analysis",
        "",
        _markdown_dict(report.architecture_fit),
        "",
        "## Testability Analysis",
        "",
        _markdown_dict(report.testability_analysis),
        "",
        "## Suggested Agent Plan",
        "",
        _markdown_agent_plan(report.suggested_agent_plan),
        "",
        "## Codex-Ready Prompt",
        "",
        "```text",
        report.codex_ready_prompt,
        "```",
        "",
        "## Architecture Summary",
        "",
        _markdown_dict(report.architecture_summary),
        "",
        "## Inspected Files",
        "",
        _markdown_list(report.inspected_files),
        "",
    ]
    return "\n".join(lines)


def save_report(report: ReadinessReport, output_dir: str = "reports") -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    slug = _slugify(f"{report.repository}-{report.feature}")[:80]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = directory / f"{timestamp}-{slug}.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


def _markdown_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _markdown_dict(value: dict[str, object]) -> str:
    if not value:
        return "- None"
    lines = []
    for key, item in value.items():
        if isinstance(item, list):
            lines.append(f"- {key}:")
            if item:
                lines.extend(f"  - {entry}" for entry in item)
            else:
                lines.append("  - None")
        else:
            lines.append(f"- {key}: {item}")
    return "\n".join(lines)


def _markdown_agent_plan(plan: list[dict[str, object]]) -> str:
    if not plan:
        return "- None"
    lines: list[str] = []
    for item in plan:
        lines.append(f"### {item.get('agent', 'Agent')}")
        lines.append("")
        lines.append(str(item.get("responsibility", "Unspecified responsibility")))
        lines.append("")
        lines.append("Files:")
        files = item.get("files", [])
        if isinstance(files, list) and files:
            lines.extend(f"- {path}" for path in files)
        else:
            lines.append("- None")
        lines.append("")
    return "\n".join(lines).rstrip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "ready4codex-report"
