PRD: Ready4Codex

The Quality Gate Before Agentic Development

---

## Overview

Ready4Codex is a repo-aware CLI tool that determines whether a feature request is ready for agentic development.

Given a GitHub repository and a plain-English feature request, Ready4Codex analyzes the codebase, identifies specification gaps, surfaces technical risks, evaluates architecture fit, and generates a Codex-ready execution plan before any implementation begins.

The output is a structured readiness report, an Agentic Readiness Score (ARS), a suggested sub-agent delegation plan, and a production-ready prompt that can be pasted directly into Codex.

---

## Problem

Modern coding agents can build software extremely quickly.

However, when the feature request is vague, incomplete, or technically ambiguous:

* Agents build incorrect solutions
* Pull requests require significant rework
* Parallel worktrees waste execution cycles
* Reviews become slower and more expensive
* Technical assumptions become hidden failure points

The largest failure mode in agentic software development is not implementation.

It is poor specifications.

---

## Target Users

* Engineers using Codex
* Teams using agentic SDLC workflows
* Developers using Cursor, Claude Code, Aider, or similar coding agents
* Technical leads reviewing feature requests before implementation

---

## Goals

1. Analyze repository architecture automatically
2. Evaluate whether a feature fits the existing architecture
3. Run PM and Engineer specialist agents in parallel
4. Identify product and technical ambiguities
5. Generate an Agentic Readiness Score (ARS)
6. Suggest an optimal sub-agent delegation strategy
7. Produce a Codex-ready implementation prompt
8. Save a reusable readiness report

---

## Non-Goals

* Generate production code
* Create pull requests
* Modify repositories
* Replace project planning workflows
* Replace Codex

Ready4Codex exists before implementation begins.

---

## Tech Stack

* Python 3.11+
* OpenAI Responses API
* PyGithub
* Rich
* asyncio
* Markdown reports

CLI only.

No frontend.

---

## Repo Structure

```text
ready4codex/

├── agents/
│   ├── pm_agent.py
│   ├── engineer_agent.py
│   └── synthesis_agent.py
│
├── skills/
│   └── codex-readiness/
│       └── SKILL.md
│
├── reports/
│
├── main.py
├── requirements.txt
└── README.md
```

---

## System Workflow

```text
GitHub Repo
+
Feature Request

↓

Repository Analysis

↓

PM Agent
||
Engineer Agent

↓

Synthesis Agent

↓

Agentic Readiness Report

↓

Codex Execution Plan

↓

Codex-Ready Prompt
```

---

## Step 1 - Repository Analysis

Inspect:

* README.md
* Repository structure
* src/
* app/
* tests/
* package.json
* pyproject.toml
* requirements.txt

Generate:

Architecture Summary

Example:

```json
{
  "backend": "FastAPI",
  "database": "PostgreSQL",
  "tests": "pytest",
  "auth": "JWT"
}
```

---

## Architecture Fit Analysis

Determine:

* impacted modules
* affected services
* feature ownership boundaries
* required infrastructure changes
* implementation complexity

Example:

```json
{
  "impacted_modules": [
    "users",
    "notifications"
  ],
  "new_infrastructure_required": [
    "email service"
  ]
}
```

---

## Step 2 - PM Agent

Prompt:

```text
You are a senior product manager reviewing a feature request.

Identify:

* unclear requirements
* missing business rules
* undefined user flows
* acceptance criteria gaps

Be specific and concise.

Return JSON only.
```

Output:

```json
{
  "must_clarify": [],
  "should_clarify": [],
  "open_questions": []
}
```

---

## Step 3 - Engineer Agent

Prompt:

```text
You are a staff software engineer reviewing a feature request against an existing codebase.

Identify:

* technical ambiguity
* architecture risks
* integration concerns
* missing implementation details
* infrastructure gaps

Return JSON only.
```

Output:

```json
{
  "risks": [],
  "missing_infrastructure": [],
  "open_questions": []
}
```

---

## Step 4 - Testability Analysis

Evaluate whether requirements are:

* measurable
* verifiable
* testable
* automatable

Example:

Bad:

```text
Notifications should work well.
```

Good:

```text
Users receive an email notification within 60 seconds of joining a project.
```

Output:

```json
{
  "testability_score": 75,
  "weak_requirements": [],
  "improved_acceptance_criteria": []
}
```

---

## Step 5 - Synthesis Agent

Combine outputs from:

* Repository Analysis
* PM Agent
* Engineer Agent
* Testability Analysis

Generate:

Agentic Readiness Score (ARS)

Start at:

100

Subtract:

* Must Clarify: -10 each
* Engineering Risk: -8 each
* Missing Infrastructure: -12 each
* Poor Testability: -15

Verdict:

80-100
READY

50-79
NEEDS WORK

0-49
NOT READY

---

## Step 6 - Sub-Agent Execution Plan

Generate a suggested delegation strategy.

Example:

Agent 1
Backend API + Data Model

Files:

* users/
* models/

Agent 2
Notification Service

Files:

* notifications/
* workers/

Agent 3
Testing + Documentation

Files:

* tests/
* docs/

---

## Step 7 - Codex-Ready Prompt

Generate a complete implementation prompt.

Example:

```text
Implement project join notifications.

Repository Context:
[architecture summary]

Requirements:
[clarified requirements]

Acceptance Criteria:
[testable criteria]

Testing Requirements:
[required tests]

Implementation Constraints:
[repo-specific constraints]

Do not begin implementation until all acceptance criteria have been validated.
```

This output is copy-paste ready for Codex.

---

## Skill Definition

skills/codex-readiness/SKILL.md

Purpose:

Before implementation:

1. Check requirement clarity
2. Check architecture fit
3. Check testability
4. Check deployment impact
5. Generate execution plan

Never recommend implementation until all critical ambiguities are surfaced.

---

## CLI Usage

```bash
python main.py \
  --repo https://github.com/org/project \
  --feature "Add notifications when users join projects"
```

---

## Final Output

```text
========================================

READY4CODEX REPORT

========================================

Repository:
github.com/company/project

Feature:
Add project join notifications

Agentic Readiness Score:
61 / 100

Verdict:
NOT READY FOR CODEX

Product Gaps:

• Who receives notifications?
• Can users disable notifications?
• Which delivery channels exist?

Engineering Risks:

• No email service detected
• Retry strategy undefined
• Database migration impact unclear

Architecture Fit:

• Users module impacted
• Notifications module impacted
• New email infrastructure required

Suggested Agent Plan:

Agent 1
Backend API + Data Model

Agent 2
Notification Service

Agent 3
Tests + Documentation

Codex-Ready Prompt:

[paste-ready prompt]

========================================
```

---

## Acceptance Criteria

* Accept GitHub URL and feature request as CLI arguments
* Analyze any public GitHub repository
* Run PM and Engineer agents concurrently
* Generate deterministic ARS score
* Generate architecture fit analysis
* Generate testability analysis
* Generate delegation plan
* Generate Codex-ready prompt
* Save report as Markdown
* Complete in under 30 seconds

---

## Success Metrics

A judge pastes:

* a GitHub repository URL
* a feature request

Within 30 seconds Ready4Codex produces:

* an Agentic Readiness Score
* product clarification requests
* technical risks
* architecture impact analysis
* delegation recommendations
* a Codex-ready implementation prompt

The output should immediately help a developer decide whether a task is ready for agentic implementation.
