from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from repo_analysis import RepositoryAnalysis


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SanitizedOutput:
    output: dict[str, list[str]]
    removed: tuple[str, ...]


def sanitize_pm_output(
    result: dict[str, object], feature: str, analysis: RepositoryAnalysis
) -> SanitizedOutput:
    removed: list[str] = []
    must_clarify: list[str] = []
    should_clarify = _coerce_string_list(result.get("should_clarify"))

    for item in _coerce_string_list(result.get("must_clarify")):
        action = _classify_item(item, feature, analysis)
        if action == "remove":
            removed.append(item)
        elif action == "demote":
            should_clarify.append(item)
        else:
            must_clarify.append(item)

    output = {
        "must_clarify": _dedupe(must_clarify),
        "should_clarify": _filter_items(should_clarify, feature, analysis, removed),
        "open_questions": _filter_items(
            _coerce_string_list(result.get("open_questions")),
            feature,
            analysis,
            removed,
        ),
    }
    _log_removed(removed)
    return SanitizedOutput(output=output, removed=tuple(_dedupe(removed)))


def sanitize_engineer_output(
    result: dict[str, object], feature: str, analysis: RepositoryAnalysis
) -> SanitizedOutput:
    removed: list[str] = []
    risks: list[str] = []
    open_questions = _coerce_string_list(result.get("open_questions"))

    for item in _coerce_string_list(result.get("risks")):
        action = _classify_item(item, feature, analysis)
        if action == "remove":
            removed.append(item)
        elif action == "demote":
            open_questions.append(item)
        else:
            risks.append(item)

    output = {
        "risks": _dedupe(risks),
        "missing_infrastructure": _filter_items(
            _coerce_string_list(result.get("missing_infrastructure")),
            feature,
            analysis,
            removed,
        ),
        "open_questions": _filter_items(open_questions, feature, analysis, removed),
    }
    _log_removed(removed)
    return SanitizedOutput(output=output, removed=tuple(_dedupe(removed)))


def sanitize_report_items(
    product_gaps: list[str],
    engineering_risks: list[str],
    feature: str,
    analysis: RepositoryAnalysis,
) -> tuple[list[str], list[str], tuple[str, ...]]:
    removed: list[str] = []
    sanitized_product_gaps = _filter_items(product_gaps, feature, analysis, removed)
    sanitized_engineering_risks = _filter_items(
        engineering_risks, feature, analysis, removed
    )
    _log_removed(removed)
    return sanitized_product_gaps, sanitized_engineering_risks, tuple(_dedupe(removed))


def _filter_items(
    items: list[str],
    feature: str,
    analysis: RepositoryAnalysis,
    removed: list[str],
) -> list[str]:
    kept: list[str] = []
    for item in items:
        action = _classify_item(item, feature, analysis)
        if action == "remove":
            removed.append(item)
        else:
            kept.append(item)
    return _dedupe(kept)


def _classify_item(item: str, feature: str, analysis: RepositoryAnalysis) -> str:
    if _already_answered_by_feature(item, feature):
        return "remove"
    if _is_persistence_concern(item) and not _persistence_is_grounded(feature, analysis):
        return "remove"
    if _is_auth_concern(item) and not _auth_is_grounded(feature, analysis):
        return "remove"
    if _is_ux_polish_concern(item):
        return "demote" if _ux_polish_is_explicitly_requested(item, feature) else "remove"
    return "keep"


def _already_answered_by_feature(item: str, feature: str) -> bool:
    item_value = item.lower()
    feature_value = feature.lower()
    if "filter" in item_value and (
        "clears all filters" in feature_value or "clear all filters" in feature_value
    ):
        return True
    if "slider" in item_value and "0-90" in feature_value:
        return True
    if "default" in item_value and "0-90" in feature_value:
        return True
    return False


def _is_persistence_concern(item: str) -> bool:
    value = item.lower()
    terms = (
        "unsaved",
        "save/discard",
        "save discard",
        "save or discard",
        "discard",
        "persistence",
        "persist",
        "data loss",
        "losing work",
        "stored",
        "database write",
        "database writes",
    )
    return any(term in value for term in terms)


def _is_auth_concern(item: str) -> bool:
    value = item.lower()
    terms = (
        "user role",
        "user roles",
        "role-based",
        "permissions",
        "permission",
        "access control",
        "authorization",
        "authentication",
        "auth",
    )
    return any(term in value for term in terms)


def _is_ux_polish_concern(item: str) -> bool:
    value = item.lower()
    terms = (
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
        "design placement",
        "placement",
        "button styling",
        "styling",
    )
    return any(term in value for term in terms)


def _persistence_is_grounded(feature: str, analysis: RepositoryAnalysis) -> bool:
    feature_terms = ("save", "persist", "unsaved", "draft", "discard", "edit", "editing")
    if any(term in feature.lower() for term in feature_terms):
        return True
    repo_text = _repo_context_text(analysis)
    repo_terms = (
        "postgres",
        "mysql",
        "sqlite",
        "mongodb",
        "database",
        "storage",
        "migration",
        "save",
        "edit",
        "editing",
    )
    return any(term in repo_text for term in repo_terms)


def _auth_is_grounded(feature: str, analysis: RepositoryAnalysis) -> bool:
    feature_terms = ("role", "permission", "access", "admin", "owner", "auth", "login")
    if any(term in feature.lower() for term in feature_terms):
        return True
    repo_text = _repo_context_text(analysis)
    repo_terms = (
        "auth",
        "jwt",
        "login",
        "users/",
        "accounts/",
        "permissions",
        "roles",
    )
    return any(term in repo_text for term in repo_terms)


def _ux_polish_is_explicitly_requested(item: str, feature: str) -> bool:
    value = item.lower()
    feature_value = feature.lower()
    category_terms = {
        "animation": ("animation", "animate", "transition"),
        "alert": ("alert", "toast", "notification"),
        "visual feedback": ("visual feedback", "highlight", "indicator"),
        "accessibility": ("accessibility", "accessible", "a11y", "screen reader"),
        "disabled": ("disabled", "disable"),
        "confirmation": ("confirmation", "confirm"),
        "design": ("design", "placement", "style", "styling", "layout", "color"),
    }
    for marker, terms in category_terms.items():
        if marker in value and any(term in feature_value for term in terms):
            return True
    return False


def _repo_context_text(analysis: RepositoryAnalysis) -> str:
    parts: list[str] = []
    parts.extend(str(key) for key in analysis.architecture_summary.keys())
    parts.extend(str(value) for value in analysis.architecture_summary.values())
    parts.extend(str(key) for key in analysis.architecture_fit.keys())
    parts.extend(str(value) for value in analysis.architecture_fit.values())
    parts.extend(analysis.tree_sample)
    parts.extend(analysis.inspected_files)
    return " ".join(parts).lower()


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if str(item).strip()])


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = re.sub(r"\s+", " ", str(item).strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _log_removed(removed: list[str]) -> None:
    if removed:
        logger.info("Sanitizer removed: %s", "; ".join(_dedupe(removed)))
