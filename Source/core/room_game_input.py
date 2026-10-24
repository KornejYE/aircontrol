"""Opt-in ordinary macOS input for a hand stick; never reads a game process.

No virtual HID driver, game hooks, macros, repeated clicks or game state.
An unselected target/output only displays the stick. All native APIs are lazy.
"""
from __future__ import annotations

from collections import deque
import math
import sys
import time

from core.room_hand_joystick import game_settings, valid_stick


def running_games():
    if sys.platform == 'win32':
        from core.room_windows_input import WindowsAPI
        return WindowsAPI().windows()
    if sys.platform != 'darwin':
        return []
    from AppKit import NSWorkspace
    applications = NSWorkspace.sharedWorkspace().runningApplications()
    return sorted({(str(a.bundleIdentifier()), str(a.localizedName())) for a in applications
                   if a.bundleIdentifier() and a.activationPolicy() == 0}, key=lambda a: a[1].casefold())


class MacGameAPI:
    def __init__(self):
        if sys.platform != 'darwin':
            raise RuntimeError('Игровой ввод этой версии доступен на Mac.')
        import Quartz
        from AppKit import NSWorkspace
        from core.room_air_mouse_native import trusted_access
        if not trusted_access():
            raise RuntimeError('Разрешите AirControl управление в macOS → Конфиденциальность → Универсальный доступ.')
        self.q = Quartz
        self.workspace = NSWorkspace.sharedWorkspace()

    def foreground(self):
        app = self.workspace.frontmostApplication()
        return str(app.bundleIdentifier() or '') if app else ''

    def escape(self):
        q = self.q
        return bool(q.CGEventSourceKeyState(q.kCGEventSourceStateHIDSystemState, 53))

    def key(self, code, down):
        q = self.q
        event = q.CGEventCreateKeyboardEvent(None, code, down)
        if event is None:
            raise RuntimeError('Не удалось создать событие клавиатуры.')
        q.CGEventSetFlags(event, 0)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def position(self):
        point = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
        return point.x, point.y

    def stick_bounds(self):
        q = self.q
        point = self.position()
        _, displays, _ = q.CGGetActiveDisplayList(16, None, None)
        bounds = next((q.CGDisplayBounds(d) for d in displays
                       if q.CGRectContainsPoint(q.CGDisplayBounds(d), point)), q.CGDisplayBounds(q.CGMainDisplayID()))
        return (bounds.origin.x + bounds.size.width / 2,
                bounds.origin.y + bounds.size.height / 2,
                min(bounds.size.width, bounds.size.height))

    def move(self, position):
        q = self.q
        event = q.CGEventCreateMouseEvent(None, q.kCGEventMouseMoved, position, q.kCGMouseButtonLeft)
        if event is None:
            raise RuntimeError('Не удалось создать движение мыши.')
        q.CGEventPost(q.kCGHIDEventTap, event)


