"""Ordinary Win32 input and display geometry; no hooks, drivers or game access.

Native calls are lazy. Tests inject an API and never post real OS input.
https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput
https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-mouseinput
"""
import ctypes
import math
import sys
import time
import zlib
from collections import deque
from types import SimpleNamespace as S

from core.room_pointer_area import absolute_desktop_point, display_target, selected_display_ids


class Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int32), ('y', ctypes.c_int32)]


class Rect(ctypes.Structure):
    _fields_ = [('left', ctypes.c_int32), ('top', ctypes.c_int32), ('right', ctypes.c_int32), ('bottom', ctypes.c_int32)]


class MonitorInfo(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('monitor', Rect), ('work', Rect), ('flags', ctypes.c_uint32), ('device', ctypes.c_wchar * 32)]


def bounds(x, y, width, height):
    return S(origin=S(x=x, y=y), size=S(width=width, height=height))


def contains(rect, point):
    return rect.origin.x <= point[0] < rect.origin.x + rect.size.width and rect.origin.y <= point[1] < rect.origin.y + rect.size.height


def initialize_windows():
    if sys.platform != 'win32':
        return
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = ctypes.c_int32
    # Before QApplication; an already-declared manifest/context is left intact.
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # Per Monitor v2
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID('AirControl.Desktop')


class WindowsAPI:
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Win32 input requires Windows')
        from core.room_media_keys import _load_windows_api
        self.u = _load_windows_api()
        self.u.GetCursorPos.argtypes = [ctypes.POINTER(Point)]
        self.u.GetCursorPos.restype = ctypes.c_int32
        self.u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.u.GetAsyncKeyState.restype = ctypes.c_int16
        self.u.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.u.GetSystemMetrics.restype = ctypes.c_int
        self.u.GetForegroundWindow.argtypes = []
        self.u.GetForegroundWindow.restype = ctypes.c_void_p
        self.u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MonitorInfo)]
        self.u.GetMonitorInfoW.restype = ctypes.c_int32
        self._monitor_callback = ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(Rect), ctypes.c_ssize_t)
        self.u.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.POINTER(Rect), self._monitor_callback, ctypes.c_ssize_t]
        self.u.EnumDisplayMonitors.restype = ctypes.c_int32

    def position(self):
        point = Point()
        if not self.u.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point.x, point.y

    def escape(self):
        return bool(self.u.GetAsyncKeyState(0x1b) & 0x8000)

    def foreground(self):
        return 'window:' + str(self.u.GetForegroundWindow() or 0)

    def displays(self):
        result = []
        def collect(handle, dc, rect, data):
            info = MonitorInfo(); info.size = ctypes.sizeof(info)
            if self.u.GetMonitorInfoW(handle, ctypes.byref(info)):
                r = info.monitor
                if r.right > r.left and r.bottom > r.top:
                    # Device name stays stable across restarts unlike HMONITOR.
                    identifier = zlib.crc32(info.device.encode('utf-8')) or 1
                    result.append((identifier, bounds(r.left, r.top, r.right-r.left, r.bottom-r.top)))
            return 1
        callback = self._monitor_callback(collect)
        if not self.u.EnumDisplayMonitors(None, None, callback, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return sorted(result, key=lambda item: (item[1].origin.x, item[1].origin.y))

    def _post(self, event):
        from core.room_media_keys import _INPUT
        ctypes.set_last_error(0)
        if self.u.SendInput(1, ctypes.pointer(event), ctypes.sizeof(_INPUT)) != 1:
            raise RuntimeError('Windows не приняла ввод. Приложение с правами администратора может блокировать обычный ввод.')

    def mouse(self, position, flags):
        from core.room_media_keys import _INPUT, _MOUSEINPUT
        left, top, width, height = (self.u.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        if width < 2 or height < 2:
            raise RuntimeError('Windows не вернула рабочую область экрана.')
        x = round((position[0]-left)*65535/(width-1)); y = round((position[1]-top)*65535/(height-1))
        event = _INPUT(); event.type = 0
        event.mi = _MOUSEINPUT(max(0,min(65535,x)),max(0,min(65535,y)),0,flags|0xC001,0,0)
        self._post(event)

    def wheel(self, amount):
        from core.room_media_keys import _INPUT, _MOUSEINPUT
        event = _INPUT(); event.type = 0
        event.mi = _MOUSEINPUT(0,0,amount & 0xffffffff,0x0800,0,0)
        self._post(event)

    def key(self, code, down):
        from core.room_media_keys import _INPUT, _KEYBDINPUT
        event = _INPUT(); event.type = 1
        event.ki = _KEYBDINPUT(code,0,0 if down else 2,0,0)
        self._post(event)

    def windows(self):
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_int32,ctypes.c_void_p,ctypes.c_ssize_t)
        self.u.EnumWindows.argtypes = [callback_type,ctypes.c_ssize_t];self.u.EnumWindows.restype = ctypes.c_int32
        self.u.IsWindowVisible.argtypes = [ctypes.c_void_p];self.u.IsWindowVisible.restype = ctypes.c_int32
        self.u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p];self.u.GetWindowTextLengthW.restype = ctypes.c_int
        self.u.GetWindowTextW.argtypes = [ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int];self.u.GetWindowTextW.restype = ctypes.c_int
        result=[]
        def collect(handle,data):
            size=self.u.GetWindowTextLengthW(handle)
            if size and self.u.IsWindowVisible(handle):
                title=ctypes.create_unicode_buffer(size+1);self.u.GetWindowTextW(handle,title,size+1)
                result.append(('window:'+str(handle),title.value))
            return 1
        self.u.EnumWindows(callback_type(collect),0)
        return sorted(result,key=lambda item:item[1].casefold())


