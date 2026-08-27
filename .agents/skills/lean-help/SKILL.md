---
name: lean-help
description: >
  Quick-reference cheat sheet for all Lean modes, commands, and skills.
  Trigger: /lean-help, "lean help", "how do I use lean", "lean cheat sheet".
---

# Lean Help & Reference

Quick reference card for all Lean skills and commands in this workspace:

## Intensity Modes
| Mode | How to invoke | Behavior |
| :--- | :--- | :--- |
| **Lite** | `lean lite` | Build requested solution, note the simpler/lazier alternative in 1 line. |
| **Full** | `lean` *(default)* | Enforces the decision ladder: YAGNI $\to$ Codebase reuse $\to$ Stdlib/KTX $\to$ Native Android $\to$ Shortest clean code. |
| **Ultra** | `lean ultra` | Radical YAGNI. Actively challenges requirements and deletes before adding. |

## Available Skills
| Skill | Trigger / Command | Purpose |
| :--- | :--- | :--- |
| **lean** | `/lean`, `"be lazy"`, `"simplest solution"` | Core lazy senior dev coding mode. |
| **lean-review** | `/lean-review`, `"review for over-engineering"` | Diff/PR review hunting bloat and unnecessary abstractions. |
| **lean-audit** | `/lean-audit`, `"audit this repo"` | Repo-wide scan for dead code, boilerplate, and stdlib reinventions. |
| **lean-debt** | `/lean-debt`, `"lean debt"` | Collects all `lean:` shortcut markers into a tracked ledger. |
| **lean-gain** | `/lean-gain`, `"lean gain"` | Shows benchmark scoreboard (LOC, cost, and time savings). |
| **lean-help** | `/lean-help`, `"lean help"` | Displays this guide. |