class GameInput:
    KEYS = {'left': 0, 'right': 2, 'up': 13, 'down': 1}  # physical A D W S

    def __init__(self, config=None, *, api_factory=None, clock=time.monotonic):
        self.config = game_settings(config)
        if api_factory is None:
            if sys.platform == 'win32':
                from core.room_windows_input import WindowsGameAPI
                api_factory = WindowsGameAPI
            else:api_factory = MacGameAPI
        self.factory = api_factory
        self.clock = clock
        self.api = None
        self.held = set()
        self.bounds = None
        self.last_mouse = None
        self.recent = deque(maxlen=16)
        self.last = None
        self.blocked = True  # reconfiguration cannot inherit an already-held grip
        self.escaped = False
        self.neutral_since = None
        self.status = ('Проверка на экране · ввод в игру выключен' if self.config['output']=='preview'
                       else 'Дождитесь установки нейтрали ручки' if self.config['source']=='object'
                       else 'Раскройте руку перед началом управления')

    def cancel(self, *, neutral=True):
        error = None
        for key in tuple(self.held):
            try:
                self.api.key(self.KEYS[key], False)
                self.held.remove(key)
            except Exception as exc:
                error = exc  # retain failed releases for the watchdog to retry
        try:
            if (neutral and self.bounds and self.api
                    and self.api.foreground() == self.config['target']):
                self.api.move(self.bounds[:2])
        except Exception as exc:
            error = exc
        finally:
            self.bounds = None
            self.last_mouse = None
            self.recent.clear()
            self.last = None
            self.neutral_since = None
        if error:
            raise error

    def poll(self):
        if self.api is None:
            return
        if self.api.escape():
            self.escaped = True
            self.cancel()
            self.status = ('Остановлено клавишей Esc · нажмите «Новая нейтраль» для возврата' if self.config['source']=='object'
                           else 'Остановлено клавишей Esc · выключите и включите управление для возврата')
        elif self.api.foreground() != self.config['target']:
            self.cancel(neutral=False)
            self.blocked = True
            self.status = ('Игра не на переднем плане · верните ручку в нейтраль перед продолжением' if self.config['source']=='object'
                           else 'Игра не на переднем плане · раскройте руку перед продолжением')
        elif self.last is not None and not 0 <= self.clock() - self.last <= .25:
            self.cancel()
            self.blocked = True
            self.status = 'Нет свежих кадров · ввод отпущен'
        elif self.held and self.last is None:
            self.cancel()  # retry any key-up that previously failed

    def send(self, packet, captured):
        if not valid_stick(packet):
            self.cancel()
            raise ValueError('Некорректное состояние джойстика')
        if (type(captured) not in (int, float) or not math.isfinite(captured)
                or not 0 <= self.clock() - captured <= .25):
            self.cancel()
            self.blocked = True
            return
        if self.config['output'] == 'preview':
            return  # no permission prompt, imports, cursor or key events
        if not self.config['target']:
            self.status = 'Выберите игру в настройках джойстика'
            return
        if self.api is None:
            self.api = self.factory()
        self.poll()
        if not packet['active']:
            self.cancel()
            self.blocked = False
            return
        if self.blocked and self.config['source']=='object' and not self.escaped and self.api.foreground()==self.config['target']:
            if math.hypot(packet['x'],packet['y'])<=.03:
                if self.neutral_since is None:self.neutral_since=self.clock()
                if self.clock()-self.neutral_since>=.4:self.blocked=False
            else:self.neutral_since=None
        if self.escaped or self.blocked or self.api.foreground() != self.config['target']:
            return
        self.last = captured
        self.status = 'WASD · ручное управление' if self.config['output'] == 'wasd' else 'Мышь-джойстик · ручное управление'
        if self.config['output'] == 'wasd':
            desired = set()
            for axis, negative, positive in (('x', 'left', 'right'), ('y', 'up', 'down')):
                value = packet[axis]
                if value < -(.18 if negative in self.held else .28):
                    desired.add(negative)
                elif value > (.18 if positive in self.held else .28):
                    desired.add(positive)
            # Release the opposite direction before pressing a new one.
            for key in sorted(self.held - desired):
                self.api.key(self.KEYS[key], False)
                self.held.remove(key)
            for key in sorted(desired - self.held):
                self.held.add(key)  # release even if posting fails part way
                try:
                    self.api.key(self.KEYS[key], True)
                except Exception:
                    self.cancel()
                    raise
        else:
            now = self.clock()
            point = self.api.position()
            own = any(now - at < .15 and math.dist(point, p) <= 4 for at, p in self.recent)
            if self.last_mouse and math.dist(point, self.last_mouse) > 4 and not own:
                self.cancel(neutral=False)
                self.blocked = True
                self.status = 'Физическая мышь получила управление · отпустите захват'
                return
            if self.bounds is None:
                self.bounds = self.api.stick_bounds()
            x, y, size = self.bounds
            position = (x + packet['x'] * size * self.config['mouse_range'],
                        y + packet['y'] * size * self.config['mouse_range'])
            self.api.move(position)
            self.last_mouse = position
            self.recent.append((now, position))
