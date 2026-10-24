"""Synthetic two-hand coordinates and fake action sinks; no camera/OS input."""
import math, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/('Source' if (ROOT/'Source').exists() else 'desktop/Source')))
from core.room_gesture_zoom import TwoHandZoom
from core.room_gesture_rules import HandRules,settings


def hand(offset=0., scale=.4, grip=True, three=False, fist=False, mirror=False):
    p=[(.5,.8),(.38,.7),(.30,.65),(.25,.6),(.2,.55),(.43,.6),(.43,.43),(.43,.3),(.43,.2),(.50,.6),(.50,.5),(.52,.6),(.52,.68),(.57,.62),(.58,.53),(.6,.62),(.6,.7),(.64,.65),(.65,.56),(.67,.65),(.67,.72)]
    if grip:p[4]=(.45,.2)
    if three:p[4]=(.44,.46);p[8]=(.43,.45);p[12]=(.45,.45)
    if fist:
        for i in (8,12,16,20):p[i]=(.5,.75)
        p[4]=(.45,.66)
    return [(.5+offset+(-1 if mirror else 1)*(x-.5)*scale,.5+(y-.5)*scale) for x,y in p]


def pair(distance=.4, *, grip=True, three=False, scale=.4, shift=0.):
    return [('Right',hand(-distance/2+shift,scale,grip,three)),
            ('Left',hand(distance/2+shift,scale,grip,three,mirror=True))]


class Geometry(unittest.TestCase):
    def armed(self):
        z=TwoHandZoom()
        for i in range(5):self.assertEqual(z.update(pair(),10+i/25,identities={'Right':1,'Left':2}),[])
        self.assertTrue(z.engaged)
        return z
    def test_two_and_three_finger_grips_but_not_a_fist_or_open_hand(self):
        for mirror in (False,True):
            self.assertTrue(TwoHandZoom.geometry(hand(mirror=mirror))['grip'])
            self.assertTrue(TwoHandZoom.geometry(hand(three=True,mirror=mirror))['grip'])
            self.assertFalse(TwoHandZoom.geometry(hand(grip=False,mirror=mirror))['grip'])
            self.assertFalse(TwoHandZoom.geometry(hand(fist=True,mirror=mirror))['grip'])
        familiar=hand(scale=1.,grip=False)
        familiar[4]=(.436,.636);familiar[8]=(.444,.644);familiar[12]=(.452,.644)
        self.assertTrue(TwoHandZoom.geometry(familiar)['grip'])
    def test_spread_and_close_zoom_in_both_directions(self):
        for fps in (15,25,60):
            z=TwoHandZoom();events=[]
            for i in range(fps+1):events+=z.update(pair(.4+max(0,i/fps-.2)*.4),10+i/fps)
            self.assertTrue(events);self.assertTrue(all(e=='zoom_in' for e in events))
            events=[]
            for i in range(1,fps+1):events+=z.update(pair(.72-i/fps*.32),11+i/fps)
            self.assertTrue(events);self.assertTrue(all(e=='zoom_out' for e in events))
    def test_stationary_grips_and_camera_jitter_do_not_zoom(self):
        z=self.armed()
        for i in range(1,101):self.assertEqual(z.update(pair(.4+.002*(-1)**i),10.16+i/25,identities={'Right':1,'Left':2}),[])
    def test_common_translation_and_camera_depth_change_do_not_zoom(self):
        z=TwoHandZoom()
        for i in range(50):
            scale=1+.08*math.sin(i/10)
            self.assertEqual(z.update(pair(.4*scale,scale=.4*scale,shift=.04*math.sin(i/8)),10+i/25),[])
    def test_holding_a_final_spacing_does_not_repeat_forever(self):
        z=TwoHandZoom()
        for i in range(40):z.update(pair(.4+min(.2,max(0,i-5)*.01)),10+i/25)
        for i in range(40,90):self.assertEqual(z.update(pair(.6),10+i/25),[])
    def test_loss_requires_both_grips_to_release_before_rearming(self):
        z=self.armed();z.update(pair()[:1],10.2);self.assertFalse(z.engaged);self.assertTrue(z.consume)
        for i in range(10):self.assertEqual(z.update(pair(.7),10.24+i/25),[])
        self.assertFalse(z.engaged)
        z.update(pair(grip=False),10.68);z.update(pair(),10.72)
        self.assertTrue(z.engaged)
    def test_identity_handoff_or_stale_frames_never_inherit_the_zoom(self):
        for changes in ({'identities':{'Right':3,'Left':2}}, {'now':10.8}):
            z=self.armed();now=changes.get('now',10.2)
            self.assertEqual(z.update(pair(.8),now,identities=changes.get('identities',{'Right':1,'Left':2})),[])
            self.assertFalse(z.engaged);self.assertTrue(z.consume)
    def test_invalid_landmarks_cannot_create_zoom(self):
        z=self.armed();bad=pair();bad[0][1][0]=(float('nan'),.5)
        self.assertEqual(z.update(bad,10.2),[]);self.assertFalse(z.engaged)
    def test_router_clutches_single_hand_actions_until_both_release(self):
        for mode in ('discrete','analog','mouse','system_mouse'):
            r=HandRules();r.configure({'mode':mode});r.take_pending()
            self.assertIsNone(r.update_pair(pair()[:1],10.))
            events=[]
            for i in range(25):events+=r.update_pair(pair(.4+max(0,i-5)*.01),10.04+i/25)
            self.assertTrue(any(g=='two_hand_zoom' for _,g,_ in events))
            self.assertFalse(any(a in ('up','down','left','right') for _,_,a in events if isinstance(a,str)))
            self.assertIsNotNone(r.update_pair(pair()[:1],11.04))
            self.assertIsNotNone(r.update_pair(pair(grip=False),11.08))
            self.assertIsNone(r.update_pair(pair(grip=False),11.12))
    def test_entering_pair_releases_a_held_mouse_button_without_clicking(self):
        r=HandRules();r.configure({'mode':'system_mouse'});r.take_pending()
        r.mouse.pose='pinch';r.mouse.down=True;r.mouse.pinch_allowed=True
        events=r.update_pair(pair(),10.)
        self.assertEqual([p['phase'] for _,_,p in events if isinstance(p,dict)],['cancel'])
        self.assertFalse(r.mouse.down)
    def test_settings_opt_out_and_joystick_keep_existing_routing(self):
        r=HandRules();r.configure({'two_hand_zoom':False})
        self.assertIsNone(r.update_pair(pair(),10.))
        if 'joystick' in settings():
            r.configure({'mode':'joystick'});self.assertIsNone(r.update_pair(pair(),10.))
        self.assertTrue(settings()['two_hand_zoom'])
        self.assertEqual(settings({'two_hand_zoom_step':float('nan')})['two_hand_zoom_step'],.12)


