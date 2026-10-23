# AirControl browser extension

This optional Chrome/Edge extension connects to the local AirControl app. It is supplied as an unpacked extension, not published in a browser marketplace.

1. Start AirControl.
2. Open `chrome://extensions` or `edge://extensions`.
3. Enable Developer mode, select **Load unpacked** and choose this folder.
4. Open a normal HTTP/HTTPS page and click **«Включить управление»** in the extension.
5. Allow page access when prompted so control can continue after navigation.

**⋯** opens settings for scope (tab/window/browser), mode, movement span and control while another application is focused. Minimized windows do not receive gesture commands.

Automatic mode uses discrete gestures for YouTube Shorts and analog control on other pages. Discrete mode supports repeated steps from a long motion; analog mode follows the position of a held grip. The two movement spans are saved separately.

The desktop app must be running. Its local address is `127.0.0.1:8767`. The extension receives control events only, not camera images or audio. Page access is used to apply gestures to the selected visible page.

To return to the previous mode after hand mouse control, choose **«Автоматически»** or the mode you prefer. Esc stops mouse control.

---

Русский: запустите AirControl, загрузите эту папку через «Загрузить распакованное расширение» на странице расширений Chrome/Edge и нажмите **«Включить управление»**. Все настройки находятся за кнопкой **⋯**. Камера включается и выключается вместе с управлением; видео и звук в расширение не передаются.
