"""Camera-area geometry, isolated Qt selection and mocked multi-monitor output."""
import base64,importlib.util,io,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/('Source' if (ROOT/'Source').exists() else 'desktop/Source')
sys.path.insert(0,str(SOURCE))
from core.room_pointer_area import pointer_area,valid_area,map_point,display_target
from core.room_gesture_rules import settings,save_settings,read_settings,poses,HandRules
from core.room_air_mouse import AirMouse
from core.room_pointer_area_picker import AreaCanvas,AreaPicker,pick_pointer_area
from core.room_air_mouse_native import NativeAirMouse
from PyQt6.QtCore import Qt,QPoint,QRectF,QBuffer,QIODevice
from PyQt6.QtGui import QPixmap,QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget


def load_fixture(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'checks'/('test-'+name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
mouse_fixture=load_fixture('air-mouse')
# Jarvis's source fixture layout is shared, but native output tests may not be present there.

def frame_data():
 image=QPixmap(640,360);image.fill(QColor('#253c43'))
 buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
 return base64.b64encode(bytes(buffer.data())).decode()


class Area(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_invalid_rectangles_fall_back_without_affecting_legacy_default(self):
  for value in [None,{},[0,0,0,0],[.8,0,.2,1],[-.1,0,1,1],[0,0,1,float('nan')],[False,0,1,1],[0,0,.09,1]]:
   self.assertFalse(valid_area(value));self.assertEqual(pointer_area(value),[.15,.15,.85,.85])
  self.assertTrue(valid_area([.2,.3,.6,.8]))
 def test_selected_edges_and_center_map_exactly_and_clamp(self):
  area=[.2,.3,.6,.8]
  self.assertEqual(map_point((.2,.3),area),[0.,0.])
  self.assertEqual(map_point((.6,.8),area),[1.,1.])
  self.assertAlmostEqual(map_point((.4,.55),area)[0],.5)
  self.assertAlmostEqual(map_point((.4,.55),area)[1],.5)
  self.assertEqual(map_point((0,1),area),[0.,1.])
 def test_settings_roundtrip_keeps_area_and_display_with_old_files_migrating(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'settings.json';save_settings(path,dict(mouse_area=[.2,.1,.7,.6],mouse_display='display:3'))
   result=read_settings(path);self.assertEqual(result['mouse_area'],[.2,.1,.7,.6]);self.assertEqual(result['mouse_display'],'display:3')
  self.assertEqual(settings()['mouse_display'],'all');self.assertEqual(display_target('injected'),'all')
 def test_absolute_hand_pose_uses_selected_field_and_relative_output_is_unchanged(self):
  p=mouse_fixture.point();norm,flags=poses(p)
  mouse=AirMouse();packets=mouse.update(p,0,norm=norm,flags=flags,positioning='absolute',area=[.25,.1,.75,.6])
  self.assertAlmostEqual(packets[-1]['x'],.36);self.assertAlmostEqual(packets[-1]['y'],.2)
  a,b=AirMouse(),AirMouse()
  for frame in range(20):
   p=mouse_fixture.point(frame*.001,frame*.001);norm,flags=poses(p)
   self.assertEqual(a.update(p,frame/30,norm=norm,flags=flags),b.update(p,frame/30,norm=norm,flags=flags,area=[0,0,.4,.4]))
 def test_router_passes_area_and_releases_old_stroke_when_bounds_change(self):
  router=HandRules();router.configure(dict(mode='system_mouse',mouse_position='absolute',mouse_area=[.25,.1,.75,.6]));router.take_pending()
  packets=router.update(mouse_fixture.point(),0,'Right')
  self.assertAlmostEqual(packets[-1][2]['x'],.36)
  router.configure(dict(mode='system_mouse',mouse_position='absolute',mouse_area=[0,0,1,1]))
  self.assertTrue(any(p[2]['phase']=='cancel' for p in router.take_pending()))
 def test_canvas_selection_preserves_mirrored_coordinates_and_letterboxing(self):
  canvas=AreaCanvas();canvas.resize(800,600);canvas.show_image(frame_data());canvas.show()
  # 16:9 image sits at y=75..525; widget borders are not part of the camera.
  self.assertEqual(canvas.image_rect(),QRectF(0,75,800,450))
  QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(40,120))
  QTest.mouseMove(canvas,QPoint(720,480))
  QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(720,480))
  for actual,expected in zip(canvas.area,[.05,.1,.9,.9]):self.assertAlmostEqual(actual,expected)
  before=list(canvas.area)
  QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,20))
  QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(700,580))
  self.assertEqual(canvas.area,before)
  canvas.close()
 def test_canvas_can_resize_move_clamp_and_reset_without_saving(self):
  canvas=AreaCanvas([.2,.2,.6,.6]);canvas.resize(800,450);canvas.show_image(frame_data());canvas.show()
  QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(160,90))
  QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(80,45))
  self.assertEqual(canvas.area,[.1,.1,.6,.6])
  QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(240,135))
  QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(1000,1000))
  for actual,expected in zip(canvas.area,[.5,.5,1,1]):self.assertAlmostEqual(actual,expected)
  canvas.set_area([0,0,1,1]);self.assertEqual(canvas.area,[0,0,1,1]);canvas.close()
 def test_picker_pauses_input_and_cancel_preserves_config_and_camera_state(self):
  from core import room_gesture_panel as panel
  for running in (False,True):
   calls=[];window=QWidget()
   c=S(_pointer_setup=False,camera_snapshot=lambda:dict(running=running),release_pointer=lambda:calls.append('release'),_clear_drag=lambda:None,relay=None,start=lambda:calls.append('start'),stop=lambda:calls.append('stop'),reload_rules=lambda:calls.append('reload'))
   parent=S(controller=c)
   class Cancel:
    def __init__(self,*args):self.canvas=S(area=[.2,.2,.8,.8])
    def exec(self):
     self_test.assertTrue(c._pointer_setup)
     return 0
   self_test=self
   with tempfile.TemporaryDirectory() as d,patch.object(panel,'DATA_DIR',Path(d)),patch('core.room_pointer_area_picker.AreaPicker',Cancel):
    path=Path(d)/'config/gesture-actions.json';save_settings(path,dict(mouse_area=[.1,.2,.9,.8]))
    before=path.read_bytes();pick_pointer_area(parent);self.assertEqual(path.read_bytes(),before)
   self.assertFalse(c._pointer_setup);self.assertIn('reload',calls)
   self.assertEqual('start' in calls,not running);self.assertEqual('stop' in calls,not running)
   window.close()


