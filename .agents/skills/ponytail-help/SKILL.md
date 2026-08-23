---
name: ponytail-help
description: >
  Quick-reference cheat sheet for all Ponytail modes, commands, and skills.
  Trigger: /ponytail-help, "ponytail help", "how do I use ponytail", "ponytail cheat sheet".
---

# Ponytail Help & Reference

Quick reference card for all Ponytail skills and commands in this workspace:

## Intensity Modes
| Mode | How to invoke | Behavior |
| :--- | :--- | :--- |
| **Lite** | `ponytail lite` | Build requested solution, note the simpler/lazier alternative in 1 line. |
| **Full** | `ponytail` *(default)* | Enforces the decision ladder: YAGNI $\to$ Codebase reuse $\to$ Stdlib/KTX $\to$ Native Android $\to$ Shortest clean code. |
| **Ultra** | `ponytail ultra` | Radical YAGNI. Actively challenges requirements and deletes before adding. |

## Available Skills
| Skill | Trigger / Command | Purpose |
| :--- | :--- | :--- |
| **ponytail** | `/ponytail`, `"be lazy"`, `"simplest solution"` | Core lazy senior dev coding mode. |
| **ponytail-review** | `/ponytail-review`, `"review for over-engineering"` | Diff/PR review hunting bloat and unnecessary abstractions. |
| **ponytail-audit** | `/ponytail-audit`, `"audit this repo"` | Repo-wide scan for dead code, boilerplate, and stdlib reinventions. |
| **ponytail-debt** | `/ponytail-debt`, `"ponytail debt"` | Collects all `ponytail:` shortcut markers into a tracked ledger. |
| **ponytail-gain** | `/ponytail-gain`, `"ponytail gain"` | Shows benchmark scoreboard (LOC, cost, and time savings). |
| **ponytail-help** | `/ponytail-help`, `"ponytail help"` | Displays this guide. |
