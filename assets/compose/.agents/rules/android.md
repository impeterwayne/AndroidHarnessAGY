---
trigger: always_on
---

# Android Workspace Rule: Architecture, Design System & Resources

## 1. Android Code Safety & Architecture
- Maintain Clean Architecture and Orbit MVI patterns (`ContainerHost`, `intent`, `reduce`, `postSideEffect`).
- Use `@HiltViewModel` for state holders and keep composable screens purely stateless (`UiState` + `onEvent`/`onAction` callbacks).
- Preserve existing ViewModel logic, UseCases, and navigation contracts when updating UI.
- Never add unnecessary comments in Kotlin code (`//`, `/* */`).
- Never hardcode user-facing strings (always declare in `res/values/strings.xml` and use `stringResource(...)`).

## 2. Design System & Image Loading Policy
- **Design System Tokens**: Use `com.genesys.core.designsystem.theme.AppTheme` (`AppTheme.colorScheme`, `AppTheme.typography`, `AppTheme.shapes`, `AppTheme.spacing`, `AppTheme.strokes`) and design system components (`AppText`, `AppPrimaryButton`, `AppSecondaryButton`, `AppChip`, `AppPanel`, `AppDivider`, etc.).
- **Vector Icons**: Simple 1-2 color vector icons (24-48dp) must be converted into `res/drawable/ic_<name>.xml` and displayed using Compose `Icon` or `Image` with `painterResource(id = R.drawable.ic_<name>)`.
- **Image Loading (`GlideImage`)**: For dynamic remote images or complex artwork in Jetpack Compose, use Skydoves Landscapist Glide (`com.skydoves.landscapist.glide.GlideImage`) with proper `previewPlaceholder`, `loading`, and `failure` states.

## 3. Device & Build Ownership
- **Gradle never installs**: no `installDebug`, `connectedAndroidTest`, or any `install*`/`uninstall*`/`connected*` task. They pick a device themselves and overwrite whatever another git worktree is verifying on it. Assemble, then `andrun install --no-build --launch --json`.
- **Never `adb install`**: same reason. `andrun` resolves the device this worktree leased.
- **Never pass a device or serial**: the `device-gate` hook leases one on your first device command and injects `-s <serial>` into `scrcpy-cli` and `adb` for you. If it denies because every device is leased elsewhere, queue with `andrun queue ensure --wait-timeout 600 --json` — do not work around it.