class Displays(unittest.TestCase):
 def fixture(self):
  events=[];position=[100.,100.]
  rectangles={1:S(origin=S(x=0,y=0),size=S(width=2560,height=1440)),3:S(origin=S(x=-1920,y=0),size=S(width=1920,height=1080))}
  q=S(CGEventCreate=lambda _:None,CGEventGetLocation=lambda _:S(x=position[0],y=position[1]),CGEventSourceKeyState=lambda *_:False,CGGetActiveDisplayList=lambda *_:(0,list(rectangles),len(rectangles)),CGDisplayBounds=rectangles.get,CGRectContainsPoint=lambda r,p:r.origin.x<=p[0]<r.origin.x+r.size.width and r.origin.y<=p[1]<r.origin.y+r.size.height,CGMainDisplayID=lambda:1,CGEventCreateMouseEvent=lambda _,kind,point,button:dict(kind=kind,point=point),CGEventSetIntegerValueField=lambda *_:None)
  for key in ('kCGEventLeftMouseUp','kCGMouseButtonLeft','kCGHIDEventTap','kCGEventSourceStateHIDSystemState','kCGEventLeftMouseDragged','kCGEventMouseMoved','kCGEventLeftMouseDown','kCGMouseEventClickState'):setattr(q,key,key)
  def post(_,event):events.append(event);position[:]=event['point']
  q.CGEventPost=post;mouse=NativeAirMouse();mouse.q=q
  return mouse,position,rectangles,events
 def test_both_screens_use_one_stable_desktop_with_negative_origin(self):
  mouse,position,rectangles,events=self.fixture()
  p=dict(action='pointer',phase='move',absolute=True,x=0,y=0)
  mouse.send(p);self.assertEqual(position,[-1920,0])
  mouse.send(p|dict(x=.5,y=.5));self.assertEqual(position,[319.5,719.5])
  mouse.send(p|dict(x=1,y=1));self.assertEqual(position,[2559,1439]);self.assertEqual(mouse.physical_pauses,0)
 def test_shorter_left_display_is_projected_to_real_pixels(self):
  mouse,position,rectangles,events=self.fixture()
  mouse.send(dict(action='pointer',phase='move',absolute=True,x=0,y=1))
  self.assertEqual(position,[-1920,1079]);self.assertEqual(mouse.physical_pauses,0)
 def test_selected_left_display_ignores_starting_cursor_monitor(self):
  mouse,position,rectangles,events=self.fixture();mouse.set_display_target('display:3')
  mouse.send(dict(action='pointer',phase='move',absolute=True,x=1,y=1))
  self.assertEqual(position,[-1,1079])
 def test_removed_display_falls_back_to_available_desktop(self):
  mouse,position,rectangles,events=self.fixture();mouse.set_display_target('display:3');del rectangles[3]
  mouse.send(dict(action='pointer',phase='move',absolute=True,x=1,y=1));self.assertEqual(position,[2559,1439])

if __name__=='__main__':unittest.main()
