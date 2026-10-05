---
name: xxpermissions-ktx
description: Guides defining Android dangerous and special permissions via PermissionLists and implementing clean pre-request rationale and permanent denial ("do not ask again") dialog flows using the XXPermissions Kotlin DSL (xxpermissionktx).
---

# XXPermissions-KTX: Permission Definition & Rationale Flow

This skill provides senior Android engineering guidelines and code recipes for requesting runtime, dangerous, and special permissions using the `xxpermissionktx` library and the `com.hjq.permissions.permission.PermissionLists` catalog.

## Core Principles

1. **Single Source of Truth (`PermissionLists`)**:
   Always reference permission objects through `PermissionLists.get<Name>Permission()` rather than hardcoding raw string manifests. `PermissionLists` encapsulates version compatibility checks, automatic fallback mappings (e.g., adding `READ_EXTERNAL_STORAGE` on Android 12 and below when requesting Android 13 media permissions), and permission group metadata.
2. **Two-Tier Educational UX**:
   - **Rationale (`onShouldShowRationale`)**: Triggered *before* the system dialog when Android determines a rationale should be shown (`ActivityCompat.shouldShowRequestPermissionRationale`) or when a special permission is ungranted. Positive action button must say **"Grant"** / **"Continue"**, proceeding to the system prompt (`onUserResult.onResult(true)`).
   - **Do Not Ask Again (`onDoNotAskAgain`)**: Triggered *after* denial when the user checked "Don't ask again" or the OS permanently restricted the permission. Positive action button must say **"Go to Settings"**, opening the application settings page (`onUserResult.onResult(true)`).
3. **Deterministic User Result Dispatch**:
   Always execute `onUserResult.onResult(isAgree: Boolean)` from dialog buttons. Failing to invoke this callback stalls the permission interceptor queue. Dialogs must be non-cancelable (`setDialogCancelable(false)`) to prevent unhandled dismissals.
4. **Android 14+ Partial Access Awareness**:
   When requesting media permissions (`READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO`) on Android 14+ (API 34+), always pair with `READ_MEDIA_VISUAL_USER_SELECTED` and check for partial access (`hasSelectedOnly && !hasFullImages`).

---

## Architecture Overview

```
xxPermissions {
    permissions(PermissionLists.get...)
    
    onShouldShowRationale { rationaleList, onUserResult ->
        // 1. Pre-system prompt educational dialog
        // Positive: onUserResult.onResult(true)  -> Continues to OS prompt
        // Negative: onUserResult.onResult(false) -> Cancels request
    }
    
    onDoNotAskAgain { doNotAskAgainList, onUserResult ->
        // 2. Post-denial settings redirect dialog
        // Positive: onUserResult.onResult(true)  -> Opens System Settings
        // Negative: onUserResult.onResult(false) -> Dismisses
    }
    
    onResult { allGranted, grantedList, deniedList ->
        // 3. Final completion handler
    }
}
```

---

## Detailed References

- [Permission Catalog & Factory Reference](./references/permission_catalog.md): Complete categorization of the 151 permissions in `PermissionLists`, caching behavior, and OS version requirements.
- [Rationale & Dialog Architecture](./references/rationale_dialog_architecture.md): The decoupled `PermissionDialogContent` + `PermissionDialogContentMapper` + `PermissionDialogFragment` design pattern.
- [Sample Implementation Recipes](./examples/permission_request_recipes.md): Copy-pasteable Kotlin snippets for common scenarios (Media & Partial Picker, Overlay/Alarm Sequences, and Fragment usage).

---

## Step-by-Step Implementation Guide

### 1. Declare Permissions in `AndroidManifest.xml`
Ensure all permissions are declared in the manifest with required flags:
```xml
<!-- Example: Android 13 Nearby Wi-Fi Devices with location derivation disabled -->
<uses-permission
    android:name="android.permission.NEARBY_WIFI_DEVICES"
    android:usesPermissionFlags="neverForLocation"
    tools:targetApi="s" />

<!-- Backward compatibility for Android 12 and below -->
<uses-permission
    android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="32" />
```

### 2. Define Dialog Content Model & Mapper
Decouple dialog UI presentation from permission logic using a Mapper:

