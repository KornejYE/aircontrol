# Changes

## 1.1.0 — 2026-10-23

- Experimental hand joystick with an on-screen axis meter, per-mode hand/span/deadzone settings and vertical inversion.
- Opt-in foreground-targeted WASD and smooth mouse-joystick outputs for macOS; preview-only by default. War Thunder compatibility is not yet confirmed.
- Input releases on tracking loss, stale frames, focus loss, settings/mode changes and shutdown. Esc stops live output until the controller is restarted.
- Existing pointer and browser modes retain their own settings; browser mode leases cannot take over the game joystick.
- Added geometry, native-input and Qt lifecycle regression checks with fake input APIs.

## 1.0.0 — 2026-10-23

- Initial standalone public source release: local hand mouse, discrete/analog gestures, searchable settings and a Chrome/Edge extension.
- Preserved original MARK LV attribution and non-commercial licensing.
