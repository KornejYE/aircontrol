"""Distance-based analog control: synthetic landmarks only, no camera or keys."""
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_gesture_analog import AnalogDrag,ViewportDrag,command,valid_amount
from core.room_gesture_rules import HandRules,settings,read_settings,save_settings
from core.room_gesture_relay import Relay


def grip(x=.5,y=.5):
    p=[(x,y)]*21;p[0]=(x,y+.2);p[9]=(x,y+.02)
    p[5]=(x-.12,y+.06);p[17]=(x+.12,y+.06)
    p[4]=(x,y);p[8]=(x+.025,y);p[12]=(x-.025,y)
    return p


def uncertain_grip(x=.5,y=.5):
    # Between the calibrated/default closed and clearly open thresholds.
    p=grip(x,y);p[8]=(x+.235,y);p[12]=(x-.275,y)
    p[6]=(x+.28,y-.1);p[10]=(x-.3,y-.1)
    return p


class Analog(unittest.TestCase):
    def test_partial_swipe_moves_partial_viewport_without_a_discrete_next_command(self):
        a=ViewportDrag('Right')
        packets=a.move((.5,.45),.1,origin=(.5,.5))
        self.assertEqual([p['phase'] for p in packets],['start','move'])
        self.assertEqual(packets[0]['position'],0.)
        self.assertAlmostEqual(packets[1]['position'],.25)
        self.assertTrue(all(p['action']=='drag_scroll' and 'steps' not in p and 'amount' not in p for p in packets))
        self.assertAlmostEqual(a.move((.5,.30),.2)[-1]['position'],1.)
        position=a.position
        for frame in range(1,61):
            for packet in a.move((.5,.30),.2+frame/30):self.assertEqual(packet['position'],position)

    def test_absolute_total_and_reversal_are_independent_of_camera_frame_rate(self):
        for fps in (12,30,60):
            a=ViewportDrag('Right');last=None
            for i in range(1,fps+1):
                packets=a.move((.5,.5-.20*i/fps),i/fps,origin=(.5,.5))
                if packets:last=packets[-1]
            self.assertAlmostEqual(last['position'],1.)
            self.assertAlmostEqual(a.move((.5,.45),1.1)[-1]['position'],.25)
            self.assertAlmostEqual(a.move((.5,.5),1.2)[-1]['position'],0.)

    def test_seek_and_volume_amount_scale_with_travel_not_hold_duration(self):
        for action,units in (('right',5),('volume_up',.05),('up',.7)):
            short=command(action,1,1);long=command(action,2,2)
            self.assertAlmostEqual(short['amount'],units)
            self.assertAlmostEqual(long['amount'],2*units)
        self.assertIsNone(command('play_pause',1,1))
        for distance in (float('nan'),float('inf'),float('-inf'),0,-1,True):
            self.assertIsNone(command('up',distance,1))
        for steps in (float('nan'),1.5,-1,5,True):self.assertIsNone(command('up',1,steps))

    def test_jitter_never_repeats_or_reverses_but_real_reverse_movement_works(self):
        a=AnalogDrag();a.update((.5,.5),0,'grab');a.update((.5,.415),.1,'grab')
        for frame in range(1,20):
            self.assertIsNone(a.update((.5,.415+(.004 if frame%2 else -.004)),.1+frame/30,'grab'))
        direction,_,steps=a.update((.5,.51),.8,'grab')
        self.assertEqual((direction,steps),('down',1))

    def test_release_loss_gap_clock_change_and_pose_change_reanchor(self):
        for condition in ('release','gap','clock','pose'):
            a=AnalogDrag();a.update((.5,.5),1,'grab');a.update((.5,.4),1.1,'grab')
            if condition=='release':a.update(None,1.15,None);result=a.update((.5,.3),1.2,'grab')
            elif condition=='gap':result=a.update((.5,.3),1.5,'grab')
            elif condition=='clock':result=a.update((.5,.3),1.,'grab')
            else:result=a.update((.5,.3),1.2,'corner')
            self.assertIsNone(result,condition)

    def test_router_ordinary_default_and_analog_grab_are_separate(self):
        self.assertEqual(settings()['mode'],'discrete')
        ordinary=HandRules();ordinary.update(grip(),0,'Right')
        self.assertEqual(ordinary.update(grip(y=.35),.1,'Right'),('Right','grab_up',{'action':'up','swipe_steps':1}))
        analog=HandRules();analog.configure(dict(mode='analog'));analog.update(grip(),0,'Right')
        packets=analog.update(grip(y=.45),.1,'Right')
        self.assertEqual([v[2]['phase'] for v in packets],['start','move'])
        self.assertEqual(packets[-1][2]['action'],'drag_scroll')
        self.assertAlmostEqual(packets[-1][2]['position'],.05/.20)
        for frame in range(1,20):
            for _,_,payload in analog.update(grip(y=.45),.1+frame/30,'Right') or []:
                self.assertAlmostEqual(payload['position'],.05/.20)
        self.assertEqual(analog.update(None,.8,'Right')[0][2]['phase'],'cancel')
        self.assertIsNone(analog.update(grip(y=.2),.9,'Right'))

    def test_release_ends_same_id_and_new_clutch_has_a_new_anchor(self):
        router=HandRules();router.configure({'mode':'analog'})
        router.update(grip(),0,'Right');first=router.update(grip(y=.43),.1,'Right')
        identity=first[0][2]['gesture_id']
        opened=grip(y=.43);opened[4]=(.2,.4);opened[8]=(.4,.2);opened[12]=(.6,.2)
        end=router.update(opened,.15,'Right')
        self.assertEqual(end[0][2]['phase'],'end');self.assertEqual(end[0][2]['gesture_id'],identity)
        router.update(grip(y=.3),.2,'Right');second=router.update(grip(y=.23),.3,'Right')
        self.assertNotEqual(second[0][2]['gesture_id'],identity)
        self.assertAlmostEqual(second[-1][2]['position'],.35)

    def test_one_grab_crosses_multiple_viewports_and_reverses_without_reanchoring(self):
        for fps in (12,30,60):
            router=HandRules();router.configure({'mode':'analog'})
            router.update(grip(y=.70),0,'Right');packets=[]
            for frame in range(1,fps+1):
                packets.extend(router.update(grip(y=.70-.48*frame/fps),frame/fps,'Right') or [])
            identities={packet['gesture_id'] for _,_,packet in packets}
            self.assertEqual(len(identities),1)
            self.assertEqual(sum(packet['phase']=='start' for _,_,packet in packets),1)
            self.assertFalse(any(packet['phase'] in ('end','cancel') for _,_,packet in packets))
            self.assertAlmostEqual(packets[-1][2]['position'],2.4)
            reverse=router.update(grip(y=.38),1.1,'Right')
            self.assertAlmostEqual(reverse[-1][2]['position'],1.6)
            self.assertIn(reverse[-1][2]['gesture_id'],identities)

    def test_ambiguous_grip_holds_position_briefly_then_resumes_same_drag(self):
        router=HandRules();router.configure({'mode':'analog'})
        router.update(grip(),0,'Right');start=router.update(grip(y=.43),.1,'Right')
        identity=start[0][2]['gesture_id'];position=start[-1][2]['position']
        self.assertIsNone(router.update(uncertain_grip(y=.4),.14,'Right'))
        self.assertFalse(router.engines['Right'].feedback['grip'])
        self.assertFalse(router.engines['Right'].feedback['grip_open'])
        self.assertEqual(router.scroll['Right'].position,position)
        resumed=router.update(grip(y=.36),.17,'Right')
        self.assertEqual([packet['phase'] for _,_,packet in resumed],['move'])
        self.assertEqual(resumed[-1][2]['gesture_id'],identity)
        self.assertAlmostEqual(resumed[-1][2]['position'],.7)

    def test_uncertain_grip_grace_never_hides_open_release_or_hand_loss(self):
        for condition in ('open','missing','timeout'):
            router=HandRules();router.configure({'mode':'analog'})
            router.update(grip(),0,'Right');router.update(grip(y=.43),.1,'Right')
            self.assertIsNone(router.update(uncertain_grip(y=.4),.14,'Right'))
            if condition=='missing':packets=router.update(None,.17,'Right');phase='cancel'
            elif condition=='timeout':packets=router.update(uncertain_grip(y=.38),.22,'Right');phase='end'
            else:
                opened=grip(y=.43);opened[4]=(.2,.4);opened[8]=(.4,.2);opened[12]=(.6,.2)
                packets=router.update(opened,.17,'Right');phase='end'
            self.assertEqual([packet['phase'] for _,_,packet in packets],[phase],condition)
            self.assertIsNone(router.scroll['Right'].gesture_id)

    def test_invalid_stale_and_reconfigured_capture_cancel_the_old_drag(self):
        for condition in ('invalid','stale','mode','distance','identity','gap'):
            router=HandRules();router.configure({'mode':'analog'})
            router.update(grip(),0,'Right');router.update(grip(y=.43),.1,'Right')
            if condition=='invalid':packets=router.update([[float('nan'),0]]*21,.15,'Right')
            elif condition=='stale':packets=router.update(grip(y=.4),.15,'Right',allow_actions=False)
            elif condition=='mode':router.configure({'mode':'discrete'});packets=router.take_pending()
            elif condition=='distance':router.set_distance(.14);packets=router.take_pending();self.assertEqual(router.engines['Right'].distance,.14)
            elif condition=='identity':router.reset_hand('Right');packets=router.take_pending()
            else:packets=router.update(grip(y=.3),.5,'Right')
            self.assertEqual([p[2]['phase'] for p in packets],['cancel'],condition)
            self.assertIsNone(router.scroll['Right'].gesture_id)

    def test_corner_volume_and_swap_use_the_logical_left_hand(self):
        data=runpy.run_path(str(Path(__file__).with_name('test-corner-geometry.py')))
        corner,shift=data['corner'],data['shifted']
        for swapped,physical in ((False,'Left'),(True,'Right')):
            router=HandRules();router.configure(dict(mode='analog',swap_hands=swapped))
            for stamp in (0,.1,.28):self.assertIsNone(router.update(corner,stamp,physical))
            result=router.update(shift(corner,y=-.12),.4,physical)
            self.assertEqual(result[:2],('Left','corner_up'));self.assertEqual(result[2]['action'],'volume_up')
            self.assertGreater(result[2]['amount'],.05)
            self.assertIsNone(router.update(shift(corner,y=-.12),.5,physical))

    def test_custom_nonlinear_binding_remains_one_shot_until_finger_release(self):
        for action in ('play_pause','mute','next_track','zoom_in'):
            router=HandRules();cfg=settings({'mode':'analog'});cfg['rules']['Right']['grab_up']=action;router.configure(cfg)
            router.update(grip(),0,'Right')
            self.assertEqual(router.update(grip(y=.4),.1,'Right'),('Right','grab_up',action))
            self.assertIsNone(router.update(grip(y=.3),.2,'Right'))
            self.assertIsNone(router.update(grip(y=.2),.3,'Right'))
            router.update(None,.4,'Right');router.update(grip(y=.2),.5,'Right')
            self.assertIsNone(router.update(grip(y=.1),.6,'Right'))
            opened=grip();opened[4]=(.2,.4);opened[8]=(.4,.2);opened[12]=(.6,.2)
            router.update(opened,.7,'Right');router.update(grip(),.8,'Right')
            self.assertEqual(router.update(grip(y=.4),.9,'Right'),('Right','grab_up',action))

    def test_persistence_preserves_bindings_and_normalizes_invalid_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.json';cfg=settings({'mode':'analog','swap_hands':True})
            cfg['rules']['Right']['grab_up']='down';save_settings(path,cfg)
            self.assertEqual(read_settings(path),cfg)
            old=json.loads(path.read_text());old.pop('mode');path.write_text(json.dumps(old))
            self.assertEqual(read_settings(path)['mode'],'discrete')
        self.assertEqual(settings({'mode':'other','analog_speed':float('nan')})['analog_speed'],1.)
        self.assertEqual(settings({'analog_span':float('nan')})['analog_span'],.20)
        self.assertEqual(settings({'analog_span':.01})['analog_span'],.12)
        self.assertEqual(settings({'analog_span':2})['analog_span'],.60)

    def test_relay_carries_bounded_amounts_and_expires_analog_quickly(self):
        from unittest.mock import patch
        relay=Relay()
        with patch('core.room_gesture_relay.time.time',return_value=10):
            relay.publish('up',amount=.7,steps=1);relay.publish('left')
            self.assertEqual(relay.snapshot(0,relay.session)['events'][0]['amount'],.7)
            self.assertEqual([e['direction'] for e in relay.snapshot(0,relay.session,analog=False)['events']],['left'])
        with patch('core.room_gesture_relay.time.time',return_value=10.31):
            self.assertEqual([e['direction'] for e in relay.snapshot(0,relay.session)['events']],['left'])
        for value in (float('nan'),float('inf'),-1,0,20):
            with self.assertRaises(ValueError):relay.publish('up',amount=value)
        self.assertFalse(valid_amount('play_pause',.1))
        old=relay.session;relay.invalidate()
        self.assertNotEqual(relay.session,old);self.assertEqual(relay.snapshot(0,relay.session)['events'],[])


if __name__=='__main__':unittest.main()
