# Index File Templates

## Template: modules/<feature>.md

```markdown
# Module: :<scope>:<name>

## exports
- 

## dependencies
- 

## used_by
- 

## symbols

### UI
- 

### ViewModel
- 

### Repository
- 

### DataSource
- 

## graph (local)

```

---

## Template: _meta.md

```markdown
# Code Index Meta
last_updated: YYYY-MM-DD
total_modules: 0

## Legend
->  CALL (function / class invocation)
=>  NAVIGATION (screen transition)
~>  DATA FLOW (StateFlow, LiveData, callback) or COMPOSE MIGRATION

## Module Map
| Module | File | Status |
|--------|------|--------|

## Split Files
| Original | Split into |
|----------|------------|
```

---

## Template: graph/navigation.md

```markdown
# Navigation Graph
# Format: SourceScreen => DestinationScreen

```

---

## Template: graph/calls.md

```markdown
# Call Graph
# Format: Caller -> Callee

```

---

## Template: graph/data_flow.md

```markdown
# Data Flow Graph
# Format: Source ~> Consumer
# Also used for XML→Compose migration links

```

---

## Template: issues.md

```markdown
# Architecture Issues
last_checked: YYYY-MM-DD

## CRITICAL

## WARNING

## INFO
```
