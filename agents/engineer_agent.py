from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from openai_support import OpenAIUnavailable, call_openai_json, string_array_schema
from repo_analysis import RepositoryAnalysis
from sanitizer import sanitize_engineer_output


ENGINEER_SYSTEM_PROMPT = """You are a staff software engineer reviewing a feature request against an existing codebase.

Identify:

* technical ambiguity
* architecture risks
* integration concerns
* missing implementation details
* infrastructure gaps

Only flag risks directly relevant to implementing the requested feature.
Do not treat optional UX improvements, future scalability concerns, or hypothetical edge cases as blocking risks.
Put non-blocking enhancement suggestions or follow-up considerations in open_questions, not risks.
Do not include general repo health issues as implementation risks unless they directly block this feature.
Context applicability check:
- If the repo appears to be a simple dashboard/data visualization app with no user accounts, database writes, persistence/save workflow, or editing workflow, do not flag unsaved changes, confirmation dialogs, save/discard behavior, or data persistence behavior as implementation risks.
- Animations, alerts, visual feedback, accessibility, disabled states, and confirmation dialogs are UX polish unless the feature explicitly asks for them.

Return JSON only."""


@dataclass(frozen=True)
class AgentResult:
    output: dict[str, list[str]]
    mode: str
    error: str | None = None
    sanitizer_removed: tuple[str, ...] = ()


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
        sanitized = sanitize_engineer_output(result, feature, analysis)
        return AgentResult(
            output=sanitized.output,
            mode="OpenAI mode",
            sanitizer_removed=sanitized.removed,
        )
    except Exception as exc:
        if not isinstance(exc, OpenAIUnavailable):
            error = str(exc)
        else:
            error = str(exc)
        fallback_output = await _run_engineer_fallback(feature, analysis)
        sanitized = sanitize_engineer_output(fallback_output, feature, analysis)
        return AgentResult(
            output=sanitized.output,
            mode="fallback mode",
            error=error,
            sanitizer_removed=sanitized.removed,
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
        open_questions.append("Which existing module should own this change?")

    if fit.get("implementation_complexity") == "high":
        risks.append("Feature appears to span many modules or infrastructure concerns.")
    elif fit.get("implementation_complexity") == "medium":
        open_questions.append("Feature may require coordination across multiple modules or services.")

    if "tests" not in analysis.architecture_summary:
        open_questions.append("Test framework or test directory was not confidently detected.")

    if missing_infrastructure:
        open_questions.append("Feature appears to require infrastructure that was not detected in the repo.")

    if any(word in tokens for word in {"email", "notification", "notifications"}):
        open_questions.append("Retry, failure, and idempotency behavior can be defined after the delivery channel is chosen.")

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


def _normalize_engineer_result(
    result: dict[str, object], feature: str, analysis: RepositoryAnalysis
) -> dict[str, list[str]]:
    risks: list[str] = []
    open_questions = _coerce_string_list(result.get("open_questions"))

    for item in _coerce_string_list(result.get("risks")):
        if _is_non_blocking_engineering_item(item) or _is_inapplicable_persistence_item(
            item, feature, analysis
        ):
            if _is_directly_relevant_followup(item, feature):
                open_questions.append(item)
            continue
        risks.append(item)

    return {
        "risks": _dedupe(risks),
        "missing_infrastructure": _coerce_string_list(result.get("missing_infrastructure")),
        "open_questions": _dedupe(open_questions),
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


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower()))


def _is_non_blocking_engineering_item(item: str) -> bool:
    value = item.lower()
    non_blocking_terms = (
        "animation",
        "animations",
        "alert",
        "alerts",
        "visual feedback",
        "accessibility",
        "disabled state",
        "disabled states",
        "confirmation dialog",
        "confirmation dialogs",
        "confirm dialog",
        "toast",
        "loading state",
        "hover",
        "focus state",
        "future scalability",
        "optional ux",
    )
    return any(term in value for term in non_blocking_terms)


def _is_inapplicable_persistence_item(
    item: str, feature: str, analysis: RepositoryAnalysis
) -> bool:
    value = item.lower()
    persistence_terms = (
        "unsaved",
        "save",
        "discard",
        "persistence",
        "persist",
        "stored",
        "database",
        "data loss",
    )
    if not any(term in value for term in persistence_terms):
        return False
    return _is_simple_dashboard_ui_feature(feature) and not _repo_has_persistence_signals(analysis)


def _is_directly_relevant_followup(item: str, feature: str) -> bool:
    value = item.lower()
    feature_tokens = _tokens(feature)
    if "disabled" in value and feature_tokens.intersection({"button", "buttons"}):
        return True
    if "accessibility" in value and feature_tokens.intersection({"button", "form", "slider"}):
        return True
    return False


def _is_simple_dashboard_ui_feature(feature: str) -> bool:
    tokens = _tokens(feature)
    return bool(tokens.intersection({"dashboard", "chart", "filters", "filter", "slider"})) and bool(
        tokens.intersection({"button", "reset", "clear", "toggle", "display", "show"})
    )


def _repo_has_persistence_signals(analysis: RepositoryAnalysis) -> bool:
    summary_text = " ".join(str(value).lower() for value in analysis.architecture_summary.values())
    fit_text = " ".join(
        str(value).lower() for value in analysis.architecture_fit.get("new_infrastructure_required", [])
    )
    persistence_terms = ("postgres", "mysql", "sqlite", "mongodb", "database", "storage")
    return any(term in summary_text or term in fit_text for term in persistence_terms)
