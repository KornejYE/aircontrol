"""Send the system Play/Pause media key, using only native OS libraries.

No player is launched or queried. A successful return confirms dispatch, not
whether the OS found a player or whether that player is now playing or paused.
Native APIs are loaded on demand so importing this module has no side effects.

References:
https://developer.apple.com/documentation/appkit/nsevent
https://developer.apple.com/documentation/coregraphics/cgevent/post(tap:)
https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDSystem/IOKit/hidsystem/ev_keymap.h
https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDSystem/IOKit/hidsystem/IOLLEvent.h
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-input
https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
"""

from __future__ import annotations

import ctypes
import sys
import time
from types import SimpleNamespace


class MediaKeyError(RuntimeError):
    """The system media key could not be dispatched."""


# Fixed-width Win32 types are intentional: ctypes.c_long is 64-bit on macOS,
# whereas a Windows LONG/DWORD remains 32-bit, including on 64-bit Windows.
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is required even for keyboard-only input: it sets INPUT's size.
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", ctypes.c_uint32), ("data", _INPUTUNION)]


def _load_windows_api():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(_INPUT), ctypes.c_int,
    ]
    user32.SendInput.restype = ctypes.c_uint32
    return user32


def _send_windows(key=0xB3):
    api = _load_windows_api()
    events = (_INPUT * 2)()
    for event, flags in zip(events, (0, 0x0002)):  # KEYEVENTF_KEYUP
        event.type = 1  # INPUT_KEYBOARD
        event.ki = _KEYBDINPUT(key, 0, flags, 0, 0)  # VK_MEDIA_PLAY_PAUSE
    ctypes.set_last_error(0)
    sent = api.SendInput(2, events, ctypes.sizeof(_INPUT))
    if sent != 2:
        error = ctypes.get_last_error()
        if sent == 1:
            # SendInput can insert only key-down. Release it without sending a
            # second toggle, and still report the original partial failure.
            api.SendInput(1, ctypes.pointer(events[1]), ctypes.sizeof(_INPUT))
        detail = f" (код Windows {error})" if error else ""
        raise MediaKeyError(
            "Windows не приняла медиаклавишу Play/Pause" + detail +
            ". Проверьте права приложения и активный сеанс пользователя."
        )


class _NSPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


def _load_macos_api():
    # Explicit objc_msgSend signatures preserve pointers and the NSPoint ABI on
    # both Intel and Apple Silicon. No PyObjC or external executable is needed.
    appkit = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    quartz = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    pointer = ctypes.c_void_p
    message = ctypes.CFUNCTYPE(pointer, pointer, pointer)(("objc_msgSend", objc))
    drain = ctypes.CFUNCTYPE(None, pointer, pointer)(("objc_msgSend", objc))
    make_event = ctypes.CFUNCTYPE(
        pointer, pointer, pointer, ctypes.c_ulong, _NSPoint, ctypes.c_ulong,
        ctypes.c_double, ctypes.c_long, pointer, ctypes.c_short,
        ctypes.c_long, ctypes.c_long,
    )(("objc_msgSend", objc))
    quartz.CGEventPost.argtypes = [ctypes.c_uint32, pointer]
    quartz.CGEventPost.restype = None
    # This checks existing permission without opening a prompt or changing it.
    quartz.CGPreflightPostEventAccess.argtypes = []
    quartz.CGPreflightPostEventAccess.restype = ctypes.c_bool
    return SimpleNamespace(
        get_class=objc.objc_getClass, selector=objc.sel_registerName,
        message=message, drain=drain, make_event=make_event,
        preflight=quartz.CGPreflightPostEventAccess, post=quartz.CGEventPost,
        libraries=(appkit, quartz, objc),
    )


def _send_macos(key=16):
    api = _load_macos_api()
    if not api.preflight():
        raise MediaKeyError(
            "macOS не разрешает отправку медиаклавиш. Разрешите управление "
            "для приложения в «Системные настройки → Конфиденциальность и "
            "безопасность → Универсальный доступ»."
        )
    event_class = api.get_class(b"NSEvent")
    pool_class = api.get_class(b"NSAutoreleasePool")
    if not event_class or not pool_class:
        raise MediaKeyError("macOS: системный API медиаклавиш недоступен.")
    pool = api.message(pool_class, api.selector(b"new"))
    if not pool:
        raise MediaKeyError("macOS: не удалось создать пул системных событий.")
    try:
        selector = api.selector(
            b"otherEventWithType:location:modifierFlags:timestamp:"
            b"windowNumber:context:subtype:data1:data2:"
        )
        # NX_SYSDEFINED=14, NX_SUBTYPE_AUX_CONTROL_BUTTONS=8,
        # NX_KEYTYPE_PLAY=16, NX_KEYDOWN=10, NX_KEYUP=11. Construct both
        # events before posting so a construction failure cannot leave it down.
        events = []
        for state in (10, 11):
            event = api.make_event(
                event_class, selector, 14, _NSPoint(0, 0), state << 8,
                time.monotonic(), 0, None, 8, (key << 16) | (state << 8), -1,
            )
            cg_event = api.message(event, api.selector(b"CGEvent")) if event else None
            if not cg_event:
                raise MediaKeyError("macOS: не удалось создать медиаклавишу Play/Pause.")
            events.append(cg_event)
        for event in events:
            api.post(0, event)  # kCGHIDEventTap
    finally:
        api.drain(pool, api.selector(b"drain"))


def toggle_play_pause() -> str:
    """Dispatch one complete system Play/Pause press, or raise MediaKeyError.

    The OS selects its current media session; no foreground focus is required.
    This function does not inspect playback state or promise a player response.
    Tests can replace _load_macos_api/_load_windows_api with native API fakes.
    """
    try:
        if sys.platform == "darwin":
            _send_macos()
        elif sys.platform == "win32":
            _send_windows()
        else:
            raise MediaKeyError("Медиаклавиша Play/Pause поддерживается на macOS и Windows.")
    except MediaKeyError:
        raise
    except Exception as exc:
        raise MediaKeyError(f"Не удалось отправить медиаклавишу Play/Pause: {exc}") from exc
    return "Системная медиаклавиша Play/Pause отправлена."


def dispatch_action(action):
    if action in ('zoom_in', 'zoom_out'):
        import pyautogui
        pyautogui.hotkey('command' if sys.platform == 'darwin' else 'ctrl', '=' if action == 'zoom_in' else '-')
        return
    keys = {'play_pause': (16, 0xB3), 'volume_up': (0, 0xAF),
            'volume_down': (1, 0xAE), 'mute': (7, 0xAD),
            'next_track': (17, 0xB0), 'previous_track': (18, 0xB1)}
    if action not in keys: raise MediaKeyError('Неизвестная медиакоманда.')
    if sys.platform == 'darwin': _send_macos(keys[action][0])
    elif sys.platform == 'win32': _send_windows(keys[action][1])
    else: raise MediaKeyError('Медиакоманды поддерживаются на macOS и Windows.')
