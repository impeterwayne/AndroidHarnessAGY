# Permission Catalog & Factory Reference (`PermissionLists`)

`PermissionLists` (`com.hjq.permissions.permission.PermissionLists`) is the central factory for all dangerous, special, and platform permissions supported by the framework.

## Internal Caching Mechanism

`PermissionLists` caches parameterless `IPermission` objects in an internal `LruCache<String, IPermission>` with a capacity of `151`:
- **Parameterless Permissions**: Cached lazily upon first access via `getCachePermission(permissionName)` and `putCachePermission(new Permission())`.
- **Parameterized Permissions**: Not cached because they carry instance-specific configuration (e.g., service classes, channel IDs). A new instance is created on each call:
  - `getBindAccessibilityServicePermission(Class<? extends AccessibilityService>)`
  - `getBindNotificationListenerServicePermission(Class<? extends NotificationListenerService>)`
  - `getBindDeviceAdminPermission(Class<? extends DeviceAdminReceiver>, String extraExplanation)`
  - `getNotificationServicePermission(String channelId)`
  - `getSystemAlertWindowPermission(boolean forceXiaomi)` (cached only when `forceXiaomi == false`)

---

## Permission Classification

### 1. Standard Dangerous Permissions (Android 6.0+)
| Category | Permission Factory Method | Underlying Platform Permission | Notes |
| :--- | :--- | :--- | :--- |
| **Camera** | `getCameraPermission()` | `Manifest.permission.CAMERA` | API 23+ |
| **Microphone** | `getRecordAudioPermission()` | `Manifest.permission.RECORD_AUDIO` | API 23+ |
| **Location (Fine)** | `getAccessFineLocationPermission()` | `Manifest.permission.ACCESS_FINE_LOCATION` | Group: `LOCATION` |
| **Location (Coarse)**| `getAccessCoarseLocationPermission()`| `Manifest.permission.ACCESS_COARSE_LOCATION` | Group: `LOCATION` |
| **Contacts** | `getReadContactsPermission()` | `Manifest.permission.READ_CONTACTS` | Group: `CONTACTS` |
| | `getWriteContactsPermission()` | `Manifest.permission.WRITE_CONTACTS` | Group: `CONTACTS` |
| | `getGetAccountsPermission()` | `Manifest.permission.GET_ACCOUNTS` | Group: `CONTACTS` |
| **Calendar** | `getReadCalendarPermission()` | `Manifest.permission.READ_CALENDAR` | Group: `CALENDAR` |
| | `getWriteCalendarPermission()` | `Manifest.permission.WRITE_CALENDAR` | Group: `CALENDAR` |
| **Sensors** | `getBodySensorsPermission()` | `Manifest.permission.BODY_SENSORS` | API 23+ |
| **SMS** | `getSendSmsPermission()` | `Manifest.permission.SEND_SMS` | Group: `SMS` |
| | `getReceiveSmsPermission()` | `Manifest.permission.RECEIVE_SMS` | Group: `SMS` |
| | `getReadSmsPermission()` | `Manifest.permission.READ_SMS` | Group: `SMS` |
| | `getReceiveWapPushPermission()` | `Manifest.permission.RECEIVE_WAP_PUSH` | Group: `SMS` |
| | `getReceiveMmsPermission()` | `Manifest.permission.RECEIVE_MMS` | Group: `SMS` |
| **Phone** | `getReadPhoneStatePermission()` | `Manifest.permission.READ_PHONE_STATE` | Caution on iQOO/vivo devices |
| | `getCallPhonePermission()` | `Manifest.permission.CALL_PHONE` | Fails on non-telephony devices |
| | `getReadCallLogPermission()` | `Manifest.permission.READ_CALL_LOG` | Group `CALL_LOG` on API 28+, `PHONE` on API < 28 |
| | `getWriteCallLogPermission()` | `Manifest.permission.WRITE_CALL_LOG` | Group `CALL_LOG` on API 28+, `PHONE` on API < 28 |
| | `getAddVoicemailPermission()` | `Manifest.permission.ADD_VOICEMAIL` | Group: `PHONE` |
| | `getUseSipPermission()` | `Manifest.permission.USE_SIP` | Group: `PHONE` |
| | `getProcessOutgoingCallsPermission()` | `Manifest.permission.PROCESS_OUTGOING_CALLS` | Deprecated in Android 10 |

---

### 2. Version-Introduced Dangerous Permissions
| Android Version | API | Factory Method | Notes / Fallbacks |
| :--- | :--- | :--- | :--- |
| **Android 8.0** | 26 | `getReadPhoneNumbersPermission()` | Automatically falls back to `READ_PHONE_STATE` on older OS |
| | 26 | `getAnswerPhoneCallsPermission()` | Fails immediately on non-telephony devices |
| **Android 9.0** | 28 | `getAcceptHandoverPermission()` | Phone handover |
| **Android 10.0**| 29 | `getAccessBackgroundLocationPermission()` | Requires "Allow all the time"; request separate from foreground location |
| | 29 | `getActivityRecognitionPermission()` | Automatically requests `BODY_SENSORS` on Android 9 and below |
| | 29 | `getAccessMediaLocationPermission()` | Requires photo/storage permission |
| **Android 12.0**| 31 | `getBluetoothScanPermission()` | Needs `neverForLocation` flag or `ACCESS_FINE_LOCATION` on API < 31 |
| | 31 | `getBluetoothConnectPermission()` | Auto-falls back to `BLUETOOTH` on API < 31 |
| | 31 | `getBluetoothAdvertisePermission()`| Auto-falls back to `BLUETOOTH_ADMIN` on API < 31 |
| **Android 13.0**| 33 | `getPostNotificationsPermission()` | Auto-downgrades to `NotificationServicePermission` on API < 33 |
| | 33 | `getNearbyWifiDevicesPermission()` | Needs `neverForLocation` attribute or `ACCESS_FINE_LOCATION` fallback |
| | 33 | `getBodySensorsBackgroundPermission()`| Background sensors |
| | 33 | `getReadMediaImagesPermission()` | Auto-downgrades to `READ_EXTERNAL_STORAGE` on API <= 32 |
| | 33 | `getReadMediaVideoPermission()` | Auto-downgrades to `READ_EXTERNAL_STORAGE` on API <= 32 |
| | 33 | `getReadMediaAudioPermission()` | Auto-downgrades to `READ_EXTERNAL_STORAGE` on API <= 32 |
| **Android 14.0**| 34 | `getReadMediaVisualUserSelectedPermission()` | Partial photo/video picker access |
| **Vendor** | Any | `getGetInstalledAppsPermission()` | OEM specific (MIUI/ColorOS app list reading) |

