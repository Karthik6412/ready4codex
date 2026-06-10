# Ready4Codex

Ready4Codex is a repo-aware CLI that checks whether a feature request is ready for agentic development before implementation begins.

It fetches a public GitHub repository, analyzes architecture signals, runs PM and Engineer readiness agents concurrently, synthesizes an Agentic Readiness Score, and saves a Markdown readiness report under `reports/`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`GITHUB_TOKEN` is optional, but recommended for higher GitHub API rate limits.

## OpenAI Setup

Ready4Codex uses `gpt-4o-mini` when `OPENAI_API_KEY` is available:

```bash
export OPENAI_API_KEY="your-api-key"
```

With the key set, the PM Agent, Engineer Agent, and Synthesis Agent use OpenAI API calls. The CLI prints whether each agent used `OpenAI mode` or `fallback mode`.

If `OPENAI_API_KEY` is missing, or if any OpenAI call fails, that agent automatically falls back to deterministic local logic. Fallback mode keeps the CLI usable for demos, offline development, and environments without API credentials.

## Usage

```bash
python main.py \
  --repo https://github.com/org/project \
  --feature "Add notifications when users join projects"
```

Example:

```bash
python main.py \
  --repo https://github.com/octocat/Hello-World \
  --feature "Add a README section that explains how users run the sample"
```

## Output

The CLI prints a compact summary and saves a full Markdown report containing:

- Agentic Readiness Score
- Verdict
- Product gaps
- Engineering risks
- Architecture fit analysis
- Testability analysis
- Suggested agent plan
- Codex-ready prompt

See [examples/](examples/) for a sample terminal output and generated Markdown report.

## MVP Scope

This MVP focuses on producing a working readiness report first. OpenAI-backed agents are used when configured, with deterministic fallback kept intentionally small and local.