class WindowsAirMouse:
    def __init__(self, api=None, clock=time.monotonic):
        self.api=api;self.clock=clock;self.previous=None;self.location=None;self.scale=None
        self.recent=deque(maxlen=32);self.down=False;self.paused_until=0.;self.scroll_remainder=0.;self.physical_pauses=0
        self.display_target='all'

    def set_display_target(self,target):
        target=display_target(target)
        if target!=self.display_target:self.cancel()
        self.display_target=target

    def cancel(self):
        if self.down and self.api:
            self.api.mouse(self.api.position(),4)
            self.down=False
        self.previous=None;self.location=None;self.scale=None;self.scroll_remainder=0.

    def check_escape(self):
        if self.api and self.api.escape():
            self.cancel();self.paused_until=float('inf')
        return self.paused_until==float('inf')

    def send(self,data):
        from core.room_air_mouse import valid_pointer
        from core.room_air_mouse_native import reachable_point
        if not valid_pointer(data):raise ValueError('Некорректное действие мыши')
        phase=data['phase']
        if phase!='scroll':self.scroll_remainder=0.
        if phase=='cancel':self.cancel();return
        if self.api is None:self.api=WindowsAPI()
        now=self.clock();point=self.api.position()
        if self.check_escape():raise RuntimeError('Мышь остановлена клавишей Esc. Выключите и включите управление для продолжения.')
        own=any(0<=now-at<.15 and math.dist(point,position)<=4 for at,position in self.recent)
        if self.location is not None and math.dist(point,self.location)>4 and not own:
            self.physical_pauses+=1;self.cancel();self.paused_until=now+1.2;self.location=point
        if now<self.paused_until:return
        xy=(data['relative_x'],data['relative_y']) if not data.get('absolute') and 'relative_x' in data else (data['x'],data['y'])
        if self.previous is None:self.location=point
        if self.previous is not None or data.get('absolute'):
            displays=self.api.displays();rectangles=[r for _,r in displays]
            if not rectangles:raise RuntimeError('Не найдено подключённых экранов.')
            current=next((r for r in rectangles if contains(r,self.location)),rectangles[0])
            if data.get('absolute'):
                ids=selected_display_ids(self.display_target)
                selected=([current] if self.display_target=='current' else [r for identifier,r in displays if identifier in ids] if ids else rectangles) or rectangles
                self.location=absolute_desktop_point(xy,selected);rectangles=selected
            else:
                if self.scale is None:self.scale=(current.size.width,current.size.height)
                self.location=tuple(self.location[a]+(xy[a]-self.previous[a])*self.scale[a] for a in (0,1))
            self.location=reachable_point(self.location,rectangles)
        self.previous=xy
        def post(flags):
            self.api.mouse(self.location,flags);self.recent.append((now,self.location))
        if phase=='move':post(0)
        elif phase=='down':
            self.down=True
            try:post(2)
            except Exception:
                self.cancel();raise
        elif phase=='up':post(4);self.down=False
        elif phase in ('click','context'):
            down,up=(2,4) if phase=='click' else (8,16)
            if phase=='click':self.down=True
            try:post(down)
            finally:
                post(up)
                if phase=='click':self.down=False
        elif phase=='scroll':
            total=self.scroll_remainder-data.get('dy',0)*1200
            amount=int(total);self.scroll_remainder=total-amount
            if amount:self.api.wheel(amount)


class WindowsGameAPI(WindowsAPI):
    def key(self, code, down):
        super().key({0:0x41,2:0x44,13:0x57,1:0x53}[code],down)

    def stick_bounds(self):
        point=self.position();rectangles=[r for _,r in self.displays()]
        rect=next((r for r in rectangles if contains(r,point)),rectangles[0])
        return rect.origin.x+rect.size.width/2,rect.origin.y+rect.size.height/2,min(rect.size.width,rect.size.height)

    def move(self,position):
        self.mouse(position,0)
