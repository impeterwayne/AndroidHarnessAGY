---
name: scrcpy
description: Use when you need to inspect, interact with, or automate actions on a connected Android device using command-line tools.
---

# Android Device Control via CLI

## Overview
This skill teaches the agent how to control and interact with any connected Android device using the command-line interface `scrcpy-cli`.

> [!IMPORTANT]
> **Daemon lifecycle is handled for you.** The `scrcpy-daemon` hook
> (`.agents/hooks/scrcpy_daemon.py`) starts the background daemon and stops it when the
> session ends. Do **not** run `daemon start` or `daemon stop` yourself — just issue
> actions directly.

---

## When to Use

### Use cases:
*   When executing automation tasks on an Android phone, emulator, or display.
*   When you need to tap, swipe, scroll, write text, or send key events (like HOME, BACK, POWER).
*   When you need to capture screenshots or fetch layout XML (`ui-dump`).

### When NOT to use:
*   Do not use when standard web browser interaction is required (use browser tools instead).
*   Do not use when running local Android emulator build commands (use Gradle tasks instead).
*   Do not use for Compose screenshot tests (Paparazzi/Roborazzi run on the JVM, no device needed).

---

## Core Pattern

### 1. Confirm a device is attached
```powershell
scrcpy-cli device-list
scrcpy-cli device-info   # model, SDK, and screen size -- needed to reason about coordinates
```

If no device is connected, `scrcpy-cli` reports `No Android devices connected` **and still exits 0**. Check the output text, not the exit code.

### 2. Locate elements before touching them
Never guess coordinates. Dump the hierarchy, read the target's `bounds`, and tap its centre:

```powershell
scrcpy-cli ui-dump current-layout.xml
```

### 3. Run actions directly
No daemon setup required:

```powershell
scrcpy-cli tap 540 960
scrcpy-cli write "Hello World"
scrcpy-cli key BACK
scrcpy-cli swipe 540 1600 540 600 300
scrcpy-cli screenshot verification.png
```

### 4. Verify
Re-dump or screenshot after the interaction and assert against what changed. A tap that
silently did nothing looks identical to a successful one unless you check.

---

## Quick Reference

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `scrcpy-cli tap` | `<x> <y>` | Taps screen coordinates |
| `scrcpy-cli swipe` | `<x1> <y1> <x2> <y2> [ms]` | Performs swipe/drag gesture |
| `scrcpy-cli write` | `<text>` | Inputs text into focused field |
| `scrcpy-cli key` | `<keycode>` | Sends keycode (HOME, BACK, POWER, etc.) |
| `scrcpy-cli scroll` | `<x> <y> <dx> <dy>` | Scrolls at specified coordinate |
| `scrcpy-cli screenshot` | `[filepath]` | Captures device screen to local file |
| `scrcpy-cli ui-dump` | `[filepath]` | Dumps layout hierarchy XML to file |
| `scrcpy-cli clipboard-get` | None | Retrieves clipboard contents |
| `scrcpy-cli clipboard-set` | `<text>` | Sets clipboard text |
| `scrcpy-cli app-start` | `<package>` | Starts app. Prefix with '+' to force-restart |
| `scrcpy-cli app-stop` | `<package>` | Force-stops app |
| `scrcpy-cli app-list` | None | Lists all installed package names |
| `scrcpy-cli device-info` | None | Gets device model, SDK version, size |
| `scrcpy-cli device-list` | None | Lists connected devices |
| `scrcpy-cli mirror` | `[scrcpy-args]` | Opens desktop mirror window (aliases: `view`, `gui`) |

---

## Common Mistakes

### ❌ Hardcoding coordinates across different devices
Different devices and emulators have different physical screen sizes.
*   **Fix:** Run `scrcpy-cli device-info` to check screen dimensions, and run `scrcpy-cli ui-dump` to locate elements dynamically using their bounding boxes in the XML layout instead of hardcoding coordinate pairs.

### ❌ Trusting the exit code
`scrcpy-cli` exits 0 even when it reports `No Android devices connected`.
*   **Fix:** Parse the output text when branching on device state.

### ❌ Firing a gesture and assuming it worked
A tap on the wrong coordinate produces no error.
*   **Fix:** Follow every state-changing interaction with a `ui-dump` or `screenshot` and assert the expected change.
