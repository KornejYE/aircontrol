# AirControl

**Local hand gestures for macOS: move the cursor, scroll pages and control videos with a webcam.**

[Русское описание](README.ru.md) · [Installation](#installation) · [Gesture guide](#gestures) · [License](#license)

![AirControl interface](docs/images/aircontrol.png)

AirControl is a standalone desktop application with local hand tracking, configurable gestures and an optional Chrome/Edge extension. No account, API key, cloud model or microphone is needed. The current interface is in Russian.

## Features

- **Hand mouse:** relative movement like a touchpad, left/right clicks, selection and dragging. Absolute positioning is also available.
- **Scrolling:** grip with three fingertips and move your hand to scroll. Two extended fingers also scroll in mouse mode.
- **Discrete gestures:** short movements perform one action; longer movements perform several.
- **Analog control:** drag a page or video feed continuously, similar to a touchscreen.
- **Media gestures:** open-palm play/pause, volume, seeking and pinch zoom.
- **Per-hand configuration:** separate left/right bindings, movement span, cursor speed and optional acceleration.
- **Visible tracking:** 21 landmarks per detected hand and a palm center. Up to eight hands can be displayed; the largest right and left hands control gestures.
- **Searchable settings**, a text gesture reference and optional background operation from the menu bar.
- **Experimental hand joystick:** a local axis preview, held WASD keys or smooth mouse-joystick positioning on macOS.

## Status

This is an early **source release**. The desktop app and system mouse have been checked on an Apple Silicon Mac with Python 3.11. Windows and Android packages are not part of this release.

Cursor smoothing and short tracking-loss recovery improve continuity but do not eliminate every tracking error. Good lighting, a visible hand and a steady camera help. Pointer output interpolates only received positions; it does not predict an invisible hand.

## Installation

Requirements: macOS, Python **3.11**, a webcam and Xcode Command Line Tools (`swiftc`). Internet access is needed to install packages and download the hand model. The model checksum is checked before it is saved.

```sh
git clone https://github.com/KornejYE/aircontrol.git
cd aircontrol
python3.11 scripts/setup.py
Runtime/bin/python Source/main.py
```

Click **«Включить управление»** to start. Allow camera access when macOS asks. System-wide mouse control also needs Accessibility permission in **System Settings → Privacy & Security → Accessibility**.

To build a local app:

```sh
Runtime/bin/python scripts/build_macos.py
```

The default destination is `~/Applications/AirControl.app`. The builder refuses to overwrite an existing app; use `--output /another/path/AirControl.app` or move the previous build first.

The generated app uses the Python installation on the Mac where it was built. It is **not a portable, notarized download for other computers**. Build it locally on each Mac.

## Gestures

The following table describes **hand mouse mode**. Other modes have separate configurable bindings.

| Action | Gesture |
| --- | --- |
| Move cursor | Move/tilt your pointing hand; the index finger may be relaxed |
| Left click | Touch thumb and index fingertip, then release |
| Drag/select | Keep thumb and index touching and move the hand |
| Right click | Touch thumb and middle fingertip, keep the index extended and hold briefly |
| Scroll | Bring thumb, index and middle fingertips together, then move up/down; two extended fingers also work |
| Clutch/stop | Make a fist; any held mouse button is released |
| Stop mouse control | Press Esc, then toggle control to resume |

In discrete/analog modes, an open palm held still for about one second toggles play/pause. The left-hand L-shaped gesture controls volume by default. See **«Как пользоваться»** and **«Настройки»** in the app for the full reference.

Acceleration is off by default. The physical mouse temporarily takes priority over hand movement.

## Browser control

The optional [Chrome/Edge extension](BrowserGestures/README.md) controls a selected tab, window or browser. It can target visible video while another application has focus.

1. Keep AirControl running.
2. Open `chrome://extensions` or `edge://extensions` and enable Developer mode.
3. Choose **Load unpacked** and select this repository's `BrowserGestures` folder.
4. Open the extension and click **«Включить управление»**. Allow page access for the websites you want to control.

With automatic mode, YouTube Shorts use discrete gestures; other pages use analog control. Browser extension settings are behind **⋯**. The extension talks only to the local app at `127.0.0.1:8767`.

System-wide mouse control works without the extension. Page control is limited by browser APIs; cross-origin frames, browser chrome and some custom widgets may require system mouse mode.

## Game joystick (experimental)

Select **«Игровой джойстик» → «Настроить джойстик»**. The default output is an on-screen preview, with no game input. Pinch thumb and index for about 0.2 seconds, with the middle finger away from the thumb, to establish neutral. Move the palm away from neutral to steer; release the pinch or remove the hand to stop. Span, deadzone, controlling hand and Y inversion are separate from pointer settings.

For live output, select a running game and either **held WASD keys** (digital tank movement, including diagonals) or **mouse-joystick positioning** (smooth cursor displacement around the current monitor's center). For the latter, configure War Thunder's own Mouse Joystick mode, use fullscreen and leave joystick neutral at screen center. Firing is not mapped. Focus loss and a 250 ms input timeout release output; resuming requires a new grip. Esc latches output off until control is toggled. The physical mouse takes priority over mouse-joystick output.

This is ordinary keyboard/mouse input, **not an analog HID gamepad**. No virtual driver, process hooks or game-memory access are used. Live War Thunder and anti-cheat compatibility have **not** been confirmed. [Gaijin prohibits gameplay automation and unfair-advantage tools](https://legal.gaijin.net/codeofconduct); this project cannot guarantee account safety or claim publisher approval. Ask game support about this specific application and do not bypass anti-cheat restrictions.

## Privacy and local data

Camera frames are processed locally and are not recorded by AirControl. The browser extension receives control events, not camera images or audio. There is no telemetry or cloud assistant integration. See [PRIVACY.md](PRIVACY.md).

Preferences and calibration are stored separately from the source code:

```text
~/Library/Application Support/AirControl/
```

Local settings, profiles, logs, runtimes and downloaded model weights are excluded from Git. Existing personal settings are not included in this repository.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the layout and focused checks. Bug reports should include the selected mode, camera, lighting, expected action and observed behavior. Please do not post raw camera recordings or personal settings by default.

## License

The project retains the original **Creative Commons Attribution–NonCommercial 4.0** license. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for authorship, origin and modifications. This is a public source project for **non-commercial use**, not a permissively licensed commercial SDK.

Original MARK LV — JARVIS: [FatihMakes](https://github.com/FatihMakes/Mark-LV). The hand model and dependencies retain their own terms; their sources are listed in [NOTICE.md](NOTICE.md) and [Models/gestures/UPSTREAM.txt](Models/gestures/UPSTREAM.txt).
