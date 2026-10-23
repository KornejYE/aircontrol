# Working on AirControl

Use macOS and Python 3.11. Install dependencies with `python3.11 scripts/setup.py`.

## Layout

```text
Source/main.py           Main window and menu-bar behavior
Source/core/             Tracking, gesture routing, cursor output and settings
BrowserGestures/         Optional Chrome/Edge extension
Native/AirControl.swift  Native launcher for the local Mac app
scripts/                Setup and app builder
checks/                 Synthetic/offscreen checks
```

The `room_` module prefix is retained from the application's origin to make the extraction traceable. The app has no dependency on a running assistant or another private repository.

## Focused checks

These checks replay numerical landmarks or use mocked input APIs. They do not need a real camera and do not move the system cursor.

```sh
Runtime/bin/python checks/test-air-mouse.py
Runtime/bin/python checks/test-pointer-motion.py
Runtime/bin/python checks/test-air-mouse-native.py
Runtime/bin/python checks/test-pointer-controller.py
Runtime/bin/python checks/test-standalone.py
Runtime/bin/python checks/test-worker.py
Runtime/bin/python checks/test-analog-gestures.py
Runtime/bin/python checks/test-stepped-wrist-gestures.py
Runtime/bin/python checks/test-gesture-browser-profile.py
node checks/test-air-mouse-browser.cjs
```

Real camera performance still needs manual evaluation. Report lighting, camera angle, distance, selected hand/mode, expected action and what actually happened. Mention whether ordinary and analog modes behave differently.

Preserve immediate cancellation on fist, tracking loss during drag, manual disable and Esc. Cursor smoothing must not replay stale commands or predict motion after the hand disappears. Keep private settings and recordings out of commits.

Changes must preserve the application's non-commercial license and third-party attribution. See [NOTICE.md](NOTICE.md).
