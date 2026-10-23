"""Synthetic pen images and fake game input; no camera, recordings or real input."""
import math,sys,unittest
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_object_joystick import ObjectJoystick,valid_box
from core.room_hand_joystick import valid_stick
from core.room_gesture_rules import HandRules
from core.room_game_input import GameInput


def frame(x=300,y=120,occluded=False):
    image=np.full((360,640,3),180,dtype=np.uint8)
    if not occluded:
        cv2.rectangle(image,(x,y),(x+29,y+59),(30,45,160),-1)
        cv2.rectangle(image,(x+8,y+3),(x+20,y+56),(170,65,20),-1)
        cv2.circle(image,(x+15,y+14),5,(240,245,250),-1)
        cv2.line(image,(x+5,y+35),(x+25,y+42),(15,20,30),3)
    return image


class Tracker:
    def __init__(self):self.box=(300,120,30,60);self.ok=True
    def init(self,image,box):self.box=box
    def update(self,image):return self.ok,self.box


class ObjectTracking(unittest.TestCase):
    def setUp(self):
        self.t=Tracker();self.s=ObjectJoystick(lambda:self.t)
        self.box=(300/640,120/360,30/640,60/360)
    def engage(self):
        self.s.select(self.box,10.,.5)
        for i in range(7):out=self.s.update(frame(),10.+i*.1,{})
        self.assertTrue(out['active'])
    def test_box_validation_rejects_outside_full_frame_and_nonfinite_values(self):
        for box in ((0,0,1,1),(.9,0,.2,.2),(.1,.1,.01,.2),(True,0,.2,.2),(0,0,math.nan,.2)):
            self.assertFalse(valid_box(box))
        self.assertTrue(valid_box(self.box))
    def test_capture_gap_before_selection_keeps_the_selection_instruction(self):
        self.s.update(frame(),10.,{})
        self.s.update(frame(),12.,{})
        self.assertEqual(self.s.state,'idle')
        self.assertIn('Выделите',self.s.feedback)
    def test_selection_countdown_then_pixel_displacement_produces_axes_without_a_hand(self):
        self.engage();self.t.box=(320,130,30,60)
        out=self.s.update(frame(320,130),10.7,{})
        self.assertGreater(out['x'],.1);self.assertGreater(out['y'],.05)
        self.assertTrue(valid_stick(out))
        router=HandRules();router.configure({'mode':'joystick','joystick':{'source':'object'}})
        self.assertIsNone(router.update(None,10.,'Right'))
    def test_pause_neutral_and_stale_capture_release_output(self):
        self.engage();self.s.pause()
        self.assertFalse(self.s.update(frame(),10.7,{})['active'])
        self.s.recenter(10.7,.5)
        for i in range(1,7):out=self.s.update(frame(),10.7+i*.1,{})
        self.assertTrue(out['active']);self.assertEqual(out['x'],0)
        self.assertFalse(self.s.update(frame(),12.,{})['active'])
        self.assertIsNone(self.s.selection)
    def test_lost_object_is_not_reacquired_as_a_different_background_patch(self):
        self.engage();self.t.ok=False
        self.assertFalse(self.s.update(frame(),10.7,{})['active'])
        self.t.ok=True
        self.assertFalse(self.s.update(frame(),10.8,{})['active'])
        self.assertEqual(self.s.state,'lost')
    def test_full_occlusion_and_a_large_jump_fail_closed(self):
        self.engage()
        self.assertFalse(self.s.update(frame(occluded=True),10.7,{})['active'])
        self.s.clear();self.engage();self.t.box=(500,120,30,60)
        self.assertFalse(self.s.update(frame(500),10.7,{})['active'])
    def test_featureless_selection_is_reported_before_any_output(self):
        self.s.select((.1,.1,.1,.2),10.,.5)
        out=self.s.update(frame(),10.,{})
        self.assertFalse(out['active']);self.assertIn('деталей',self.s.feedback)
    def test_actual_csrt_tracks_a_small_moving_pen_patch(self):
        s=ObjectJoystick();s.select(self.box,10.,.5)
        for i in range(10):
            x=300+max(0,i-6)*5
            out=s.update(frame(x),10.+i*.1,{})
        self.assertTrue(out['active'],s.feedback)
        self.assertGreater(out['x'],.05)
        self.assertLess(abs(s.bbox[0]-315),10)
    def test_object_resume_requires_neutral_dwell_and_escape_stays_latched(self):
        now=[10.];events=[]
        class API:
            def foreground(self):return 'game'
            def escape(self):return False
            def key(self,code,down):events.append((code,down))
        s=GameInput({'source':'object','output':'wasd','target':'game'},api_factory=API,clock=lambda:now[0])
        def send(x):s.send(dict(action='joystick',phase='update',active=True,x=x,y=0.),now[0])
        send(1.);self.assertFalse(events)
        send(0.);now[0]+=.2;send(0.);self.assertFalse(events)
        now[0]+=.21;send(0.);send(1.);self.assertEqual(events,[(2,True)])
        s.cancel();s.blocked=True;s.escaped=True
        send(0.);now[0]+=.5;send(0.);send(1.)
        self.assertFalse(s.held)


if __name__=='__main__':unittest.main()
