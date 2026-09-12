# Figma Layout to Jetpack Compose & Android XML Mapping Guide

This guide maps Figma design properties directly to Jetpack Compose and Android XML equivalents.

---

## 1. Auto-Layout to Compose Layout Mapping

| Figma Property | Figma Value | Compose Equivalent | Android XML Equivalent |
|---|---|---|---|
| `layoutMode` | `HORIZONTAL` | `Row(...)` | `LinearLayout (android:orientation="horizontal")` or `ConstraintLayout` |
| `layoutMode` | `VERTICAL` | `Column(...)` | `LinearLayout (android:orientation="vertical")` or `ConstraintLayout` |
| `layoutMode` | `NONE` (Absolute positioning) | `Box(...)` with `Modifier.align(...)` or `Modifier.offset(...)` | `FrameLayout` or `ConstraintLayout` with constraints |
| `itemSpacing` | `<N> px` | `horizontalArrangement = Arrangement.spacedBy(<N>.dp)` or `verticalArrangement = Arrangement.spacedBy(<N>.dp)` | `app:dividerGap="<N>dp"` or item margins |
| `primaryAxisAlignItems` | `MIN` | `Arrangement.Start` / `Arrangement.Top` | `gravity="start/top"` |
| `primaryAxisAlignItems` | `CENTER` | `Arrangement.Center` | `gravity="center"` |
| `primaryAxisAlignItems` | `MAX` | `Arrangement.End` / `Arrangement.Bottom` | `gravity="end/bottom"` |
| `primaryAxisAlignItems` | `SPACE_BETWEEN` | `Arrangement.SpaceBetween` | `ConstraintLayout` chain or weight |
| `counterAxisAlignItems` | `MIN` | `Alignment.Top` / `Alignment.Start` | `layout_gravity="top/start"` |
| `counterAxisAlignItems` | `CENTER` | `Alignment.CenterVertically` / `Alignment.CenterHorizontally` | `layout_gravity="center"` |
| `counterAxisAlignItems` | `MAX` | `Alignment.Bottom` / `Alignment.End` | `layout_gravity="bottom/end"` |

---

## 2. Padding Mapping

Figma provides:
- `paddingTop`, `paddingBottom`, `paddingLeft` (or `paddingStart`), `paddingRight` (or `paddingEnd`)

**Compose Mapping:**
- Uniform: `Modifier.padding(all = 16.dp)`
- Symmetric: `Modifier.padding(horizontal = 16.dp, vertical = 12.dp)`
- Asymmetric: `Modifier.padding(start = 16.dp, top = 12.dp, end = 16.dp, bottom = 24.dp)`

---

## 3. Sizing Modes (Horizontal & Vertical Resizing)

| Figma Resizing Mode | Compose Modifier | Android XML Attribute |
|---|---|---|
| `FIXED` width/height | `Modifier.width(<w>.dp)` / `Modifier.height(<h>.dp)` / `Modifier.size(<w>.dp, <h>.dp)` | `android:layout_width="<w>dp"` |
| `HUG` contents | `Modifier.wrapContentSize()` (or default behavior without fixed width/height) | `android:layout_width="wrap_content"` |
| `FILL` container (in Row/Column) | `Modifier.weight(1f)` (in flex layout) or `Modifier.fillMaxWidth()` / `Modifier.fillMaxHeight()` | `android:layout_width="0dp"`, `android:layout_weight="1"` or `match_parent` |

---

## 4. Visual Styles Mapping

### Corner Radius (Shapes)
- `cornerRadius: 12` -> `Modifier.clip(RoundedCornerShape(12.dp))` or `CardDefaults.shape`
- Individual corners (`topLeftRadius`, etc.) -> `RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp)`

### Fills (Colors & Gradients)
- Solid Color: `Modifier.background(color)` or `Surface(color = ...)`
- Linear Gradient: `Modifier.background(Brush.linearGradient(colors = listOf(...), start = ..., end = ...))`
- Radial Gradient: `Modifier.background(Brush.radialGradient(colors = listOf(...)))`

### Strokes & Borders
- Border: `Modifier.border(width = 1.dp, color = strokeColor, shape = RoundedCornerShape(12.dp))`

### Effects (Drop Shadows, Elevation, Blurs)
- Drop Shadow: `Modifier.shadow(elevation = 4.dp, shape = RoundedCornerShape(12.dp))`
- Inner Shadow / Custom Blur: Blur modifier or Canvas drawing where supported.

---

## 5. Typography Mapping

| Figma Property | Compose `TextStyle` Field |
|---|---|
| `fontSize` | `fontSize = 16.sp` |
| `fontWeight` (400, 500, 600, 700) | `FontWeight.Normal`, `FontWeight.Medium`, `FontWeight.SemiBold`, `FontWeight.Bold` |
| `lineHeightPx` | `lineHeight = 24.sp` |
| `letterSpacing` | `letterSpacing = 0.5.sp` |
| `textAlignHorizontal` (LEFT, CENTER, RIGHT) | `textAlign = TextAlign.Start / Center / End` |
