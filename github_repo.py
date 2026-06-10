from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


IMPORTANT_FILE_NAMES = {
    "readme.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "poetry.lock",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "dockerfile",
    "docker-compose.yml",
    ".github/workflows",
}

IMPORTANT_DIRS = (
    "src/",
    "app/",
    "lib/",
    "server/",
    "backend/",
    "frontend/",
    "api/",
    "routes/",
    "models/",
    "services/",
    "tests/",
    "test/",
    "docs/",
)

SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".html",
    ".css",
    ".sql",
}


@dataclass(frozen=True)
class RepoFile:
    path: str
    content: str


@dataclass(frozen=True)
class RepoSnapshot:
    full_name: str
    default_branch: str
    description: str
    html_url: str
    tree_paths: list[str]
    files: list[RepoFile]


class GitHubRepoError(RuntimeError):
    pass


def parse_github_repo(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:").removesuffix(".git")
    elif candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        if parsed.netloc.lower() != "github.com":
            raise GitHubRepoError("Only github.com repository URLs are supported.")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise GitHubRepoError("GitHub URL must include owner and repository.")
        candidate = f"{parts[0]}/{parts[1].removesuffix('.git')}"
    elif candidate.count("/") == 1:
        candidate = candidate.removesuffix(".git")
    else:
        raise GitHubRepoError("Use a GitHub URL or owner/repo name.")

    owner, repo = candidate.split("/", 1)
    if not owner or not repo:
        raise GitHubRepoError("GitHub repository must be in owner/repo format.")
    return f"{owner}/{repo}"


class GitHubRepoClient:
    def __init__(self, max_files: int = 80, max_file_bytes: int = 20_000) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.token = os.getenv("GITHUB_TOKEN")

    def fetch(self, repo_url: str) -> RepoSnapshot:
        full_name = parse_github_repo(repo_url)
        try:
            return self._fetch_with_pygithub(full_name)
        except ImportError:
            return self._fetch_with_api(full_name)
        except Exception as exc:
            if exc.__class__.__name__ in {"GithubException", "BadCredentialsException"}:
                raise GitHubRepoError(f"Could not fetch {full_name}: {exc}") from exc
            raise

    def _fetch_with_pygithub(self, full_name: str) -> RepoSnapshot:
        from github import Github  # type: ignore

        github = Github(self.token) if self.token else Github()
        repo = github.get_repo(full_name)
        tree = repo.get_git_tree(repo.default_branch, recursive=True).tree
        paths = sorted(item.path for item in tree if item.type == "blob")
        selected_paths = self._select_paths(paths)

        files: list[RepoFile] = []
        for path in selected_paths:
            try:
                content_file = repo.get_contents(path, ref=repo.default_branch)
                if isinstance(content_file, list):
                    continue
                raw = content_file.decoded_content[: self.max_file_bytes]
                files.append(RepoFile(path=path, content=raw.decode("utf-8", errors="replace")))
            except Exception:
                continue

        return RepoSnapshot(
            full_name=full_name,
            default_branch=repo.default_branch,
            description=repo.description or "",
            html_url=repo.html_url,
            tree_paths=paths,
            files=files,
        )

    def _fetch_with_api(self, full_name: str) -> RepoSnapshot:
        repo_data = self._get_json(f"https://api.github.com/repos/{full_name}")
        default_branch = repo_data["default_branch"]
        tree_data = self._get_json(
            f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}?recursive=1"
        )
        paths = sorted(
            item["path"]
            for item in tree_data.get("tree", [])
            if item.get("type") == "blob" and isinstance(item.get("path"), str)
        )
        selected_paths = self._select_paths(paths)

        files: list[RepoFile] = []
        for path in selected_paths:
            encoded_path = "/".join(part.replace("#", "%23") for part in path.split("/"))
            data = self._get_json(
                f"https://api.github.com/repos/{full_name}/contents/{encoded_path}?ref={default_branch}"
            )
            content = data.get("content")
            if not isinstance(content, str):
                continue
            raw = base64.b64decode(content, validate=False)[: self.max_file_bytes]
            files.append(RepoFile(path=path, content=raw.decode("utf-8", errors="replace")))

        return RepoSnapshot(
            full_name=full_name,
            default_branch=default_branch,
            description=repo_data.get("description") or "",
            html_url=repo_data.get("html_url") or f"https://github.com/{full_name}",
            tree_paths=paths,
            files=files,
        )

    def _get_json(self, url: str) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ready4codex",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GitHubRepoError(f"GitHub API returned {exc.code} for {url}") from exc
        except URLError as exc:
            raise GitHubRepoError(f"Could not reach GitHub: {exc.reason}") from exc

    def _select_paths(self, paths: Iterable[str]) -> list[str]:
        important: list[str] = []
        source_like: list[str] = []

        for path in paths:
            normalized = path.replace("\\", "/")
            if self._should_skip(normalized):
                continue
            lower = normalized.lower()
            name = lower.rsplit("/", 1)[-1]

            if name in IMPORTANT_FILE_NAMES or any(lower.startswith(item) for item in IMPORTANT_FILE_NAMES):
                important.append(normalized)
                continue

            if lower.startswith(IMPORTANT_DIRS) and self._has_text_extension(lower):
                source_like.append(normalized)

        selected = important + source_like
        return selected[: self.max_files]

    def _should_skip(self, path: str) -> bool:
        return any(part in SKIP_PARTS for part in path.split("/"))

    def _has_text_extension(self, path: str) -> bool:
        if "." not in path:
            return False
        extension = "." + path.rsplit(".", 1)[-1]
        return extension in TEXT_EXTENSIONS
