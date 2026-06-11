from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from github_repo import RepoSnapshot
from openai_support import OpenAIUnavailable, call_openai_json
from repo_analysis import RepositoryAnalysis


@dataclass(frozen=True)
class ReadinessReport:
    repository: str
    feature: str
    score: int
    verdict: str
    product_gaps: list[str]
    engineering_risks: list[str]
    architecture_fit: dict[str, object]
    testability_analysis: dict[str, object]
    repo_health_warnings: list[str]
    suggested_agent_plan: list[dict[str, object]]
    codex_ready_prompt: str
    architecture_summary: dict[str, str]
    inspected_files: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SynthesisResult:
    report: ReadinessReport
    mode: str
    error: str | None = None


async def run_synthesis_agent(
    snapshot: RepoSnapshot,
    feature: str,
    analysis: RepositoryAnalysis,
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
    skill_path: str = "skills/codex-readiness/SKILL.md",
) -> SynthesisResult:
    fallback_report = synthesize_report(snapshot, feature, analysis, pm_result, engineer_result)
    try:
        skill_contents = Path(skill_path).read_text(encoding="utf-8")
        result = await call_openai_json(
            system_prompt=_synthesis_system_prompt(skill_contents),
            payload={
                "repository": snapshot.full_name,
                "feature_request": feature,
                "repo_analysis_summary": analysis.architecture_summary,
                "architecture_fit_analysis": analysis.architecture_fit,
                "pm_agent_output": pm_result,
                "engineer_agent_output": engineer_result,
            },
            schema_name="ready4codex_synthesis",
            schema=_synthesis_schema(),
            max_output_tokens=3000,
        )
        return SynthesisResult(
            report=_report_from_openai_result(
                result=result,
                snapshot=snapshot,
                feature=feature,
                analysis=analysis,
                fallback=fallback_report,
            ),
            mode="OpenAI mode",
        )
    except Exception as exc:
        if not isinstance(exc, OpenAIUnavailable):
            error = str(exc)
        else:
            error = str(exc)
        return SynthesisResult(report=fallback_report, mode="fallback mode", error=error)


def synthesize_report(
    snapshot: RepoSnapshot,
    feature: str,
    analysis: RepositoryAnalysis,
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
) -> ReadinessReport:
    testability = analyze_testability(feature, pm_result)
    repo_health_warnings = collect_repo_health_warnings(analysis, pm_result, engineer_result)
    feature_pm_result = feature_specific_pm_result(pm_result)
    feature_engineer_result = feature_specific_engineer_result(engineer_result)
    score = calculate_score(
        feature_pm_result,
        feature_engineer_result,
        testability,
        analysis.architecture_fit,
    )
    verdict = calculate_verdict(score, feature_pm_result, feature_engineer_result, testability)
    agent_plan = build_agent_plan(analysis)
    prompt = build_codex_prompt(
        feature,
        analysis,
        feature_pm_result,
        feature_engineer_result,
        testability,
    )

    product_gaps = (
        feature_pm_result.get("must_clarify", [])
        + feature_pm_result.get("should_clarify", [])
        + pm_result.get("open_questions", [])
    )
    engineering_risks = (
        feature_engineer_result.get("risks", [])
        + feature_engineer_result.get("missing_infrastructure", [])
    )

    return ReadinessReport(
        repository=snapshot.full_name,
        feature=feature,
        score=score,
        verdict=verdict,
        product_gaps=_dedupe(product_gaps),
        engineering_risks=_dedupe(engineering_risks),
        architecture_fit=analysis.architecture_fit,
        testability_analysis=testability,
        repo_health_warnings=repo_health_warnings,
        suggested_agent_plan=agent_plan,
        codex_ready_prompt=prompt,
        architecture_summary=analysis.architecture_summary,
        inspected_files=analysis.inspected_files,
    )


