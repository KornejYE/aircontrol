# Local processing and stored data

AirControl uses the selected webcam only while gesture control is enabled. Frames are processed locally for hand landmarks, drawn in the preview and held briefly in memory. The app does not save camera recordings, send frames to a cloud model, use a microphone or include telemetry.

The optional browser extension receives gesture events over HTTP on the loopback address `127.0.0.1:8767`. It does not receive camera images or audio. The local endpoint checks Host, extension ID, Origin and event freshness; it is not bound to the network-facing address. The extension requests page access to execute commands on pages selected by the user.

Runtime preferences and calibration are stored under:

```text
~/Library/Application Support/AirControl/
```

This includes camera selection, gesture bindings, sensitivity, calibration and diagnostic logs. Preferences and logs are local files accessible to the current operating-system account. The application has no API key or cloud conversation store.

The optional game joystick lists local foreground-capable applications so you can choose a target. It stores that application's bundle identifier and checks which application is in front before sending ordinary keyboard or mouse events. It does not read game memory, inspect a game's process contents or capture gameplay. The default output is a local on-screen preview.

Camera ownership uses a small local lock file in the user cache. It contains an application label and process ID, not camera data.

During setup, packages are downloaded from the configured Python package registry and the hand model is downloaded from Google's official model host. Normal camera processing does not need those services.

Local settings, profiles, logs, dependencies and model downloads are excluded by `.gitignore`. Do not attach raw recordings, personal configuration files or complete system logs to a public issue. For a tracking bug, start with a written description and the selected mode.
