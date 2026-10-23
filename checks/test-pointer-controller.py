"""Offscreen controller/timer replay; no camera, Quartz or real input."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from PyQt6.QtWidgets import QApplication,QWidget
from core import room_gesture_panel as panel
from core.room_pointer_motion import PointerMotion


class ControllerMotion(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.clock=[10.];self.events=[];self.cancels=0
  self.patches=[patch.object(panel,'DATA_DIR',Path(self.directory.name)),
    patch.object(panel,'load_preferences',return_value={}),
    patch.object(panel.time,'monotonic',side_effect=lambda:self.clock[0]),
    patch.object(panel.subprocess,'Popen',side_effect=AssertionError('No camera start'))]
  for p in self.patches:p.start()
  self.window=QWidget();self.c=panel.GestureController(self.window)
  self.c._browser_timer.stop();self.c.control_mode='system_mouse';self.c.ready=True
  self.c.process=S(poll=lambda:None,stdin=io.StringIO())
  def cancel():self.cancels+=1
  native=S(send=lambda packet:self.events.append(dict(packet)),cancel=cancel,check_escape=lambda:False)
  self.c._pointer_native=native;self.c._pointer_motion=PointerMotion(native.send,lambda:self.clock[0])
 def tearDown(self):
  self.c.release_pointer();self.c.process=None;self.window.close()
  for p in reversed(self.patches):p.stop()
  self.directory.cleanup()
 def receive(self,ident,x,captured=None,phase='move'):
  self.c.receive(dict(type='pointer',action='pointer',mode='system_mouse',id=ident,
   phase=phase,x=x,y=.5,relative_x=x,relative_y=.5,
   captured_monotonic=self.clock[0] if captured is None else captured))
 def start_segment(self):
  self.receive(1,.2);self.clock[0]=10.04;self.receive(2,.6)
  self.assertTrue(self.c._pointer_timer.isActive());self.assertEqual(len(self.events),1)
 def test_native_timer_outputs_intermediate_positions_and_stops_at_endpoint(self):
  self.start_segment();self.clock[0]=10.06;self.c.tick_pointer()
  self.assertAlmostEqual(self.events[-1]['relative_x'],.4)
  self.clock[0]=10.081;self.c.tick_pointer()
  self.assertAlmostEqual(self.events[-1]['relative_x'],.6)
  self.assertFalse(self.c._pointer_timer.isActive())
 def test_release_and_cancel_drop_all_pending_output(self):
  for explicit in (False,True):
   self.events.clear();self.c._pointer_id=0;self.clock[0]=10.
   self.start_segment()
   if explicit:self.receive(3,.6,phase='cancel')
   else:self.c.release_pointer()
   before=list(self.events);self.clock[0]=10.07;self.c.tick_pointer()
   self.assertEqual(self.events,before);self.assertFalse(self.c._pointer_timer.isActive())
 def test_mode_or_readiness_change_cannot_emit_queued_movement(self):
  for change in ('mode','ready','calibration','process'):
   self.c.control_mode='system_mouse';self.c.ready=True;self.c._calibrating=False
   self.c.process=S(poll=lambda:None,stdin=io.StringIO());self.events.clear()
   self.c.release_pointer();self.c._pointer_id=0;self.clock[0]=10.;self.start_segment()
   if change=='mode':self.c.control_mode='discrete'
   elif change=='ready':self.c.ready=False
   elif change=='calibration':self.c._calibrating=True
   else:self.c.process=None
   self.clock[0]=10.06;self.c.tick_pointer()
   self.assertEqual(len(self.events),1);self.assertFalse(self.c._pointer_timer.isActive())
 def test_capture_freshness_cannot_be_extended_by_output_interpolation(self):
  self.receive(1,.2);self.clock[0]=10.04;self.receive(2,.6,captured=9.75)
  self.assertTrue(self.c._pointer_timer.isActive())
  self.clock[0]=10.06;self.c.tick_pointer()
  self.assertEqual(len(self.events),1);self.assertFalse(self.c._pointer_timer.isActive())
 def test_output_error_stops_timer_and_is_visible_to_user(self):
  self.start_segment()
  def fail(packet):raise RuntimeError('ESC / native output stopped')
  self.c._pointer_motion._send=fail;self.clock[0]=10.06;self.c.tick_pointer()
  self.assertFalse(self.c._pointer_timer.isActive());self.assertFalse(self.c._pointer_motion.pending)
  self.assertIn('native output stopped',self.c._pointer_error)


if __name__=='__main__':unittest.main()