from PyQt6.QtWidgets import QApplication,QWidget
from core import room_gesture_panel as panel
from core import room_media_keys as media
class NativeZoom(unittest.TestCase):
    def test_mac_zoom_has_native_modifier_press_and_release_without_pyautogui(self):
        for action,key in (('zoom_in',24),('zoom_out',27)):
            created=[];sent=[];released=[];flags=[]
            def create(source,code,down):
                event=(code,down);created.append(event);return event
            api=S(preflight=lambda:True,create_key=create,flags=lambda e,f:flags.append(f),post=lambda tap,e:sent.append(e),release_event=released.append)
            with patch.object(media.sys,'platform','darwin'),patch.object(media,'_load_macos_api',return_value=api):media.dispatch_action(action)
            self.assertEqual(sent,[(55,True),(key,True),(key,False),(55,False)])
            self.assertEqual(released,created);self.assertEqual(flags,[1<<20,1<<20,1<<20,0])
    def test_mac_zoom_releases_keys_after_a_partial_send_failure(self):
        sent=[];released=[];created=[]
        def create(source,key,down):created.append((key,down));return (key,down)
        def post(tap,event):
            sent.append(event)
            if len(sent)==2:raise RuntimeError('native dispatch failed')
        api=S(preflight=lambda:True,create_key=create,flags=lambda *args:None,post=post,release_event=released.append)
        with patch.object(media,'_load_macos_api',return_value=api):
            with self.assertRaises(RuntimeError):media._send_macos_zoom('zoom_in')
        self.assertEqual(sent[-2:],[(24,False),(55,False)]);self.assertEqual(released,created)
    def test_mac_zoom_does_not_request_or_bypass_missing_permission(self):
        api=S(preflight=lambda:False)
        with patch.object(media,'_load_macos_api',return_value=api):
            with self.assertRaises(media.MediaKeyError):media._send_macos_zoom('zoom_out')
class Delivery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_fresh_pair_zoom_targets_foreground_in_system_mouse_and_browser_in_browser_mode(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(panel,'DATA_DIR',Path(tmp)),patch('core.room_media_keys.dispatch_action') as native,patch.object(panel.time,'monotonic',return_value=10.):
            window=QWidget();c=panel.GestureController(window);c._browser_timer.stop()
            c.ready=True;c.process=S(poll=lambda:None);c.browser_media=True;c.control_mode='system_mouse'
            sent=[];c.relay=S(publish=lambda action,**kw:sent.append(action),browser_profile=lambda:dict(revision=0))
            packet=dict(type='action',action='zoom_in',gesture='two_hand_zoom',hand='Both',mode='system_mouse',id=1,captured_monotonic=10.)
            c.receive(packet);native.assert_called_once_with('zoom_in');self.assertFalse(sent)
            c.receive(dict(packet,id=2,captured_monotonic=9.));self.assertEqual(native.call_count,1)
            c.control_mode='mouse';c.receive(dict(packet,id=3,mode='mouse'))
            self.assertEqual(sent,['zoom_in']);self.assertEqual(native.call_count,1)
            c.control_mode='system_mouse';c._pointer_native=S(check_escape=lambda:True)
            c.receive(dict(packet,id=4));self.assertEqual(native.call_count,1)
            c._pointer_native=None
            c.process=None;c.relay=None;window.close()

if __name__=='__main__':unittest.main()
