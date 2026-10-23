# Changes

## 1.1.1 — 2026-10-23

- Added a closed-fist grip and 3D tilt steering for a hand resting on its little-finger edge, with a separate angle sensitivity setting.
- Preserved pinch/translation options and existing mouse/scroll behavior. The fist remains a stop gesture outside joystick mode.
- Forwarded MediaPipe world landmarks without changing image points used by the existing gesture pipeline; tilt remains independent of whole-hand translation.
- Added fist, tabletop-pivot, depth, inversion and geometry-source regression checks; exposed joystick state through local diagnostics.

## 1.1.0 — 2026-10-23

- Experimental hand joystick with an on-screen axis meter, per-mode hand/span/deadzone settings and vertical inversion.
- Opt-in foreground-targeted WASD and smooth mouse-joystick outputs for macOS; preview-only by default. War Thunder compatibility is not yet confirmed.
- Input releases on tracking loss, stale frames, focus loss, settings/mode changes and shutdown. Esc stops live output until the controller is restarted.
- Existing pointer and browser modes retain their own settings; browser mode leases cannot take over the game joystick.
- Added geometry, native-input and Qt lifecycle regression checks with fake input APIs.

## 1.0.0 — 2026-10-23

- Initial standalone public source release: local hand mouse, discrete/analog gestures, searchable settings and a Chrome/Edge extension.
- Preserved original MARK LV attribution and non-commercial licensing.