---

### 3. Special Permissions (Settings / AppOps Pages)
Special permissions cannot be requested via standard system dialogs. The framework redirects the user to the designated Settings page.

| Factory Method | Android Permission Constant | Settings Page Type / Intent |
| :--- | :--- | :--- |
| `getSystemAlertWindowPermission(forceXiaomi)` | `SYSTEM_ALERT_WINDOW` | Overlay permission; Xiaomi checks popup/lockscreen ops |
| `getManageExternalStoragePermission()` | `MANAGE_EXTERNAL_STORAGE` | All Files Access (`ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION`) |
| `getRequestInstallPackagesPermission()` | `REQUEST_INSTALL_PACKAGES` | Unknown app sources (`ACTION_MANAGE_UNKNOWN_APP_SOURCES`) |
| `getScheduleExactAlarmPermission()` | `SCHEDULE_EXACT_ALARM` | Exact alarms (`ACTION_REQUEST_SCHEDULE_EXACT_ALARM`) |
| `getUseFullScreenIntentPermission()` | `USE_FULL_SCREEN_INTENT` | Android 14 full-screen intent settings |
| `getManageMediaPermission()` | `MANAGE_MEDIA` | Media management settings (Android 12+) |
| `getPictureInPicturePermission()` | `PICTURE_IN_PICTURE` | Picture-in-picture settings |
| `getRequestIgnoreBatteryOptimizationsPermission()`| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | Battery optimization exemption prompt |
| `getPackageUsageStatsPermission()` | `PACKAGE_USAGE_STATS` | Usage access settings (`ACTION_USAGE_ACCESS_SETTINGS`) |
| `getAccessNotificationPolicyPermission()` | `ACCESS_NOTIFICATION_POLICY` | Do Not Disturb access (`ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS`)|
| `getWriteSettingsPermission()` | `WRITE_SETTINGS` | Modify system settings (`ACTION_MANAGE_WRITE_SETTINGS`) |
| `getBindVpnServicePermission()` | `BIND_VPN_SERVICE` | VPN preparation intent (`VpnService.prepare`) |
| `getNotificationServicePermission([channelId])`| N/A | App/channel notification settings page |
| `getBindAccessibilityServicePermission(clazz)`| `BIND_ACCESSIBILITY_SERVICE` | Accessibility settings |
| `getBindNotificationListenerServicePermission(clazz)`| `BIND_NOTIFICATION_LISTENER_SERVICE` | Notification listener settings |
| `getBindDeviceAdminPermission(clazz, extra)` | `BIND_DEVICE_ADMIN` | Device admin activation screen |

---

### 4. Health & Fitness Permissions (Android 14, 15, 16)
Included via `StandardFitnessAndWellnessDataPermission` and `StandardHealthRecordsPermission`:
- **Android 14 (Health Connect)**:
  `getReadHeartRatePermission()`, `getWriteHeartRatePermission()`, `getReadStepsPermission()`, `getWriteStepsPermission()`, `getReadSleepPermission()`, `getWriteSleepPermission()`, `getReadDistancePermission()`, `getReadActiveCaloriesBurnedPermission()`, `getReadBloodGlucosePermission()`, `getReadBloodPressurePermission()`, `getReadBodyTemperaturePermission()`, `getReadOxygenSaturationPermission()`, `getReadRespiratoryRatePermission()`, `getReadVo2MaxPermission()`, `getReadWeightPermission()`, etc.
- **Android 15**:
  `getReadHealthDataInBackgroundPermission()`, `getReadHealthDataHistoryPermission()`, `getReadExerciseRoutesPermission()`, `getWriteExerciseRoutePermission()`, `getReadPlannedExercisePermission()`, `getWritePlannedExercisePermission()`, `getReadSkinTemperaturePermission()`, `getWriteSkinTemperaturePermission()`.
- **Android 16**:
  `getReadActivityIntensityPermission()`, `getWriteActivityIntensityPermission()`, `getReadMindfulnessPermission()`, `getWriteMindfulnessPermission()`.
- **Android 16 Medical Data Records (EHR)**:
  `getReadMedicalDataAllergiesIntolerancesPermission()`, `getReadMedicalDataConditionsPermission()`, `getReadMedicalDataLaboratoryResultsPermission()`, `getReadMedicalDataMedicationsPermission()`, `getReadMedicalDataPersonalDetailsPermission()`, `getReadMedicalDataPractitionerDetailsPermission()`, `getReadMedicalDataPregnancyPermission()`, `getReadMedicalDataProceduresPermission()`, `getReadMedicalDataSocialHistoryPermission()`, `getReadMedicalDataVaccinesPermission()`, `getReadMedicalDataVisitsPermission()`, `getReadMedicalDataVitalSignsPermission()`, `getWriteMedicalDataPermission()`.
