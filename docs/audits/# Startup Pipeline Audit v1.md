# Startup Pipeline Audit v1

### Goal: Eliminate the Black Window Before Splash

---

# Problem

Current startup:

```text
User launches BookBuddy

↓

Windows creates main window

↓

Black window is visible

↓

Backend starts

↓

React mounts

↓

Splash renders

↓

Library
```

The splash is **too late**.

It is a React page, therefore it cannot exist until React itself exists.

This defeats the purpose of a splash screen.

---

# Objective

The user must **never** see an uninitialized application window.

Desired startup:

```text
Launch

↓

Splash Window

↓

Backend Startup

↓

Health Check

↓

Frontend Initialization

↓

Library Ready

↓

Close Splash

↓

Show Main Window
```

The splash is a native startup component, not part of the application UI. This is also the approach recommended in the current Tauri v2 splashscreen guide, where the main window is created hidden and a separate splash window is shown until initialization completes. ([Tauri][1])

---

# Architecture

Current

```text
BookBuddy.exe

↓

Main Window

↓

React

↓

Splash
```

Required

```text
BookBuddy.exe

↓

Splash Window

↓

Backend

↓

React

↓

Main Window
```

The splash owns startup.

React never owns startup.

---

# Startup State Machine

```text
Launching

↓

Starting Backend

↓

Backend Healthy

↓

Loading Configuration

↓

Initializing React

↓

Restoring Session

↓

Ready

↓

Transition
```

Every state may update the splash progress.

---

# Window Lifecycle

## Splash Window

Properties

* Visible immediately
* Borderless
* Non-resizable
* Fixed size
* Centered
* Always on top (startup only)
* No taskbar icon
* No minimize/maximize

Purpose

Display startup progress only.

Destroyed after initialization.

---

## Main Window

Properties

* Created hidden
* Never shown before initialization
* Shown only after Ready

Never expose an empty WebView.

---

# Initialization Order

## Stage 1

OS launches BookBuddy.

No React.

No backend.

Splash already visible.

---

## Stage 2

Spawn backend process.

Wait.

Progress

```text
Starting reading engine...
```

---

## Stage 3

Health check

Example

```text
GET /health
```

Retry until healthy.

Progress

```text
Connecting to backend...
```

---

## Stage 4

Load frontend.

React mounts.

Progress

```text
Preparing interface...
```

---

## Stage 5

Restore

* theme
* settings
* last session
* window state

Progress

```text
Restoring workspace...
```

---

## Stage 6

Library ready.

Close splash.

Fade in main window.

---

# Progress Rules

Progress reflects **completed stages**, not fake percentages.

Wrong

```text
67%
```

Correct

```text
Starting backend...

━━━━━━━━━━━━
```

↓

```text
Preparing reader...

━━━━━━━━━━━━━━━━━━━━━━
```

↓

```text
Loading library...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

↓

```text
Ready

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

# Rendering Rules

Splash must never depend on

* backend
* API
* React state
* TanStack Query
* Zustand

Splash should render immediately using static assets.

---

# Timing Requirements

Window creation

Immediate.

Splash visibility

<100 ms.

Backend startup

Background.

Main window

Hidden.

Library

Only shown when usable.

---

# Transition

Required

```text
Splash

↓

150 ms fade

↓

Main Window

↓

150 ms fade
```

Forbidden

```text
Splash

↓

Instant disappear

↓

Library pop
```

---

# Failure Handling

## Backend timeout

Keep splash.

Display

```text
Backend is taking longer than expected...
```

Retry automatically.

---

## Backend failure

Display

```text
Unable to start BookBuddy engine.

Retry

Exit
```

Never show a broken application.

---

## React failure

Keep splash.

Show

```text
Preparing interface...
```

Log error.

Never expose blank WebView.

---

# Logging

Measure startup.

Example

```text
Launch

Splash shown

Backend spawned

Backend healthy

React mounted

Library ready

Main window shown
```

Persist timings.

Useful for regressions.

---

# Tauri Implementation

Use the Tauri v2 splashscreen architecture rather than rendering the splash as a React route.

Configuration should follow this model:

* Main window created with `visible: false`.
* Separate splash window created visible.
* Perform startup tasks.
* Close splash.
* Show main window. ([Tauri][1])

---

# Startup Ownership

| Component      | Responsibility        |
| -------------- | --------------------- |
| Rust           | Process orchestration |
| Splash Window  | Startup feedback      |
| Python Backend | Engine initialization |
| React          | Application UI        |
| FastAPI        | Service readiness     |

React never controls startup.

Rust controls startup.

---

# Acceptance Criteria

Startup is complete when:

* No black window is ever visible.
* Splash is the first visible UI.
* Main window remains hidden until fully initialized.
* Splash updates by startup stage, not artificial percentages.
* Transition to the library uses a short fade rather than an abrupt swap.
* Backend failures are handled from the splash without exposing a broken application.
* Startup timings are logged for regression analysis.
* No PowerShell, terminal, or console window appears during launch.

---

## Recommendation

Based on the current Tauri v2 documentation, **do not treat the splash as another React page**. Tauri's intended pattern is exactly the problem you're trying to solve: a **separate native splash window** that appears immediately while the **main window is hidden**, then hands off to the fully initialized application. ([Tauri][1])

This changes the startup sequence from:

```text
Black Window → React Splash → Library
```

to:

```text
Native Splash → Backend → React Ready → Library
```

The second sequence is what users perceive as a polished desktop application.


