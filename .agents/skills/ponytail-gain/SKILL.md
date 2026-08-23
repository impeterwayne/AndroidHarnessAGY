---
name: ponytail-gain
description: >
  Show ponytail's measured impact and scoreboard: lines of code saved, token reduction,
  cost savings, and speed improvements from empirical benchmarks.
  Trigger: /ponytail-gain, "ponytail gain", "what does ponytail save", "show ponytail impact",
  or "ponytail scoreboard".
---

# Ponytail Gain (Efficiency Scoreboard)

Display the measured benchmark scoreboard showing real-world impact across LOC, tokens, cost, and latency.

```
  ponytail gain               benchmark median · 12 tasks · Haiku / Sonnet / Opus
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
