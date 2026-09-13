# Asset Manifest — the stage 2 to stage 3 contract

`docs/<feature>/figma-assets.json` is what stage 2 actually did, as opposed to §8 of the
spec, which is what stage 1 asked for. The two differ every time an icon already existed,
a name collided, or a token snapped — and stage 3 needs the difference, not the request.

Stage 2 writes it. Stage 3 reads it before it writes a single `R.drawable` reference.
Without it, a name mismatch surfaces as an unresolved symbol at compile time at best, and
as a blank icon at runtime at worst.

Write the manifest **even when nothing was exported**. An empty manifest with
`"exported": []` proves stage 2 ran and found everything already present; a missing file
is indistinguishable from a stage that never ran.

## Schema

```json
{
  "feature": "home",
  "spec": "docs/home/figma-spec.md",
  "generated": "2026-09-12",
  "exported": [
    {
      "name": "ic_back",
      "nodeId": "145:222",
      "path": "core/designsystem/src/main/res/drawable/ic_back.xml",
      "kind": "vector",
      "viewport": "24x24",
      "tinted": false
    },
    {
      "name": "img_empty_devices",
      "nodeId": "145:643",
      "path": "feature/home/src/main/res/drawable-nodpi/img_empty_devices.png",
      "kind": "raster",
      "render": "painterResource"
    }
  ],
  "reused": [
    {
      "name": "ic_close",
      "path": "core/designsystem/src/main/res/drawable/ic_close.xml",
      "requestedAs": "ic_dismiss"
    }
  ],
  "tokens": {
    "added": [
      {
        "token": "colorScheme.colorAccentSuccess",
        "file": "core/designsystem/src/main/kotlin/.../Color.kt",
        "value": "#3DDC97"
      }
    ],
    "snapped": [
      {
        "figmaValue": "15dp",
        "token": "spacing.md",
        "tokenValue": "16dp",
        "delta": "1dp"
      }
    ],
    "conflicts": [
      {
        "token": "colorScheme.colorBgBase",
        "existing": "#0E0F13",
        "figma": "#101218",
        "action": "NOT CHANGED — shared surface, caller decides"
      }
    ]
  },
  "renamed": [
    {
      "specName": "ic_arrow-back",
      "actualName": "ic_arrow_back",
      "reason": "hyphen is a build failure in a resource name"
    }
  ],
  "verification": {
    "command": "./gradlew :app:processDebugResources",
    "exitCode": 0
  }
}
```

## Field rules

- `exported[].path` is **workspace-relative and must exist on disk** when the manifest is
  written. Stage 3 and `verifier` both resolve it literally.
- `reused[].requestedAs` is present only when the spec asked for a different name than the
  drawable that already existed. Its presence is what tells stage 3 to use the existing
  name instead of the spec's.
- `renamed[]` covers every deviation from §8 of the spec. **A name changed without a
  `renamed` entry is the defect this file exists to prevent.**
- `tokens.snapped[]` is not optional bookkeeping — it is the record that a design value was
  deliberately not honoured to the pixel, which is exactly what floor 4 of `verifier` will
  otherwise flag as a layout defect.
- `tokens.conflicts[]` means stage 2 refused to act. Every entry needs a caller decision
  before the feature is done.
- `verification` is the resource compile stage 2 ran. An exported drawable with no
  verification entry has not been proven to parse.

## How stage 3 uses it

1. Read the manifest before writing any resource reference.
2. For every `R.drawable.*` it intends to emit, find the `exported` or `reused` entry. No
   entry means the drawable does not exist — stop and report the gap rather than writing a
   reference that will not resolve.
3. Apply `renamed` and `reused[].requestedAs` mappings to the names the spec proposed.
4. Treat every `tokens.conflicts[]` entry as blocking for the elements it affects; build
   the rest.