def _synthesis_system_prompt(skill_contents: str) -> str:
    return f"""You are the Ready4Codex synthesis agent.

Use the following skill definition as the governing rubric:

{skill_contents}

Combine repository analysis, PM review, Engineer review, and testability concerns into a concise readiness report.
Score this feature request on whether IT is ready to implement. Repo health issues are warnings, not score penalties unless they directly block this specific feature.
Separate feature readiness from repo health:
- FEATURE READINESS affects the ARS score: must-clarify items specific to this feature, engineering risks that block this feature, missing infrastructure required for this feature, and poor testability of this feature's requirements.
- REPO HEALTH appears only in repo_health_warnings and must not reduce the score: general missing tests, no CI/CD, broad architectural gaps unrelated to the feature, and repository hygiene issues.
A simple, well-scoped feature on an imperfect repo should still score 70-80+ when the request itself is clear.
Distinguish blocking issues from non-blocking improvements. Readiness scoring should primarily reflect implementation readiness, not perfection.
Ready4Codex answers: "Can an engineer or coding agent reasonably begin implementation?" not "Have all possible future questions been answered?"
Context applicability check:
- If the repo appears to be a simple dashboard/data visualization app with no user accounts, database writes, persistence/save workflow, or editing workflow, do not treat unsaved changes, confirmation dialogs, save/discard behavior, or data persistence behavior as blockers.
- Animations, alerts, visual feedback, accessibility, disabled states, and confirmation dialogs are non-blocking UX polish unless explicitly requested.
- If implementation_complexity is low, new_infrastructure_required is empty, must_clarify is empty, and there are no blocking engineering risks, the ARS must be at least 75.
Return JSON only. Follow the skill output order. Do not recommend implementation when critical ambiguities remain."""


def feature_specific_pm_result(
    pm_result: dict[str, list[str]]
) -> dict[str, list[str]]:
    return {
        "must_clarify": [
            item
            for item in pm_result.get("must_clarify", [])
            if not _is_repo_health_item(item)
        ],
        "should_clarify": [
            item
            for item in pm_result.get("should_clarify", [])
            if not _is_repo_health_item(item)
        ],
        "open_questions": pm_result.get("open_questions", []),
    }


def feature_specific_engineer_result(
    engineer_result: dict[str, list[str]]
) -> dict[str, list[str]]:
    return {
        "risks": [
            item
            for item in engineer_result.get("risks", [])
            if not _is_repo_health_item(item)
        ],
        "missing_infrastructure": [
            item
            for item in engineer_result.get("missing_infrastructure", [])
            if not _is_repo_health_item(item)
        ],
        "open_questions": engineer_result.get("open_questions", []),
    }


def collect_repo_health_warnings(
    analysis: RepositoryAnalysis,
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(analysis.repo_notes)

    if "ci" not in analysis.architecture_summary:
        warnings.append("No CI/CD workflow detected.")

    ownership_boundaries = analysis.architecture_fit.get("ownership_boundaries", [])
    if isinstance(ownership_boundaries, list):
        warnings.extend(
            str(item)
            for item in ownership_boundaries
            if "no clear ownership boundary" in str(item).lower()
        )

    for item in (
        pm_result.get("must_clarify", [])
        + pm_result.get("should_clarify", [])
        + engineer_result.get("risks", [])
        + engineer_result.get("missing_infrastructure", [])
    ):
        if _is_repo_health_item(item):
            warnings.append(item.removeprefix("Repository context note: ").strip())

    return _dedupe(warnings)


def _synthesis_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "score",
            "verdict",
            "product_gaps",
            "engineering_risks",
            "architecture_fit",
            "testability_analysis",
            "repo_health_warnings",
            "suggested_agent_plan",
            "codex_ready_prompt",
        ],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "verdict": {"type": "string", "enum": ["READY", "NEEDS WORK", "NOT READY"]},
            "product_gaps": {"type": "array", "items": {"type": "string"}},
            "engineering_risks": {"type": "array", "items": {"type": "string"}},
            "architecture_fit": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "impacted_modules",
                    "affected_services",
                    "new_infrastructure_required",
                    "implementation_complexity",
                    "ownership_boundaries",
                ],
                "properties": {
                    "impacted_modules": {"type": "array", "items": {"type": "string"}},
                    "affected_services": {"type": "array", "items": {"type": "string"}},
                    "new_infrastructure_required": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "implementation_complexity": {"type": "string"},
                    "ownership_boundaries": {"type": "array", "items": {"type": "string"}},
                },
            },
            "testability_analysis": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "testability_score",
                    "weak_requirements",
                    "improved_acceptance_criteria",
                ],
                "properties": {
                    "testability_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "weak_requirements": {"type": "array", "items": {"type": "string"}},
                    "improved_acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "repo_health_warnings": {"type": "array", "items": {"type": "string"}},
            "suggested_agent_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["agent", "responsibility", "files"],
                    "properties": {
                        "agent": {"type": "string"},
                        "responsibility": {"type": "string"},
                        "files": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "codex_ready_prompt": {"type": "string"},
        },
    }


