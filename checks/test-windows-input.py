"""Windows mouse/key adapter tests with fake APIs only; safe on Mac or Windows."""
import ctypes,sys,unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_windows_input import WindowsAirMouse,WindowsAPI,WindowsGameAPI,bounds,contains
from core.room_media_keys import _INPUT,_send_windows_zoom


class FakeAPI:
 def __init__(self):
  self.point=(100.,100.);self.events=[];self.escaped=False
  self.monitors=[(1,bounds(-1000,0,1000,800)),(2,bounds(0,0,1200,1000)),(3,bounds(1200,0,800,800))]
 def position(self):return self.point
 def displays(self):return self.monitors
 def escape(self):return self.escaped
 def mouse(self,point,flags):self.point=tuple(point);self.events.append(('mouse',tuple(point),flags))
 def wheel(self,amount):self.events.append(('wheel',amount))


class WindowsInput(unittest.TestCase):
 def fixture(self):
  api=FakeAPI();clock=[1.];m=WindowsAirMouse(api,lambda:clock[0]);return m,api,clock
 def packet(self,**kw):return dict(action='pointer',phase='move',x=.5,y=.5)|kw
 def test_abi_matches_windows_x64_input_size(self):self.assertEqual(ctypes.sizeof(_INPUT),40)
 def test_relative_motion_reverses_and_keeps_stroke_scale_between_monitors(self):
  m,api,t=self.fixture();p=self.packet(relative_x=.5,relative_y=.5)
  m.send(p);m.send(p|dict(relative_x=.6));self.assertAlmostEqual(api.point[0],220)
  m.send(p|dict(relative_x=.55));self.assertAlmostEqual(api.point[0],160)
  self.assertEqual(m.physical_pauses,0)
 def test_absolute_mapping_and_subset_projection_never_enter_unchosen_monitor(self):
  m,api,t=self.fixture();m.set_display_target('displays:1,3')
  for x in (0,.2,.5,.8,1):
   m.send(self.packet(x=x,y=.5,absolute=True))
   self.assertTrue(any(contains(rect,api.point) for identifier,rect in api.monitors if identifier in (1,3)))
  self.assertEqual(api.point,(1999,399.5));self.assertEqual(m.physical_pauses,0)
 def test_click_drag_cancel_and_context_release_buttons(self):
  m,api,t=self.fixture();p=self.packet()
  m.send(p|dict(phase='click'));self.assertEqual([e[2] for e in api.events],[2,4])
  m.send(p|dict(phase='down'));self.assertTrue(m.down)
  m.send(p|dict(x=.6));m.send(p|dict(phase='cancel'));self.assertFalse(m.down)
  self.assertEqual(api.events[-1][2],4)
  m.send(p|dict(phase='context'));self.assertEqual([e[2] for e in api.events[-2:]],[8,16])
 def test_physical_mouse_pauses_and_escape_latches_stop(self):
  m,api,t=self.fixture();p=self.packet();m.send(p)
  api.point=(500,200);count=len(api.events);m.send(p|dict(x=.6))
  self.assertEqual(len(api.events),count);self.assertEqual(m.physical_pauses,1)
  t[0]+=2;api.escaped=True
  with self.assertRaises(RuntimeError):m.send(p)
  api.escaped=False
  with self.assertRaises(RuntimeError):m.send(p)
 def test_reported_previous_os_position_does_not_look_like_a_physical_mouse(self):
  m,api,t=self.fixture();p=self.packet();m.send(p);previous=api.point
  m.send(p|dict(x=.55));api.point=previous;m.send(p|dict(x=.6))
  self.assertEqual(m.physical_pauses,0)
 def test_scroll_retains_fractions_and_reverses_without_clicks(self):
  m,api,t=self.fixture();p=self.packet(phase='scroll',dy=.0004)
  for _ in range(10):m.send(p)
  self.assertEqual(sum(e[1] for e in api.events),-4)
  for _ in range(10):m.send(p|dict(dy=-.0004))
  self.assertEqual(sum(e[1] for e in api.events),0);self.assertFalse(m.down)
  self.assertTrue(all(e[0]=='wheel' for e in api.events))
 def test_failed_mouse_down_attempts_release(self):
  m,api,t=self.fixture();original=api.mouse
  def mouse(point,flags):
   original(point,flags)
   if flags==2:raise RuntimeError('partial failure')
  api.mouse=mouse
  with self.assertRaises(RuntimeError):m.send(self.packet(phase='down'))
  self.assertFalse(m.down);self.assertEqual(api.events[-1][2],4)
 def test_win32_absolute_event_uses_virtual_desktop_and_signed_wheel(self):
  api=WindowsAPI.__new__(WindowsAPI);events=[]
  def send(count,pointer,size):
   event=pointer.contents;events.append((event.type,event.mi.dx,event.mi.dy,event.mi.mouseData,event.mi.dwFlags,size));return 1
  api.u=S(GetSystemMetrics=lambda i:{76:-1000,77:-200,78:3000,79:1200}[i],SendInput=send)
  # ctypes last-error helpers exist only on Windows; fake this diagnostic call on Mac.
  with patch('ctypes.set_last_error',create=True):
   api.mouse((-1000,-200),2);api.mouse((1999,999),4);api.wheel(-120)
  self.assertEqual(events[0][1:3],(0,0));self.assertEqual(events[1][1:3],(65535,65535))
  self.assertEqual(events[0][4],0xC003);self.assertEqual(events[1][4],0xC005)
  self.assertEqual(events[2][3],0xffffff88);self.assertEqual(events[2][4],0x0800)
 def test_zoom_releases_own_control_but_does_not_release_a_physical_control(self):
  for held in (False,True):
   events=[];fake=S(u=S(GetAsyncKeyState=lambda key:0x8000 if held else 0),key=lambda key,down:events.append((key,down)))
   with patch('core.room_windows_input.WindowsAPI',return_value=fake):_send_windows_zoom('zoom_in')
   self.assertEqual(events,[(0xBB,True),(0xBB,False)] if held else [(0x11,True),(0xBB,True),(0xBB,False),(0x11,False)])
 def test_zoom_failure_releases_modifier(self):
  events=[]
  def key(code,down):
   events.append((code,down))
   if code==0xBB and down:raise RuntimeError('blocked')
  with patch('core.room_windows_input.WindowsAPI',return_value=S(u=S(GetAsyncKeyState=lambda key:0),key=key)):
   with self.assertRaises(RuntimeError):_send_windows_zoom('zoom_in')
  self.assertEqual(events[-2:],[(0xBB,False),(0x11,False)])
 def test_game_api_maps_existing_hand_axis_keys_to_windows_wasd(self):
  api=WindowsGameAPI.__new__(WindowsGameAPI);events=[]
  with patch.object(WindowsAPI,'key',side_effect=lambda code,down:events.append((code,down))):
   for code in (0,2,13,1):api.key(code,True)
  self.assertEqual(events,[(0x41,True),(0x44,True),(0x57,True),(0x53,True)])

if __name__=='__main__':unittest.main()
