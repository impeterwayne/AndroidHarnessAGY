---
name: code-review
description: Audits modified code for architectural compliance, over-engineering, design token usage, and Android security.
trigger:
  slash_command: /code-review
  keywords:
    - "review code"
    - "audit diff"
    - "check architecture"
skills:
  - ponytail-review
  - android-resource-policy
  - android-intent-security
---

# Code Review & Simplification Workflow

## Phase 1: Diff & Scope Analysis
- Inspect git status and changed files across modules.
- Check for architectural boundary violations (e.g. feature depending on data layer).

## Phase 2: Simplification Audit (Ponytail)
- Identify over-engineering, unnecessary wrapper classes, and redundant abstractions.
- Ensure standard Kotlin stdlib / Android KTX utilities are preferred.

## Phase 3: Resource & Security Inspection
- Verify all user-facing strings are extracted to strings.xml.
- Ensure colors use AppTheme.colorScheme tokens.
- Audit exported components in AndroidManifest.xml for intent security.

## Phase 4: Feedback Summary
- Generate concise review report with line-by-line recommendations.