def _report_from_openai_result(
    *,
    result: dict[str, object],
    snapshot: RepoSnapshot,
    feature: str,
    analysis: RepositoryAnalysis,
    fallback: ReadinessReport,
) -> ReadinessReport:
    architecture_fit = _coerce_dict(result.get("architecture_fit")) or analysis.architecture_fit
    product_gaps = _coerce_string_list(result.get("product_gaps")) or fallback.product_gaps
    engineering_risks = _coerce_string_list(result.get("engineering_risks")) or fallback.engineering_risks
    testability_analysis = (
        _coerce_dict(result.get("testability_analysis")) or fallback.testability_analysis
    )
    blocking_product_gaps = [
        item for item in product_gaps if not _is_non_blocking_synthesis_item(item)
    ]
    blocking_engineering_risks = [
        item for item in engineering_risks if _is_blocking_engineering_risk(item)
    ]
    score = _coerce_score(result.get("score"), fallback.score)
    if _should_apply_readiness_floor(
        architecture_fit,
        {"must_clarify": blocking_product_gaps},
        {"risks": blocking_engineering_risks, "missing_infrastructure": []},
        blocking_engineering_risks,
    ):
        score = max(score, 75)
    verdict = calculate_verdict(
        score,
        {"must_clarify": blocking_product_gaps},
        {"risks": blocking_engineering_risks, "missing_infrastructure": []},
        testability_analysis,
    )

    return ReadinessReport(
        repository=snapshot.full_name,
        feature=feature,
        score=score,
        verdict=verdict,
        product_gaps=product_gaps,
        engineering_risks=engineering_risks,
        architecture_fit=architecture_fit,
        testability_analysis=testability_analysis,
        repo_health_warnings=_coerce_string_list(result.get("repo_health_warnings"))
        if "repo_health_warnings" in result
        else fallback.repo_health_warnings,
        suggested_agent_plan=_coerce_agent_plan(result.get("suggested_agent_plan"))
        or fallback.suggested_agent_plan,
        codex_ready_prompt=str(result.get("codex_ready_prompt") or fallback.codex_ready_prompt),
        architecture_summary=analysis.architecture_summary,
        inspected_files=analysis.inspected_files,
    )


