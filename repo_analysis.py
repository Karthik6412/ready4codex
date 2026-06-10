from __future__ import annotations

import json
import re
from dataclasses import dataclass

from github_repo import RepoSnapshot


@dataclass(frozen=True)
class RepositoryAnalysis:
    architecture_summary: dict[str, str]
    architecture_fit: dict[str, object]
    tree_sample: list[str]
    inspected_files: list[str]
    repo_notes: list[str]


FRAMEWORK_HINTS = {
    "fastapi": ("backend", "FastAPI"),
    "django": ("backend", "Django"),
    "flask": ("backend", "Flask"),
    "express": ("backend", "Express"),
    "nestjs": ("backend", "NestJS"),
    "next": ("frontend", "Next.js"),
    "react": ("frontend", "React"),
    "vue": ("frontend", "Vue"),
    "svelte": ("frontend", "Svelte"),
    "pytest": ("tests", "pytest"),
    "jest": ("tests", "Jest"),
    "vitest": ("tests", "Vitest"),
    "playwright": ("e2e_tests", "Playwright"),
    "postgres": ("database", "PostgreSQL"),
    "psycopg": ("database", "PostgreSQL"),
    "mysql": ("database", "MySQL"),
    "sqlite": ("database", "SQLite"),
    "mongodb": ("database", "MongoDB"),
    "redis": ("cache", "Redis"),
    "celery": ("jobs", "Celery"),
    "rq": ("jobs", "RQ"),
    "jwt": ("auth", "JWT"),
    "next-auth": ("auth", "NextAuth"),
}

INFRA_KEYWORDS = {
    "email": ("email service", ("email", "mail", "smtp", "sendgrid", "ses", "postmark")),
    "notification": ("notification service", ("notification", "notify", "webhook")),
    "payment": ("payment provider", ("stripe", "payment", "billing", "checkout")),
    "upload": ("file storage", ("s3", "blob", "storage", "upload")),
    "search": ("search index", ("search", "elasticsearch", "opensearch", "meilisearch")),
    "queue": ("background queue", ("queue", "celery", "rq", "worker", "bullmq")),
}


def analyze_repository(snapshot: RepoSnapshot, feature: str) -> RepositoryAnalysis:
    file_map = {item.path: item.content for item in snapshot.files}
    combined_text = "\n".join(file_map.values()).lower()
    paths = snapshot.tree_paths

    architecture_summary = _build_architecture_summary(file_map, combined_text, paths)
    architecture_fit = _build_architecture_fit(feature, paths, combined_text)

    notes = []
    if not any(path.lower().endswith("readme.md") for path in paths):
        notes.append("No README.md detected.")
    if not any(path.lower().startswith(("tests/", "test/")) for path in paths):
        notes.append("No top-level test directory detected.")
    if len(snapshot.files) == 0:
        notes.append("No readable repository files were fetched.")

    return RepositoryAnalysis(
        architecture_summary=architecture_summary,
        architecture_fit=architecture_fit,
        tree_sample=paths[:80],
        inspected_files=[item.path for item in snapshot.files],
        repo_notes=notes,
    )


def _build_architecture_summary(
    files: dict[str, str], combined_text: str, paths: list[str]
) -> dict[str, str]:
    summary: dict[str, str] = {}

    package_json = _read_json(files.get("package.json", ""))
    if package_json:
        dependencies = {
            **package_json.get("dependencies", {}),
            **package_json.get("devDependencies", {}),
        }
        for name in dependencies:
            _apply_hint(summary, name.lower())

    pyproject = files.get("pyproject.toml", "").lower()
    requirements = files.get("requirements.txt", "").lower()
    for hint_source in (pyproject, requirements, combined_text):
        for key in FRAMEWORK_HINTS:
            if key in hint_source:
                _apply_hint(summary, key)

    if any(path.endswith(".py") for path in paths):
        summary.setdefault("language", "Python")
    elif any(path.endswith((".ts", ".tsx")) for path in paths):
        summary.setdefault("language", "TypeScript")
    elif any(path.endswith((".js", ".jsx")) for path in paths):
        summary.setdefault("language", "JavaScript")
    elif any(path.endswith(".go") for path in paths):
        summary.setdefault("language", "Go")

    if any(path.lower().startswith(("tests/", "test/")) for path in paths):
        summary.setdefault("tests", "Detected")
    if any(path.lower().startswith(".github/workflows/") for path in paths):
        summary.setdefault("ci", "GitHub Actions")
    if any(path.lower().endswith("dockerfile") for path in paths):
        summary.setdefault("containerization", "Docker")

    return summary or {"status": "No strong architecture signals detected"}


def _build_architecture_fit(
    feature: str, paths: list[str], combined_text: str
) -> dict[str, object]:
    tokens = _meaningful_tokens(feature)
    top_dirs = sorted({path.split("/", 1)[0] for path in paths if "/" in path})

    impacted_modules = []
    for directory in top_dirs:
        directory_tokens = _meaningful_tokens(directory.replace("-", " ").replace("_", " "))
        if tokens.intersection(directory_tokens):
            impacted_modules.append(directory)

    if not impacted_modules:
        impacted_modules = _infer_modules_from_feature(tokens, top_dirs)

    new_infrastructure = []
    for trigger, (label, evidence_words) in INFRA_KEYWORDS.items():
        if trigger in tokens and not any(word in combined_text for word in evidence_words):
            new_infrastructure.append(label)

    complexity = "low"
    if len(impacted_modules) >= 3 or new_infrastructure:
        complexity = "medium"
    if len(impacted_modules) >= 5 or len(new_infrastructure) >= 2:
        complexity = "high"

    return {
        "impacted_modules": impacted_modules[:8],
        "affected_services": _infer_services(impacted_modules),
        "new_infrastructure_required": new_infrastructure,
        "implementation_complexity": complexity,
        "ownership_boundaries": _ownership_boundaries(impacted_modules),
    }


def _apply_hint(summary: dict[str, str], key: str) -> None:
    category, value = FRAMEWORK_HINTS[key]
    summary.setdefault(category, value)


def _read_json(content: str) -> dict:
    if not content.strip():
        return {}
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _meaningful_tokens(value: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "as",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "when",
        "with",
        "user",
        "users",
        "add",
        "create",
        "update",
        "build",
        "make",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower())
        if token not in stop_words
    }


def _infer_modules_from_feature(tokens: set[str], top_dirs: list[str]) -> list[str]:
    guesses = []
    mappings = {
        "auth": ("auth", "users", "accounts"),
        "login": ("auth", "users", "accounts"),
        "notification": ("notifications", "workers", "services"),
        "email": ("notifications", "workers", "services"),
        "payment": ("billing", "payments", "services"),
        "billing": ("billing", "payments", "services"),
        "admin": ("admin", "dashboard"),
        "api": ("api", "routes", "controllers"),
    }
    for token, candidates in mappings.items():
        if token in tokens:
            guesses.extend(directory for directory in top_dirs if directory in candidates)
    return sorted(set(guesses))


def _infer_services(modules: list[str]) -> list[str]:
    service_like = {"api", "server", "backend", "workers", "services", "jobs"}
    return [module for module in modules if module in service_like]


def _ownership_boundaries(modules: list[str]) -> list[str]:
    if not modules:
        return ["No clear ownership boundary detected from repository structure."]
    return [f"{module}/" for module in modules]
