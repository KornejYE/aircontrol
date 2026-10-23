"""Ordinary wrist-only stepping, distance controls and mode isolation. No camera/input."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_gesture_rules import HandRules
from core.room_gesture_relay import Relay

def grip(travel=0.):
 p=[(.5,.5)]*21;p[0]=(.5,.7);p[9]=(.5,.52);p[5]=(.38,.56);p[17]=(.62,.56)
 for i,x in ((4,.5),(8,.525),(12,.475),(6,.5),(10,.5)):p[i]=(x,.5-travel)
 return p

def count(value):return value[2].get('swipe_steps',0) if value and isinstance(value[2],dict) else 0

class Stepped(unittest.TestCase):
 def test_minimum_range_accepts_finger_movement_with_palm_and_wrist_fixed(self):
  r=HandRules(distance=.04);r.update(grip(),0,'Right')
  before,after=grip(),grip(.045)
  self.assertTrue(all(before[i]==after[i] for i in (0,5,9,13,17)))
  event=r.update(after,.1,'Right')
  self.assertEqual(event,('Right','grab_up',{'action':'up','swipe_steps':1}))
  for i in range(1,31):self.assertIsNone(r.update(after,.1+i/30,'Right'))

 def test_one_long_wrist_sweep_earns_four_steps_at_different_camera_rates(self):
  for fps in (12,30,60):
   for swap,physical in ((False,'Right'),(True,'Left')):
    r=HandRules();r.configure({'swap_hands':swap});r.update(grip(),0,physical);events=[]
    for frame in range(1,fps+1):
     e=r.update(grip(.36*frame/fps),frame/fps,physical)
     if e:events.append(e)
    e=r.update(grip(.36),1.1,physical)
    if e:events.append(e)
    self.assertEqual(sum(map(count,events)),4,(fps,swap,events))
    self.assertTrue(all(e[:2]==('Right','grab_up') for e in events))
    for frame in range(1,fps+1):self.assertIsNone(r.update(grip(.36),1.1+frame/fps,physical))

 def test_horizontal_sweep_counts_steps_and_holding_does_not_repeat(self):
  for sign,direction in ((1,'right'),(-1,'left')):
   def horizontal(travel):
    return [(x+sign*travel,y) for x,y in grip()]
   r=HandRules(distance=.04);r.update(horizontal(0),0,'Right');events=[]
   for frame in range(1,31):
    e=r.update(horizontal(.17*frame/30),frame/30,'Right')
    if e:events.append(e)
   e=r.update(horizontal(.17),1.1,'Right')
   if e:events.append(e)
   self.assertEqual(sum(map(count,events)),4)
   self.assertTrue(all(e[2]['action']==direction for e in events))
   for i in range(20):self.assertIsNone(r.update(horizontal(.17),1.2+i/30,'Right'))

 def test_short_range_does_not_inherit_large_hand_floor_or_previous_saved_range(self):
  r=HandRules(distance=.20);r.update(grip(),0,'Right');self.assertIsNone(r.update(grip(.045),.1,'Right'))
  r.set_distance(.04);r.update(grip(),.2,'Right');self.assertEqual(count(r.update(grip(.045),.3,'Right')),1)

 def test_loss_mode_change_and_owner_change_discard_old_remainder(self):
  for condition in ('loss','mode','owner','disabled','gap'):
   r=HandRules();r.update(grip(),0,'Right');r.update(grip(.06),.1,'Right')
   if condition=='loss':r.update(None,.15,'Right')
   elif condition=='mode':r.configure({'mode':'analog'});r.configure({'mode':'discrete'})
   elif condition=='owner':r.reset_hand('Right')
   elif condition=='disabled':r.update(grip(.06),.15,'Right',allow_actions=False)
   else:r.update(grip(.06),.5,'Right')
   t=.6 if condition=='gap' else .2
   self.assertIsNone(r.update(grip(.10),t,'Right'),condition)

 def test_analog_still_follows_palm_and_emits_no_ordinary_steps(self):
  r=HandRules();r.configure({'mode':'analog'});r.update(grip(),0,'Right')
  self.assertIsNone(r.update(grip(.045),.1,'Right'))
  moved=[(x,y-.10) for x,y in grip(.045)]
  events=r.update(moved,.2,'Right')
  self.assertTrue(events)
  self.assertTrue(all(e[2]['action']=='drag_scroll' and 'swipe_steps' not in e[2] for e in events))

 def test_relay_preserves_finite_step_count_and_rejects_mixed_or_invalid_commands(self):
  r=Relay();r.publish('up',swipe_steps=3)
  self.assertEqual(r.snapshot(0,r.session)['events'][0]['swipe_steps'],3)
  for action in ('left','right','volume_up','volume_down'):
   r.publish(action,swipe_steps=3);self.assertEqual(r.events[-1]['swipe_steps'],3)
  for value in (True,0,-1,5,1.5,float('nan')):
   with self.assertRaises(ValueError):r.publish('up',swipe_steps=value)
  with self.assertRaises(ValueError):r.publish('play_pause',swipe_steps=2)
  with self.assertRaises(ValueError):r.publish('up',swipe_steps=2,amount=.7)

if __name__=='__main__':unittest.main()
