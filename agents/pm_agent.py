from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from openai_support import OpenAIUnavailable, call_openai_json, string_array_schema
from repo_analysis import RepositoryAnalysis


PM_SYSTEM_PROMPT = """You are a senior product manager reviewing a feature request.

Identify:

* unclear requirements
* missing business rules
* undefined user flows
* acceptance criteria gaps

Be specific and concise.

Return JSON only."""


@dataclass(frozen=True)
class AgentResult:
    output: dict[str, list[str]]
    mode: str
    error: str | None = None


async def run_pm_agent(feature: str, analysis: RepositoryAnalysis) -> AgentResult:
    try:
        result = await call_openai_json(
            system_prompt=PM_SYSTEM_PROMPT,
            payload={
                "feature_request": feature,
                "repo_analysis_summary": analysis.architecture_summary,
                "architecture_fit_analysis": analysis.architecture_fit,
            },
            schema_name="pm_readiness_review",
            schema=string_array_schema(
                ["must_clarify", "should_clarify", "open_questions"]
            ),
        )
        return AgentResult(output=_normalize_pm_result(result), mode="OpenAI mode")
    except Exception as exc:
        if not isinstance(exc, OpenAIUnavailable):
            error = str(exc)
        else:
            error = str(exc)
        return AgentResult(
            output=await _run_pm_fallback(feature, analysis),
            mode="fallback mode",
            error=error,
        )


async def _run_pm_fallback(feature: str, analysis: RepositoryAnalysis) -> dict[str, list[str]]:
    await asyncio.sleep(0)

    feature_lower = feature.lower()
    tokens = _tokens(feature_lower)

    must_clarify: list[str] = []
    should_clarify: list[str] = []
    open_questions: list[str] = []

    if len(tokens) < 5:
        must_clarify.append("Feature request is too short to infer scope or acceptance criteria.")

    if not _mentions_actor(feature_lower) and not _has_implied_ui_actor(tokens):
        must_clarify.append("Primary user or actor is not clearly defined.")

    if not _mentions_success_condition(feature_lower):
        must_clarify.append("Acceptance criteria are not stated in measurable terms.")

    if any(word in tokens for word in {"notification", "notifications", "email", "message"}):
        if not any(word in tokens for word in {"email", "sms", "push", "in-app", "webhook"}):
            must_clarify.append("Notification delivery channel is not specified.")
        if not any(word in tokens for word in {"receive", "recipient", "admin", "owner", "member", "user"}):
            should_clarify.append("Notification recipients should be explicitly defined.")
        open_questions.append("Can users configure or disable these notifications?")

    if any(word in tokens for word in {"permission", "role", "admin", "owner", "access"}):
        should_clarify.append("Role and permission rules need explicit allowed and denied cases.")

    if any(word in tokens for word in {"delete", "remove", "cancel"}):
        should_clarify.append("Destructive action behavior and recovery expectations should be defined.")

    if any(word in tokens for word in {"payment", "billing", "subscription", "invoice"}):
        must_clarify.append("Payment states, failure handling, and business rules are not fully defined.")

    if any(word in tokens for word in {"ml", "prediction", "predictions", "model", "inference"}):
        must_clarify.append("Prediction target and expected output are not defined.")
        should_clarify.append("Input data source for predictions should be defined.")
        should_clarify.append("Model quality, freshness, or evaluation criteria should be defined.")

    if any(word in tokens for word in {"report", "dashboard", "analytics"}):
        should_clarify.append("Reporting dimensions, filters, and freshness expectations should be defined.")

    if analysis.repo_notes:
        should_clarify.extend(f"Repository context note: {note}" for note in analysis.repo_notes)

    if not open_questions:
        open_questions.append("What exact user-visible behavior confirms this feature is complete?")

    return {
        "must_clarify": _dedupe(must_clarify),
        "should_clarify": _dedupe(should_clarify),
        "open_questions": _dedupe(open_questions),
    }


def _normalize_pm_result(result: dict[str, object]) -> dict[str, list[str]]:
    return {
        "must_clarify": _coerce_string_list(result.get("must_clarify")),
        "should_clarify": _coerce_string_list(result.get("should_clarify")),
        "open_questions": _coerce_string_list(result.get("open_questions")),
    }


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if str(item).strip()])


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value))


def _mentions_actor(value: str) -> bool:
    actors = ("user", "admin", "owner", "member", "customer", "developer", "team", "player")
    return any(actor in value for actor in actors)


def _has_implied_ui_actor(tokens: set[str]) -> bool:
    ui_terms = {
        "button",
        "form",
        "screen",
        "page",
        "field",
        "filter",
        "filters",
        "modal",
        "menu",
        "dashboard",
    }
    return bool(tokens.intersection(ui_terms))


def _mentions_success_condition(value: str) -> bool:
    signals = (
        "within",
        "after",
        "before",
        "must",
        "should",
        "can",
        "cannot",
        "display",
        "receive",
        "return",
        "when",
    )
    return any(signal in value for signal in signals)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
