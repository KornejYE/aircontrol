# Attribution and third-party notices

## Application origin

AirControl was developed by **KornejYE** as a separate local gesture-control application. It was extracted and adapted from work based on **MARK LV — JARVIS**, copyright © 2026 **FatihMakes**.

- Original project: https://github.com/FatihMakes/Mark-LV
- Original reference: `c3e795af71bff38bb406c62a2e7a63869cdc8eb2`
- Retained application license: Creative Commons Attribution–NonCommercial 4.0 International.
- License text: [LICENSE](LICENSE); canonical terms: https://creativecommons.org/licenses/by-nc/4.0/legalcode

Modifications include the independent application UI and preferences, hand mouse, click/drag/scroll state handling, gesture routing, smoothing and short-loss recovery, browser extension, per-hand configuration and checks. The original author's credit is retained; no endorsement by the original author is implied.

## Hand model

The setup script downloads Google's MediaPipe Hand Landmarker float16 model. Model weights are not included in the repository. The expected file checksum and official source are in [Models/gestures/UPSTREAM.txt](Models/gestures/UPSTREAM.txt).

- Documentation: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker
- MediaPipe project and license: https://github.com/google-ai-edge/mediapipe

## Runtime dependencies

Dependencies are installed from their package registries and keep their own licenses. They are not relicensed by the application's CC license. In particular:

- MediaPipe: Google, Apache 2.0.
- PyQt6: Riverbank Computing, GPL v3 or a commercial license; Qt has its own licensing terms.
- OpenCV, NumPy, PyObjC and the remaining packages: see the license files supplied with their installed distributions.

The repository publishes application source. It does not redistribute a bundled Python runtime, third-party wheels, a notarized application or model weights.
