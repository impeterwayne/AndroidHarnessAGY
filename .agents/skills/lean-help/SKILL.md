---
name: lean-help
description: >
  Quick-reference cheat sheet for all Lean modes, commands, and skills.
  Trigger: /lean-help, "lean help", "how do I use lean", "lean cheat sheet".
---

# Lean Help & Reference (Radical Simplicity)

Quick reference card for all Lean skills and commands in this workspace, fusing the Lazy Senior Developer with George Hotz's radical simplicity (*"Complexity is the enemy — LOC is debt, not output"*):

## Intensity Modes
| Mode | How to invoke | Behavior |
| :--- | :--- | :--- |
| **Lite** | `lean lite` | Build requested solution, note the simpler/lazier alternative in 1 line. |
| **Full** | `lean` *(default)* | Enforces the decision ladder: Delete/Collapse $\to$ YAGNI $\to$ Codebase reuse $\to$ Stdlib/KTX $\to$ Native Android $\to$ Shortest clean code. |
| **Ultra** | `lean ultra` | Radical YAGNI & Geohot mode. Actively challenges requirements, prioritizes negative diffs, flags wide interfaces ($>4$ params), and deletes before adding. |

## Available Skills
| Skill | Trigger / Command | Purpose |
| :--- | :--- | :--- |
| **lean** | `/lean`, `"be lazy"`, `"simplest solution"`, `"geohot"` | Core radical simplicity & minimal code mode. |
| **lean-review** | `/lean-review`, `"review for over-engineering"` | Diff/PR review hunting bloat, wide interfaces, layer sprawl, and dead code. |
| **lean-audit** | `/lean-audit`, `"audit this repo"` | Repo-wide scan for dead code, boilerplate, and stdlib reinventions. |
| **lean-debt** | `/lean-debt`, `"lean debt"` | Collects all `lean:` shortcut markers into a tracked ledger. |
| **lean-gain** | `/lean-gain`, `"lean gain"` | Shows benchmark scoreboard (LOC, cost, and time savings). |
| **lean-help** | `/lean-help`, `"lean help"` | Displays this guide. |
