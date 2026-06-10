from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from openai_support import OpenAIUnavailable, call_openai_json, string_array_schema
from repo_analysis import RepositoryAnalysis


ENGINEER_SYSTEM_PROMPT = """You are a staff software engineer reviewing a feature request against an existing codebase.

Identify:

* technical ambiguity
* architecture risks
* integration concerns
* missing implementation details
* infrastructure gaps

Return JSON only."""


@dataclass(frozen=True)
class AgentResult:
    output: dict[str, list[str]]
    mode: str
    error: str | None = None


async def run_engineer_agent(feature: str, analysis: RepositoryAnalysis) -> AgentResult:
    try:
        result = await call_openai_json(
            system_prompt=ENGINEER_SYSTEM_PROMPT,
            payload={
                "feature_request": feature,
                "repo_analysis_summary": analysis.architecture_summary,
                "architecture_fit_analysis": analysis.architecture_fit,
            },
            schema_name="engineer_readiness_review",
            schema=string_array_schema(
                ["risks", "missing_infrastructure", "open_questions"]
            ),
        )
        return AgentResult(output=_normalize_engineer_result(result), mode="OpenAI mode")
    except Exception as exc:
        if not isinstance(exc, OpenAIUnavailable):
            error = str(exc)
        else:
            error = str(exc)
        return AgentResult(
            output=await _run_engineer_fallback(feature, analysis),
            mode="fallback mode",
            error=error,
        )


async def _run_engineer_fallback(
    feature: str, analysis: RepositoryAnalysis
) -> dict[str, list[str]]:
    await asyncio.sleep(0)

    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", feature.lower()))
    fit = analysis.architecture_fit
    impacted_modules = list(fit.get("impacted_modules", []))
    missing_infrastructure = list(fit.get("new_infrastructure_required", []))

    risks: list[str] = []
    open_questions: list[str] = []

    if not impacted_modules:
        risks.append("No clearly impacted modules were detected from the repository structure.")

    if fit.get("implementation_complexity") == "high":
        risks.append("Feature appears to span many modules or infrastructure concerns.")
    elif fit.get("implementation_complexity") == "medium":
        risks.append("Feature may require coordination across multiple modules or services.")

    if "tests" not in analysis.architecture_summary:
        risks.append("Test framework or test directory was not confidently detected.")

    if missing_infrastructure:
        risks.append("Feature appears to require infrastructure that was not detected in the repo.")

    if any(word in tokens for word in {"email", "notification", "notifications"}):
        open_questions.append("What retry, failure, and idempotency behavior is required?")

    if any(word in tokens for word in {"migration", "database", "model", "schema"}):
        open_questions.append("What database migration and rollback expectations apply?")

    if any(word in tokens for word in {"auth", "permission", "role", "access"}):
        open_questions.append("Which authorization layer owns this behavior?")

    if any(word in tokens for word in {"webhook", "integration", "sync"}):
        risks.append("External integration behavior may need secrets, retries, and rate-limit handling.")

    if any(word in tokens for word in {"background", "async", "queue", "worker"}):
        if "jobs" not in analysis.architecture_summary:
            missing_infrastructure.append("background job runner")

    if not open_questions:
        open_questions.append("Which existing tests should define the regression boundary?")

    return {
        "risks": _dedupe(risks),
        "missing_infrastructure": _dedupe([str(item) for item in missing_infrastructure]),
        "open_questions": _dedupe(open_questions),
    }


def _normalize_engineer_result(result: dict[str, object]) -> dict[str, list[str]]:
    return {
        "risks": _coerce_string_list(result.get("risks")),
        "missing_infrastructure": _coerce_string_list(result.get("missing_infrastructure")),
        "open_questions": _coerce_string_list(result.get("open_questions")),
    }


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if str(item).strip()])


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
