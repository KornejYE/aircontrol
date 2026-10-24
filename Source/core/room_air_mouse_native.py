"""Opt-in macOS mouse output. Imports Quartz only when explicitly selected."""
import time
from collections import deque

def reachable_point(point,rectangles):
 # A bounding box around several monitors includes gaps and offset corners
 # where Quartz cannot place the pointer. Keep our predicted position inside
 # a real display, otherwise the OS correction looks like physical mouse input.
 candidates=[(max(r.origin.x,min(r.origin.x+r.size.width-1,point[0])),
              max(r.origin.y,min(r.origin.y+r.size.height-1,point[1]))) for r in rectangles]
 return min(candidates,key=lambda candidate:sum((a-b)**2 for a,b in zip(point,candidate)))

def trusted_access():
 import ctypes
 library=ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
 library.AXIsProcessTrusted.restype=ctypes.c_bool;library.AXIsProcessTrusted.argtypes=[]
 return bool(library.AXIsProcessTrusted())
class NativeAirMouse:
 def __init__(self):self.q=None;self.previous=None;self.location=None;self.scale=None;self.recent=deque(maxlen=32);self.down=False;self.paused_until=0.;self.last_click=0.;self.click_count=0;self.scroll_remainder=0.;self.physical_pauses=0
 def set_display_target(self,target):
  from core.room_pointer_area import display_target
  target=display_target(target)
  if target!=getattr(self,'display_target','all'):self.cancel()
  self.display_target=target
 def cancel(self):
  try:
   if self.q and self.down and self.location is not None:
    event=self.q.CGEventCreateMouseEvent(None,self.q.kCGEventLeftMouseUp,self.q.CGEventGetLocation(self.q.CGEventCreate(None)),self.q.kCGMouseButtonLeft);self.q.CGEventPost(self.q.kCGHIDEventTap,event)
  except Exception:pass
  finally:self.down=False;self.previous=None;self.location=None;self.scale=None;self.scroll_remainder=0.
 def check_escape(self):
  if self.q and self.q.CGEventSourceKeyState(self.q.kCGEventSourceStateHIDSystemState,53):self.cancel();self.paused_until=float('inf')
  return self.paused_until==float('inf')
 def send(self,data):
  from core.room_air_mouse import valid_pointer
  if not valid_pointer(data):raise ValueError('Некорректное действие мыши')
  if data['phase']!='scroll':self.scroll_remainder=0.
  if data['phase']=='cancel':self.cancel();return
  if self.q is None:
   import sys
   if sys.platform!='darwin':raise RuntimeError('Системная мышь пока доступна только на Mac. Выберите мышь в браузере.')
   import Quartz
   if not trusted_access():raise RuntimeError('Разрешите AirControl управление компьютером в настройках macOS → Конфиденциальность → Универсальный доступ.')
   self.q=Quartz
  q=self.q;now=time.monotonic();point=q.CGEventGetLocation(q.CGEventCreate(None));point=(point.x,point.y)
  if self.check_escape():raise RuntimeError('Мышь остановлена клавишей Esc. Выключите и снова включите управление для продолжения.')
  # CGEventPost is asynchronous: the OS can still report an earlier position
  # we posted. That is not physical mouse input and must not pause hand control.
  own_position=any(now-at<.15 and sum((a-b)**2 for a,b in zip(point,location))<=16 for at,location in self.recent)
  if (self.location is not None and sum((a-b)**2 for a,b in zip(point,self.location))>16 and not own_position):
   self.physical_pauses+=1
   self.cancel();self.paused_until=now+1.2;self.location=point
  if now<self.paused_until:return
  xy=(data['relative_x'],data['relative_y']) if not data.get('absolute') and 'relative_x' in data else (data['x'],data['y']);phase=data['phase']
  if self.previous is None:self.location=point
  if self.previous is not None or data.get('absolute'):
   _,displays,_=q.CGGetActiveDisplayList(16,None,None)
   bounds=next((q.CGDisplayBounds(d) for d in displays if q.CGRectContainsPoint(q.CGDisplayBounds(d),self.location)),q.CGDisplayBounds(q.CGMainDisplayID()))
   if data.get('absolute'):
    from core.room_pointer_area import absolute_desktop_point
    target=getattr(self,'display_target','all')
    selected=([bounds] if target=='current' else
              [q.CGDisplayBounds(d) for d in displays if target==f'display:{d}'] if target.startswith('display:') else
              [q.CGDisplayBounds(d) for d in displays]) or [q.CGDisplayBounds(d) for d in displays] or [bounds]
    self.location=absolute_desktop_point(xy,selected);dx=dy=0.
   else:
    # Keep one scale throughout a stroke; crossing to a different-sized monitor
    # must not suddenly change the cursor's speed.
    if self.scale is None:self.scale=(bounds.size.width,bounds.size.height)
    dx=(xy[0]-self.previous[0])*self.scale[0];dy=(xy[1]-self.previous[1])*self.scale[1]
   rectangles=[q.CGDisplayBounds(d) for d in displays] or [bounds]
   self.location=reachable_point((self.location[0]+dx,self.location[1]+dy),rectangles)
  self.previous=xy
  def post(kind,button=q.kCGMouseButtonLeft,count=1):
   event=q.CGEventCreateMouseEvent(None,kind,self.location,button);q.CGEventSetIntegerValueField(event,q.kCGMouseEventClickState,count);q.CGEventPost(q.kCGHIDEventTap,event)
   self.recent.append((now,self.location))
  if phase=='move':post(q.kCGEventLeftMouseDragged if self.down else q.kCGEventMouseMoved)
  elif phase=='down':self.down=True;post(q.kCGEventLeftMouseDown)
  elif phase=='up':post(q.kCGEventLeftMouseUp);self.down=False
  elif phase=='click':
   self.click_count=self.click_count+1 if now-self.last_click<.45 else 1;self.last_click=now
   post(q.kCGEventLeftMouseDown,count=self.click_count);post(q.kCGEventLeftMouseUp,count=self.click_count)
  elif phase=='context':post(q.kCGEventRightMouseDown,q.kCGMouseButtonRight);post(q.kCGEventRightMouseUp,q.kCGMouseButtonRight)
  elif phase=='scroll':
   # Quartz accepts integer pixels. Retain subpixel travel instead of losing
   # every small movement at high camera frame rates.
   total=self.scroll_remainder-data.get('dy',0)*600
   amount=int(total);self.scroll_remainder=total-amount
   if amount:q.CGEventPost(q.kCGHIDEventTap,q.CGEventCreateScrollWheelEvent(None,q.kCGScrollEventUnitPixel,1,amount))