def analyze_testability(feature: str, pm_result: dict[str, list[str]]) -> dict[str, object]:
    weak_requirements: list[str] = []
    improved_criteria: list[str] = []
    score = 100
    feature_lower = feature.lower()
    feature_tokens = _tokens(feature)

    vague_terms = {
        "easy": "Define the exact action count, screen, or workflow completion criteria.",
        "fast": "Define an expected response time or completion time.",
        "better": "Define the baseline and measurable improvement.",
        "well": "Define the observable success behavior.",
        "simple": "Define the exact UI or API behavior expected.",
        "optimize": "Define the target metric and threshold.",
    }

    for term, rewrite in vague_terms.items():
        if term in feature_lower:
            weak_requirements.append(f'Vague term "{term}" needs a measurable target.')
            improved_criteria.append(rewrite)
            score -= 12

    measurable_signals = (
        "within",
        "seconds",
        "minutes",
        "must",
        "cannot",
        "returns",
        "displays",
        "receives",
        "when",
        "after",
    )
    if not any(signal in feature_lower for signal in measurable_signals):
        weak_requirements.append("Feature request does not include measurable acceptance criteria.")
        improved_criteria.append(
            "Given the relevant starting state, when the user performs the action, then the expected result is observable and testable."
        )
        score -= 10 if _has_objective_primary_behavior(feature_tokens) else 25

    if pm_result.get("must_clarify"):
        score -= min(25, len(pm_result["must_clarify"]) * 8)

    return {
        "testability_score": max(0, score),
        "weak_requirements": _dedupe(weak_requirements),
        "improved_acceptance_criteria": _dedupe(improved_criteria),
    }


def calculate_score(
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
    testability: dict[str, object],
    architecture_fit: dict[str, object] | None = None,
) -> int:
    score = 100
    scored_risks = [
        risk
        for risk in engineer_result.get("risks", [])
        if _is_blocking_engineering_risk(risk)
    ]
    score -= len(pm_result.get("must_clarify", [])) * 10
    score -= len(scored_risks) * 8
    score -= len(engineer_result.get("missing_infrastructure", [])) * 12
    if int(testability.get("testability_score", 0)) < 70:
        score -= 15
    elif int(testability.get("testability_score", 0)) < 85:
        score -= 5
    if any(
        "no clearly impacted modules" in risk.lower()
        for risk in engineer_result.get("risks", [])
    ):
        score = min(score, 85)
    if (
        not engineer_result.get("risks")
        and not engineer_result.get("missing_infrastructure")
        and any("module should own" in question.lower() for question in engineer_result.get("open_questions", []))
    ):
        score = min(score, 90)
    if _should_apply_readiness_floor(
        architecture_fit or {},
        pm_result,
        engineer_result,
        scored_risks,
    ):
        score = max(score, 75)
    return max(0, min(100, score))


def calculate_verdict(
    score: int,
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
    testability: dict[str, object],
) -> str:
    has_blockers = bool(pm_result.get("must_clarify")) or bool(
        engineer_result.get("missing_infrastructure")
    )
    testability_score = int(testability.get("testability_score", 0))

    if score >= 80 and not has_blockers and testability_score >= 70:
        return "READY"
    if score >= 50:
        return "NEEDS WORK"
    return "NOT READY"


def build_agent_plan(analysis: RepositoryAnalysis) -> list[dict[str, object]]:
    fit = analysis.architecture_fit
    modules = [str(item) for item in fit.get("impacted_modules", [])]
    infrastructure = [str(item) for item in fit.get("new_infrastructure_required", [])]

    plan: list[dict[str, object]] = []
    plan.append(
        {
            "agent": "Agent 1",
            "responsibility": "Core implementation and data/API changes",
            "files": modules[:4] or ["src/", "app/", "api/"],
        }
    )

    if infrastructure:
        plan.append(
            {
                "agent": "Agent 2",
                "responsibility": "Infrastructure and integration concerns",
                "files": infrastructure,
            }
        )

    plan.append(
        {
            "agent": f"Agent {len(plan) + 1}",
            "responsibility": "Tests, documentation, and acceptance criteria validation",
            "files": ["tests/", "docs/", "README.md"],
        }
    )

    return plan


