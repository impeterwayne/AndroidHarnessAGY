# Architecture Violation Rules

## Layer Order (strict)
```
UI  →  ViewModel  →  Repository  →  DataSource
 0         1               2              3
```

## Detection Rules

### CRITICAL violations (layer skip ≥ 2)
| Pattern | Rule ID | Description |
|---------|---------|-------------|
| UI -> Repository | C1 | Screen directly calls Repository |
| UI -> DataSource | C2 | Screen directly calls DataSource |
| ViewModel -> DataSource | C3 | ViewModel skips Repository |

### WARNING violations (layer skip = 1, wrong direction)
| Pattern | Rule ID | Description |
|---------|---------|-------------|
| Repository -> ViewModel | W1 | Repository holds ViewModel reference |
| DataSource -> Repository | W2 | DataSource holds Repository reference |

### INFO notices
| Pattern | Rule ID | Description |
|---------|---------|-------------|
| Screen(XML) + Screen(Compose) | I1 | Migration in progress — both UI types exist |
| Module has no exports defined | I2 | Module exports not documented |
| Circular module dependency | I3 | Module A depends on Module B which depends on Module A |

## How to detect

When indexing a file, for every `->` relation found:
1. Identify the layer index of the left side (caller)
2. Identify the layer index of the right side (callee)
3. If callee_layer ≤ caller_layer AND it's not a ~> data flow: flag as violation
4. Compute skip = callee_layer - caller_layer
   - skip ≥ 2 → CRITICAL
   - wrong direction → WARNING
   - Presence of both XML and Compose for same screen → INFO I1
