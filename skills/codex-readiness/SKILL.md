# Skill: codex-readiness

## Name
codex-readiness

## Description
Determine whether a feature request is sufficiently
specified before agentic implementation begins.

## When to Use
Before any implementation, PR, or code generation
begins.

Input: GitHub repo URL + plain-English feature request
Output: Readiness report + Codex-ready prompt

---

## Evaluation Areas

### 1. Requirement Clarity
Identify:
- missing requirements
- ambiguous requirements
- undefined user flows
- unclear acceptance criteria

### 2. Architecture Fit
Identify:
- impacted modules
- affected services
- new infrastructure requirements
- architectural inconsistencies

### 3. Technical Risk
Identify:
- implementation risks
- integration concerns
- deployment concerns
- scalability concerns

### 4. Testability
Determine whether requirements are:
- measurable
- verifiable
- automatable

Rewrite vague requirements into testable
acceptance criteria when possible.

Example:
Bad:  "Notifications should work well."
Good: "User receives email within 60 seconds
       of joining a project."

### 5. Delegation Planning
Suggest an optimal sub-agent execution plan:
- agent responsibilities
- impacted files
- implementation boundaries

---

## Scoring Rules
Start at 100.
- Must Clarify item:       -10 each
- Engineering Risk:         -8 each
- Missing Infrastructure:  -12 each
- Poor Testability:        -15

Verdicts:
80-100 → ✅ READY
50-79  → ⚠️  NEEDS WORK
0-49   → ❌ NOT READY

---

## Output Requirements
Always generate in this order:
1. Agentic Readiness Score (ARS)
2. Verdict
3. Product Gaps
4. Engineering Risks
5. Architecture Fit Analysis
6. Testability Analysis
7. Suggested Agent Plan
8. Codex-Ready Prompt

Never recommend implementation until all
critical ambiguities are surfaced.

## Success Criteria

The task is considered READY only when:

- Critical requirements are defined
- Acceptance criteria are testable
- Architecture impact is understood
- No blocking ambiguities remain
