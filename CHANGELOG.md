# Changes

## 1.3.3 — 2026-10-24

- Redrew the hand icon with four raised fingers and a single thumb; removed the extra side protrusion. The same vector generates the application and macOS bundle icons.

## 1.3.2 — 2026-10-24

- Added a screen-count and monitor selection dialog: choose one or several attached displays, or automatically use all connected monitors. The list follows detected hardware instead of assuming two displays. Refresh handles connection changes without saving until confirmed.
- Saved subsets keep their exact monitors when new ones are attached. Absolute pointer mapping excludes unselected monitors, including gaps containing another display.
- Added isolated Qt checks for 0/1/2/3/8/32 monitors, count and checkbox synchronization, connection changes, settings roundtrips and fake native output.

## 1.3.1 — 2026-10-24

- Added a live, mirrored camera-area picker for absolute pointing. Draw, resize or move the rectangle; normalized bounds survive window resizing and are saved locally. Relative pointing retains its existing behavior.
- Absolute system pointing spans all active monitors by default, including negative origins and different heights. A display selector also offers one specific monitor or the current monitor; unreachable gap pixels are projected onto a real display.
- Gesture output pauses while choosing the area. Cancel preserves the saved bounds; the camera returns to its previous on/off state. Added geometry, settings, Qt-selection and mocked multi-display regression checks.

## 1.3.0 — 2026-10-24

- The macOS interface runs in its own named AirControl bundle instead of appearing as Python, retaining the existing virtual environment and native launcher.

- Added two-hand grip zoom: spreading the selected right and left hands zooms in; bringing them together zooms out. Common camera-depth changes are normalized by palm size.
- The two-hand clutch suppresses single-hand pointer/scroll actions and requires both grips to release after loss or a hand-identity change. Joystick mode keeps its existing behavior.
- Added an opt-out, movement sensitivity and two text-only gesture-guide entries. System-mouse zoom targets the foreground app; browser-mode zoom retains the selected-tab route.
- macOS zoom shortcuts use native keyboard events with release cleanup, removing the missing PyAutoGUI dependency on that path. Tests use synthetic landmarks, real worker replay and fake native event sinks.

## 1.2.1 — 2026-10-24

- Added an adaptive positional tether after coordinate smoothing to suppress stationary hand-landmark jitter without rounding away every small movement.
- Added independent low-speed precision aiming, enabled by default: sensitivity falls to 30% for fine adjustments and returns to normal during ordinary movement. Fast acceleration retains its existing separate setting and remains off by default.
- Dragging, scrolling, absolute aiming and joystick behavior are unchanged. Added noisy stationary/slow-stroke and settings regression checks using synthetic landmarks and fake input only.

## 1.2.0 — 2026-10-23

- Added explicit selection and local CSRT tracking of an ordinary pen tip/cap without markers; no hand inference is performed while this source is selected.
- Added a live region-selection dialog, a five-second neutral countdown, object sensitivity, pause/rearm controls and neutral-dwell resume after focus changes.
- Added loss, appearance-change, bounds and discontinuity checks. Object templates stay in memory and are not automatically reacquired after loss.
- Synthetic object tests exercise the actual CSRT tracker and verify fail-closed input and focus recovery without sending real OS input.
- Kept the camera worker alive during the asynchronous macOS camera-permission prompt instead of immediately terminating its request.
- Kept the native macOS launcher registered with AppKit while the Python interface runs, allowing system authorization dialogs to be presented.

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
