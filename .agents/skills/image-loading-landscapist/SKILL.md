---
name: image-loading-landscapist
description: Specialized skill for loading images using Skydoves Landscapist Glide in Jetpack Compose, managing placeholder/loading/error states, and following premium performance guidelines.
---

# Landscapist Glide Image Loading Skill

## Overview

This skill is specialized for implementing premium, high-performance image loading in Jetpack Compose using [Skydoves Landscapist Glide](https://github.com/skydoves/landscapist).
Landscapist Glide bridges standard Glide image loading with Compose state, offering built-in state handlers, plugins, and preview capabilities.

Use this skill when:
- Implementing dynamic remote images (URLs), raw resource files, or drawables in Compose layouts.
- Designing loading placeholders, progress indicators, shimmer, or error states for images.
- Optimizing image memory footprint, cache strategies, or performance metrics in feature modules.

---

## 1. Setup & Dependencies

Before using `GlideImage`, verify that the feature module has the necessary landscapist libraries declared in `build.gradle.kts`:

```kotlin
// In target feature/module's build.gradle.kts
dependencies {
    implementation(libs.landscapist.glide)
    implementation(libs.landscapist.placeholder)
    implementation(libs.landscapist.animation)
}
```

Ensure the versions are unified through `gradle/libs.versions.toml`:
```toml
[versions]
landscapist = "2.4.4"

[libraries]
landscapist-glide = { module = "com.github.skydoves:landscapist-glide", version.ref = "landscapist" }
landscapist-placeholder = { module = "com.github.skydoves:landscapist-placeholder", version.ref = "landscapist" }
landscapist-animation = { module = "com.github.skydoves:landscapist-animation", version.ref = "landscapist" }
```

---

## 2. Standard Usage Pattern

Below is the canonical implementation pattern for `GlideImage`, as demonstrated in `:feature:pokedex` (e.g., [PokemonCard.kt](file:///d:/Quest/AndroidHarnessAGY/CodeBaseCompose/feature/pokedex/src/main/java/com/genesys/feature/pokedex/presentation/list/components/PokemonCard.kt) and [PokemonDetailContent.kt](file:///d:/Quest/AndroidHarnessAGY/CodeBaseCompose/feature/pokedex/src/main/java/com/genesys/feature/pokedex/presentation/detail/components/PokemonDetailContent.kt)).

```kotlin
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.genesys.core.designsystem.theme.AppTheme
import com.genesys.feature.pokedex.presentation.common.components.CustomCircularProgressIndicator
import com.skydoves.landscapist.glide.GlideImage

@Composable
fun PokemonImage(
    imageUrl: String,
    modifier: Modifier = Modifier,
    contentDescription: String? = null
) {
    GlideImage(
        imageModel = { imageUrl },
        modifier = modifier.size(80.dp),
        contentDescription = contentDescription,
        // Shows a system icon or custom drawable inside Layout Preview
        previewPlaceholder = painterResource(id = android.R.drawable.ic_menu_gallery),
        
        // Custom Composable to display while the image is fetching
        loading = {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(8.dp))
                    .background(Color(0x0FFFFFFF)),
                contentAlignment = Alignment.Center
            ) {
                CustomCircularProgressIndicator(
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(24.dp),
                    color = AppTheme.colorScheme.colorPrimary
                )
            }
        },
        
        // Custom Composable to display if the image fetch fails
        failure = {
            Image(
                painter = painterResource(id = android.R.drawable.ic_menu_gallery),
                contentDescription = "Failed to load image",
                colorFilter = ColorFilter.tint(AppTheme.colorScheme.colorBorder),
                modifier = Modifier.size(24.dp)
            )
        }
    )
}
```

---

## 3. Best Practices & Design Tokens (NO Hardcode Rule)

| Category | Do | Don't |
| :--- | :--- | :--- |
| **Strings & Text** | **MANDATORY**: Extract all text and accessibility/content description strings to `strings.xml`. Never hardcode raw strings. | Hardcode visual labels or accessibility descriptions directly inside Composable files. |
| **Preview Capability** | **MANDATORY**: Always provide `previewPlaceholder` so layouts render successfully in Android Studio's preview window. | Omit `previewPlaceholder`, causing layout previews to appear blank or break. |
| **Loading State styling** | Use `CustomCircularProgressIndicator` tinted with theme colors (`AppTheme.colorScheme.colorPrimary`) or themed shimmers. | Use generic unstyled Android `ProgressBar` or hardcoded primary colors (`Color.Blue`). |
| **Failure fallback** | Render a meaningful, tintable icon representing the missing resource (e.g. system drawable or generic item vector). | Show an empty box, crash, or leave a missing space. |
| **Sizing and Modifiers** | Define strict dimensions (`Modifier.size()`, `.fillMaxSize()`) on the `GlideImage` or its parent layout to prevent sizing loops. | Let `GlideImage` scale infinitely without constrained boundaries, causing infinite recompositions. |
| **Accessibility** | Supply descriptive `contentDescription` strings for important visual components (fetched from standard `strings.xml`). | Leave `contentDescription` as null for primary visual components, or hardcode accessibility strings in code. |

---

## 4. Advanced: Animations & Crossfade

To enable elegant transitions (crossfade) when images load successfully, leverage Landscapist plugins from `com.skydoves.landscapist.animation.crossfade`:

```kotlin
import com.skydoves.landscapist.animation.crossfade.CrossfadePlugin
import com.skydoves.landscapist.components.rememberImageComponent

GlideImage(
    imageModel = { imageUrl },
    modifier = Modifier.size(120.dp),
    component = rememberImageComponent {
        +CrossfadePlugin(duration = 350) // Smooth 350ms transition
    },
    previewPlaceholder = painterResource(id = android.R.drawable.ic_menu_gallery)
)
```

---

## 5. Pre-Delivery Checklist

Ensure your implementation of `GlideImage` complies with all of the following rules:

- [ ] **Strings Externalized**: All accessibility text and user-facing labels are placed inside `strings.xml` (No hardcoded strings).
- [ ] **Previews Ready**: `previewPlaceholder` is defined with a lightweight drawable resource.
- [ ] **No Hardcoded Tokens**: Any custom backgrounds or indicators in the `loading` or `failure` blocks use `AppTheme.colorScheme` and `AppTheme.spacing` tokens.
- [ ] **Accessibility Compliant**: A valid `contentDescription` from resources is provided unless the image is purely decorative.
- [ ] **Error Safety**: Custom `failure` block returns a fallback layout with vector graphics rather than breaking layout bounds.
- [ ] **Performance Guard**: Modifier bounds (width/height/size) are constrained explicitly to prevent recomposition overhead.
- [ ] **Zero Redundancy**: Pre-existing `CustomCircularProgressIndicator` or design system equivalents are reused rather than rebuilding loading indicators from scratch.
