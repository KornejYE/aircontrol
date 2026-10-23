"""Mock native APIs: never move or click the user's actual pointer."""
import sys,time,unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_air_mouse_native import NativeAirMouse
class Native(unittest.TestCase):
 def fixture(self):
  events=[];position=[100.,100.]
  q=S(AXIsProcessTrusted=lambda:True,CGEventCreate=lambda _:None,CGEventGetLocation=lambda _:S(x=position[0],y=position[1]),CGEventSourceKeyState=lambda *_:False,CGGetActiveDisplayList=lambda *_:(0,[1],1),CGDisplayBounds=lambda _:S(origin=S(x=0,y=0),size=S(width=1000,height=800)),CGRectContainsPoint=lambda *_:True,CGMainDisplayID=lambda:1,CGEventCreateMouseEvent=lambda _,kind,point,button:dict(kind=kind,point=point,button=button),CGEventSetIntegerValueField=lambda *_:None,CGEventCreateScrollWheelEvent=lambda *a:dict(kind='scroll',point=position[:],amount=a[-1]))
  for key in ('kCGEventLeftMouseUp','kCGMouseButtonLeft','kCGHIDEventTap','kCGEventSourceStateHIDSystemState','kCGEventLeftMouseDragged','kCGEventMouseMoved','kCGEventLeftMouseDown','kCGMouseEventClickState','kCGEventRightMouseDown','kCGMouseButtonRight','kCGEventRightMouseUp','kCGScrollEventUnitPixel'):setattr(q,key,key)
  def post(_,event):
   events.append(event)
   point=event['point']
   position[:]=[point.x,point.y] if hasattr(point,'x') else point
  q.CGEventPost=post;m=NativeAirMouse();m.q=q
  return m,events,position
 def test_click_drag_and_cancel_are_balanced(self):
  m,out,pos=self.fixture();p=dict(action='pointer',x=.5,y=.5)
  m.send(p|dict(phase='click'));self.assertEqual(len(out),2)
  m.send(p|dict(phase='down'));self.assertTrue(m.down)
  m.send(p|dict(phase='move',x=.55));self.assertEqual(out[-1]['kind'],'kCGEventLeftMouseDragged')
  m.send(p|dict(phase='cancel'));self.assertFalse(m.down);self.assertEqual(out[-1]['kind'],'kCGEventLeftMouseUp')
 def test_absolute_pointer_uses_selected_display_coordinates(self):
  m,out,pos=self.fixture();m.send(dict(action='pointer',phase='move',x=.2,y=.3,absolute=True))
  self.assertAlmostEqual(pos[0],199.8);self.assertAlmostEqual(pos[1],239.7)
 def test_relative_motion_ignores_virtual_edge_and_supports_reversal(self):
  m,out,pos=self.fixture();p=dict(action='pointer',phase='move',x=1.,y=.5,relative_x=.6,relative_y=0.)
  m.send(p);m.send(p|dict(relative_x=.7));self.assertAlmostEqual(pos[0],200.)
  m.send(p|dict(relative_x=.8));self.assertAlmostEqual(pos[0],300.)
  m.send(p|dict(relative_x=.75));self.assertAlmostEqual(pos[0],250.)
 def test_os_reporting_previous_post_is_not_physical_mouse_movement(self):
  m,out,pos=self.fixture();p=dict(action='pointer',phase='move',x=.5,y=.5)
  m.send(p);m.send(p|dict(x=.55));pos[:]=[100.,100.]
  m.send(p|dict(x=.6));self.assertEqual(m.paused_until,0.);self.assertAlmostEqual(pos[0],200.)
  self.assertEqual(m.physical_pauses,0)
 def test_gaps_between_monitors_cannot_trigger_false_physical_priority(self):
  m,out,pos=self.fixture();pos[:]=[900.,100.]
  bounds={1:S(origin=S(x=0,y=0),size=S(width=1000,height=800)),
          2:S(origin=S(x=1200,y=200),size=S(width=800,height=600))}
  m.q.CGGetActiveDisplayList=lambda *_:(0,[1,2],2)
  m.q.CGDisplayBounds=lambda display:bounds[display]
  m.q.CGRectContainsPoint=lambda r,p:r.origin.x<=p[0]<r.origin.x+r.size.width and r.origin.y<=p[1]<r.origin.y+r.size.height
  p=dict(action='pointer',phase='move',x=.5,y=.5,relative_x=.5,relative_y=.5)
  m.send(p);m.send(p|dict(relative_x=.7))
  self.assertEqual(pos,[999.,100.],'gap is projected onto the nearest actual screen')
  m.send(p|dict(relative_x=.9));self.assertEqual(pos,[1200.,200.])
  m.send(p|dict(relative_x=1.));self.assertAlmostEqual(pos[0],1300.,msg='crossing screens retains the original stroke scale')
  self.assertEqual(m.physical_pauses,0);self.assertEqual(m.paused_until,0.)
  for event in out:
   self.assertTrue(any(m.q.CGRectContainsPoint(r,event['point']) for r in bounds.values()))
 def test_offset_negative_monitor_corner_stays_on_reachable_pixels(self):
  m,out,pos=self.fixture()
  bounds={1:S(origin=S(x=0,y=0),size=S(width=1000,height=800)),
          2:S(origin=S(x=-800,y=-600),size=S(width=800,height=600))}
  m.q.CGGetActiveDisplayList=lambda *_:(0,[1,2],2)
  m.q.CGDisplayBounds=lambda display:bounds[display]
  m.q.CGRectContainsPoint=lambda r,p:r.origin.x<=p[0]<r.origin.x+r.size.width and r.origin.y<=p[1]<r.origin.y+r.size.height
  p=dict(action='pointer',phase='move',x=.5,y=.5,relative_x=.5,relative_y=.5)
  m.send(p);m.send(p|dict(relative_x=.3));self.assertEqual(pos,[0.,100.])
  m.send(p|dict(relative_x=.3,relative_y=.3));self.assertAlmostEqual(pos[0],-1.);self.assertAlmostEqual(pos[1],-60.)
  self.assertEqual(m.physical_pauses,0);self.assertEqual(m.paused_until,0.)
 def test_real_mouse_and_escape_take_priority(self):
  m,out,pos=self.fixture();p=dict(action='pointer',phase='move',x=.5,y=.5);m.send(p)
  pos[0]+=50;n=len(out);m.send(p|dict(x=.6));self.assertEqual(len(out),n)
  self.assertEqual(m.physical_pauses,1)
  m.paused_until=0;m.q.CGEventSourceKeyState=lambda *_:True
  with self.assertRaises(RuntimeError):m.send(p)
  self.assertEqual(len(out),n)
  m.cancel();self.assertEqual(m.physical_pauses,1,'diagnostics survive cancellation and Esc')
 def test_subpixel_scroll_accumulates_without_mouse_button_events(self):
  m,out,pos=self.fixture();p=dict(action='pointer',phase='scroll',x=.5,y=.5,dy=.0004)
  for _ in range(10):m.send(p)
  self.assertEqual(sum(e['amount'] for e in out),-2)
  self.assertAlmostEqual(m.scroll_remainder,-.4)
  self.assertTrue(all(e['kind']=='scroll' and e['amount']<0 for e in out))
  self.assertEqual(pos,[100.,100.]);self.assertFalse(m.down)
 def test_fractional_scroll_reversal_preserves_direction_and_total(self):
  m,out,pos=self.fixture();p=dict(action='pointer',phase='scroll',x=.5,y=.5,dy=.0004)
  for _ in range(10):m.send(p)
  count=len(out)
  for _ in range(10):m.send(p|dict(dy=-.0004))
  self.assertTrue(all(e['amount']>0 for e in out[count:]))
  self.assertEqual(sum(e['amount'] for e in out),0)
  self.assertAlmostEqual(m.scroll_remainder,0.)
 def test_scroll_fraction_is_discarded_on_cancel_or_non_scroll_action(self):
  for phase in ('cancel','move','click','down','up','context'):
   m,out,pos=self.fixture();p=dict(action='pointer',x=.5,y=.5)
   m.send(p|dict(phase='scroll',dy=.0004));self.assertAlmostEqual(m.scroll_remainder,-.24)
   m.send(p|dict(phase=phase));self.assertEqual(m.scroll_remainder,0.)
   start=len(out)
   for _ in range(4):m.send(p|dict(phase='scroll',dy=.0004))
   self.assertFalse(any(e['kind']=='scroll' for e in out[start:]))
   m.send(p|dict(phase='scroll',dy=.0004))
   self.assertEqual(sum(e['amount'] for e in out[start:] if e['kind']=='scroll'),-1)
 def test_untrusted_process_cannot_emit_input(self):
  m=NativeAirMouse()
  with patch('sys.platform','darwin'),patch('core.room_air_mouse_native.trusted_access',return_value=False),patch.dict(sys.modules,Quartz=S()):
   with self.assertRaises(RuntimeError):m.send(dict(action='pointer',phase='click',x=.5,y=.5))
if __name__=='__main__':unittest.main()
