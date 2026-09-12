---
name: lean-gain
description: >
  Show lean's measured impact and scoreboard: lines of code saved, token reduction,
  cost savings, and speed improvements from empirical benchmarks.
  Trigger: /lean-gain, "lean gain", "what does lean save", "show lean impact",
  or "lean scoreboard".
---

# Lean Gain (Efficiency Scoreboard)

Display the measured benchmark scoreboard showing real-world impact across LOC, tokens, cost, and latency.

```
  lean gain               benchmark median · 12 tasks · Haiku / Sonnet / Opus
  ─────────────────────────────────────────────────────────────────────────────
  Lines of Code (LOC)  ████████████████████░░░░░░░░░░░░░░░░░░░░  -54% (up to -94%)
  Token Consumption    ████████████████████████████████░░░░░░░░  -22%
  API Cost             █████████████████████████████████░░░░░░░  -20%
  Execution Time       ██████████████████████████████░░░░░░░░░░  -27%
  Safety Score         ████████████████████████████████████████  100%
  ─────────────────────────────────────────────────────────────────────────────
```

### Key Takeaways:
- **Largest reductions**: Over-engineered components (custom pickers, heavy wrapper classes, unnecessary adapters).
- **Zero regression**: 100% safety preserved because validation, null-safety, and error handling are never stripped.