def build_codex_prompt(
    feature: str,
    analysis: RepositoryAnalysis,
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
    testability: dict[str, object],
) -> str:
    return "\n".join(
        [
            f"Implement: {feature}",
            "",
            "Repository Context:",
            _format_dict(analysis.architecture_summary),
            "",
            "Architecture Fit:",
            _format_dict(analysis.architecture_fit),
            "",
            "Requirements To Clarify Before Coding:",
            _format_list(pm_result.get("must_clarify", []) + pm_result.get("should_clarify", [])),
            "",
            "Engineering Risks To Resolve:",
            _format_list(
                engineer_result.get("risks", [])
                + engineer_result.get("missing_infrastructure", [])
            ),
            "",
            "Acceptance Criteria:",
            _format_list(
                [str(item) for item in testability.get("improved_acceptance_criteria", [])]
            ),
            "",
            "Testing Requirements:",
            "- Add or update automated tests covering each acceptance criterion.",
            "- Run the repo's existing relevant test suite before finishing.",
            "",
            "Implementation Constraints:",
            "- Follow existing repository architecture and naming conventions.",
            "- Keep changes scoped to the impacted modules.",
            "- Do not begin implementation until all critical ambiguities are resolved.",
        ]
    )


def _format_dict(value: dict[str, object]) -> str:
    if not value:
        return "- None detected"
    return "\n".join(f"- {key}: {item}" for key, item in value.items())


def _format_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower()))


def _has_objective_primary_behavior(tokens: set[str]) -> bool:
    objective_terms = {
        "button",
        "clear",
        "reset",
        "display",
        "show",
        "hide",
        "sort",
        "filter",
        "filters",
        "export",
        "download",
        "upload",
        "save",
        "delete",
        "remove",
        "create",
        "update",
        "page",
        "screen",
        "form",
        "field",
    }
    return bool(tokens.intersection(objective_terms))


def _coerce_score(value: object, fallback: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(100, score))


def _coerce_verdict(value: object, fallback: str) -> str:
    verdict = str(value)
    if verdict in {"READY", "NEEDS WORK", "NOT READY"}:
        return verdict
    return fallback


def _coerce_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if str(item).strip()])


def _coerce_agent_plan(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    plan: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        files = item.get("files", [])
        plan.append(
            {
                "agent": str(item.get("agent") or "Agent"),
                "responsibility": str(item.get("responsibility") or "Unspecified"),
                "files": _coerce_string_list(files),
            }
        )
    return plan


def _is_repo_health_item(item: str) -> bool:
    value = str(item).lower()
    repo_health_phrases = (
        "repository context note",
        "no readme",
        "readme.md detected",
        "no top-level test",
        "test directory",
        "test framework",
        "tests were not",
        "no ci",
        "ci/cd",
        "github actions",
        "no readable repository files",
        "no strong architecture signals",
        "no clear ownership boundary",
    )
    return any(phrase in value for phrase in repo_health_phrases)


def _is_blocking_engineering_risk(item: str) -> bool:
    value = str(item).lower()
    non_blocking_or_duplicate = (
        "coordination across multiple modules",
        "require infrastructure that was not detected",
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
        "unsaved",
        "save/discard",
        "save discard",
        "persistence",
    )
    return not any(phrase in value for phrase in non_blocking_or_duplicate)


def _is_non_blocking_synthesis_item(item: str) -> bool:
    value = str(item).lower()
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
        "unsaved",
        "save/discard",
        "save discard",
        "persistence",
        "persist",
        "toast",
        "loading state",
        "hover",
        "focus state",
        "optional",
        "polish",
    )
    return any(term in value for term in non_blocking_terms)


def _should_apply_readiness_floor(
    architecture_fit: dict[str, object],
    pm_result: dict[str, list[str]],
    engineer_result: dict[str, list[str]],
    scored_risks: list[str],
) -> bool:
    infrastructure = architecture_fit.get("new_infrastructure_required", [])
    if infrastructure is None:
        infrastructure = []
    return (
        str(architecture_fit.get("implementation_complexity", "")).lower() == "low"
        and not infrastructure
        and not pm_result.get("must_clarify")
        and not scored_risks
        and not engineer_result.get("missing_infrastructure")
    )


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = re.sub(r"\s+", " ", str(item).strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
