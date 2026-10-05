# Permission Request Recipes

Copy-pasteable implementation recipes based on `XXPermission-ktx` sample code.

---

## 1. Sequence / Multi-Permission Request (Special + Dangerous)

Demonstrates requesting a mix of special permissions (`SYSTEM_ALERT_WINDOW`, `USE_FULL_SCREEN_INTENT`, `SCHEDULE_EXACT_ALARM`) and runtime permissions (`POST_NOTIFICATIONS`) with full rationale and settings recovery:

```kotlin
class MainActivity : AppCompatActivity() {

    private val contentMapper by lazy { PermissionDialogContentMapper(this) }

    fun requestSequencePermissions() {
        xxPermissions {
            permissions(
                PermissionLists.getSystemAlertWindowPermission(forceXiaomi = true),
                PermissionLists.getPostNotificationsPermission(),
                PermissionLists.getUseFullScreenIntentPermission(),
                PermissionLists.getScheduleExactAlarmPermission()
            )

            onShouldShowRationale { shouldShowRationaleList, onUserResult ->
                Timber.d("Showing rationale for: %s", shouldShowRationaleList)
                showPermissionDialog(
                    content = contentMapper.map(shouldShowRationaleList.first(), isDoNotAskAgain = false),
                    positiveButtonText = getString(R.string.permission_button_grant),
                    negativeButtonText = getString(R.string.permission_button_cancel),
                    onUserResult = onUserResult
                )
            }

            onDoNotAskAgain { doNotAskAgainList, onUserResult ->
                Timber.d("Permanently denied: %s", doNotAskAgainList)
                showPermissionDialog(
                    content = contentMapper.map(doNotAskAgainList.first(), isDoNotAskAgain = true),
                    positiveButtonText = getString(R.string.permission_button_go_to_settings),
                    negativeButtonText = getString(R.string.permission_button_cancel),
                    onUserResult = onUserResult
                )
            }

            onResult { allGranted, grantedList, deniedList ->
                if (allGranted) {
                    Timber.i("All sequence permissions granted successfully.")
                    startAppService()
                } else {
                    Timber.w("Permissions denied: %s", deniedList)
                }
            }
        }
    }

    private fun showPermissionDialog(
        content: PermissionDialogContent,
        positiveButtonText: String,
        negativeButtonText: String,
        onUserResult: OnUserResultCallback
    ) {
        PermissionDialogFragment.show(
            fragmentManager = supportFragmentManager,
            content = content,
            positiveButtonText = positiveButtonText,
            negativeButtonText = negativeButtonText,
            onUserResult = onUserResult
        )
    }
}
```

---

## 2. Android 14+ Media Permissions & Partial Access Handling

Demonstrates requesting scoped photo/video access with compatibility fallbacks and checking for partial access:

```kotlin
fun requestMediaWithPartialAccessSupport(activity: AppCompatActivity, onReady: (isPartial: Boolean) -> Unit) {
    activity.xxPermissions {
        permissions(
            PermissionLists.getReadMediaImagesPermission(),
            PermissionLists.getReadMediaVisualUserSelectedPermission(),
            PermissionLists.getWriteExternalStoragePermission()
        )

        onDoNotAskAgain { deniedList, onUserResult ->
            PermissionDialogFragment.show(
                fragmentManager = activity.supportFragmentManager,
                content = contentMapper.map(deniedList.first(), isDoNotAskAgain = true),
                positiveButtonText = activity.getString(R.string.permission_button_go_to_settings),
                negativeButtonText = activity.getString(R.string.permission_button_cancel),
                onUserResult = onUserResult
            )
        }

        onResult { allGranted, _, deniedList ->
            val hasFullImages = XXPermissions.isGrantedPermission(
                activity,
                PermissionLists.getReadMediaImagesPermission()
            )
            val hasSelectedOnly = XXPermissions.isGrantedPermission(
                activity,
                PermissionLists.getReadMediaVisualUserSelectedPermission()
            )
            val isRestricted = hasSelectedOnly && !hasFullImages

            if (allGranted || isRestricted) {
                Timber.d("Media access ready: full=%s, partial=%s", hasFullImages, isRestricted)
                onReady(isRestricted)
            } else {
                Timber.w("Media permissions denied: %s", deniedList)
            }
        }
    }
}
```

---

## 3. Location Request with Background Escalation

Demonstrates two-step location request (foreground first, background escalated only after foreground is granted):

```kotlin
fun requestLocationWithBackground(activity: AppCompatActivity) {
    activity.xxPermissions {
        permissions(
            PermissionLists.getAccessFineLocationPermission(),
            PermissionLists.getAccessCoarseLocationPermission()
        )

        onResult { fgGranted, _, _ ->
            if (fgGranted) {
                // Escalate to background location in a separate step as required by Android 11+
                activity.xxPermissions {
                    permissions(PermissionLists.getAccessBackgroundLocationPermission())

                    onShouldShowRationale { _, onUserResult ->
                        PermissionDialogFragment.show(
                            fragmentManager = activity.supportFragmentManager,
                            content = PermissionDialogContent(
                                imageResId = android.R.drawable.ic_dialog_map,
                                title = activity.getString(R.string.bg_location_title),
                                description = activity.getString(R.string.bg_location_rationale_desc)
                            ),
                            positiveButtonText = activity.getString(R.string.allow_all_the_time),
                            negativeButtonText = activity.getString(R.string.cancel),
                            onUserResult = onUserResult
                        )
                    }

                    onResult { bgGranted, _, _ ->
                        Timber.i("Background location granted: %s", bgGranted)
                    }
                }
            }
        }
    }
}
```