```kotlin
data class PermissionDialogContent(
    @field:DrawableRes val imageResId: Int,
    val title: String,
    val description: String
)

class PermissionDialogContentMapper(private val context: Context) {
    fun map(permission: String, isDoNotAskAgain: Boolean): PermissionDialogContent {
        return when (permission) {
            PermissionLists.getPostNotificationsPermission().getPermissionName() -> PermissionDialogContent(
                imageResId = android.R.drawable.ic_dialog_info,
                title = context.getString(
                    if (isDoNotAskAgain) R.string.permission_notification_denied_title
                    else R.string.permission_notification_needed_title
                ),
                description = context.getString(
                    if (isDoNotAskAgain) R.string.permission_notification_denied_description
                    else R.string.permission_notification_needed_description
                )
            )
            // Map remaining permissions...
            else -> PermissionDialogContent(
                imageResId = android.R.drawable.ic_dialog_alert,
                title = context.getString(
                    if (isDoNotAskAgain) R.string.permission_default_denied_title
                    else R.string.permission_default_needed_title
                ),
                description = context.getString(
                    if (isDoNotAskAgain) R.string.permission_default_denied_description
                    else R.string.permission_default_needed_description
                )
            )
        }
    }
}
```

### 3. Implement the Non-Cancelable Dialog Fragment
```kotlin
class PermissionDialogFragment : DialogFragment() {
    private var onUserResult: OnUserResultCallback? = null

    // Configure dialog to be non-cancelable outside button clicks
    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        val dialog = super.onCreateDialog(savedInstanceState)
        dialog.setCanceledOnTouchOutside(false)
        dialog.setCancelable(false)
        return dialog
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        binding.btnPositive.setOnClickListener {
            onUserResult?.onResult(true)
            dismiss()
        }
        binding.btnNegative.setOnClickListener {
            onUserResult?.onResult(false)
            dismiss()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        onUserResult = null
    }

    companion object {
        fun show(
            fragmentManager: FragmentManager,
            content: PermissionDialogContent,
            positiveButtonText: String,
            negativeButtonText: String,
            onUserResult: OnUserResultCallback
        ) {
            PermissionDialogFragment().apply {
                // pass arguments and callback
                this.onUserResult = onUserResult
            }.show(fragmentManager, "PermissionDialogFragment")
        }
    }
}
```

### 4. Execute the Request with Kotlin DSL
```kotlin
xxPermissions {
    permissions(
        PermissionLists.getPostNotificationsPermission(),
        PermissionLists.getScheduleExactAlarmPermission()
    )

    onShouldShowRationale { rationaleList, onUserResult ->
        val content = permissionDialogContentMapper.map(rationaleList[0], isDoNotAskAgain = false)
        PermissionDialogFragment.show(
            fragmentManager = supportFragmentManager,
            content = content,
            positiveButtonText = getString(R.string.permission_grant),
            negativeButtonText = getString(R.string.permission_cancel),
            onUserResult = onUserResult
        )
    }

    onDoNotAskAgain { doNotAskAgainList, onUserResult ->
        val content = permissionDialogContentMapper.map(doNotAskAgainList[0], isDoNotAskAgain = true)
        PermissionDialogFragment.show(
            fragmentManager = supportFragmentManager,
            content = content,
            positiveButtonText = getString(R.string.permission_go_to_settings),
            negativeButtonText = getString(R.string.permission_cancel),
            onUserResult = onUserResult
        )
    }

    onResult { allGranted, grantedList, deniedList ->
        if (allGranted) {
            Timber.d("All requested permissions granted!")
        } else {
            Timber.w("Permissions denied: %s", deniedList)
        }
    }
}
```

---

## Verification & Edge Cases Checklist

- [ ] **Xiaomi Device Overlay Traps**: On MIUI / HyperOS, `PermissionLists.getSystemAlertWindowPermission(forceXiaomi = true)` checks proprietary ops (`OP_BACKGROUND_START_ACTIVITY`, `OP_SHOW_WHEN_LOCKED`, `OP_POPUP_WINDOW`). Always set `forceXiaomi = true` if targeting Xiaomi background window behavior.
- [ ] **Parameterized Permissions**: Permissions requiring constructor arguments (e.g., `getBindAccessibilityServicePermission(MyService::class.java)`, `getNotificationServicePermission("channel_id")`, `getBindDeviceAdminPermission(MyReceiver::class.java)`) are **not** cached in `PERMISSION_CACHE_MAP`. Instantiate them directly with their arguments.
- [ ] **TargetSdk >= 33 Media Permissions**: Do not request `WRITE_EXTERNAL_STORAGE` on Android 13+ devices for media. Use `getReadMediaImagesPermission()`, `getReadMediaVideoPermission()`, or `getReadMediaAudioPermission()`. The library automatically downgrades to `READ_EXTERNAL_STORAGE` on Android 12 and below.
- [ ] **Android 14 Visual User Selected**: When user selects "Select photos and videos" instead of "Allow all", `allGranted` may be false if `READ_MEDIA_IMAGES` was requested alongside it. Check `val isRestricted = hasSelectedOnly && !hasFullImages` to proceed with partial media display.
