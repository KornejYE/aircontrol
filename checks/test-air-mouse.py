"""Replay mouse gestures without accessing a camera or generating real input."""
import sys,unittest,math,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_air_mouse import AirMouse,valid_pointer,pointer_gain
from core.room_gesture_rules import HandRules,poses,settings
from core.room_gesture_relay import Relay

def point(dx=0,dy=0):
 p=[(.5,.8),(.38,.7),(.30,.65),(.25,.6),(.2,.55),(.43,.6),(.43,.43),(.43,.3),(.43,.2),(.50,.6),(.50,.5),(.52,.6),(.52,.68),(.57,.62),(.58,.53),(.6,.62),(.6,.7),(.64,.65),(.65,.56),(.67,.65),(.67,.72)]
 return [(x+dx,y+dy) for x,y in p]
def pinch(dx=0,dy=0):
 p=point(dx,dy);p[4]=(p[8][0]+.02,p[8][1]);return p
def fist():
 p=point()
 for i in (8,12,16,20):p[i]=(.5,.75)
 p[4]=(.45,.66);return p
def relaxed(dx=0,dy=0):
 p=point();p[8]=(.43,.50);p[4]=(.25,.50)
 return [(x+dx,y+dy) for x,y in p]
def scroll_grab(dx=0,dy=0):
 p=point();p[4]=(.44,.46);p[8]=(.43,.45);p[12]=(.45,.45)
 return [(x+dx,y+dy) for x,y in p]
def run(mouse,p,t,**options):
 norm,flags=poses(p) if p is not None else (.2,{})
 return mouse.update(p,t,norm=norm,flags=flags,**options)
class Mouse(unittest.TestCase):
 def test_pointer_movement_and_fist_freeze(self):
  m=AirMouse();run(m,point(),0);out=run(m,point(.04),.1)
  self.assertGreater(m.xy[0],.5);self.assertTrue(any(e['phase']=='move' for e in out))
  frozen=m.xy[:];self.assertTrue(poses(fist())[1]['fist'])
  out=run(m,fist(),.2);self.assertEqual([e['phase'] for e in out],['cancel'])
  for t in (.3,.4,.5):self.assertEqual(run(m,fist(),t),[])
  self.assertEqual(m.xy,frozen)
 def test_pinch_release_clicks_once_without_cursor_jump(self):
  m=AirMouse();run(m,point(),0);position=m.xy[:]
  run(m,pinch(),.1);run(m,pinch(),.2);out=run(m,point(),.3)
  self.assertEqual(sum(e['phase']=='click' for e in out),1);self.assertEqual(m.xy,position)
  self.assertFalse(any(e['phase']=='click' for e in run(m,point(),.4)))
 def test_drag_and_fist_release_without_click(self):
  m=AirMouse();run(m,point(),0);run(m,pinch(),.1)
  out=run(m,pinch(.04),.22);self.assertEqual(sum(e['phase']=='down' for e in out),1);self.assertTrue(m.down)
  out+=run(m,pinch(.06),.3);self.assertEqual(sum(e['phase']=='down' for e in out),1)
  out=run(m,fist(),.4);self.assertEqual([e['phase'] for e in out],['cancel']);self.assertFalse(m.down)
 def test_loss_time_jump_and_teleport_never_click(self):
  for failure in (None,point(.5),point()):
   m=AirMouse();run(m,point(),0);run(m,pinch(),.1)
   out=run(m,failure,1.)
   self.assertFalse(any(e['phase']=='click' for e in out));self.assertFalse(m.down)
 def test_one_missing_frame_freezes_then_uses_newly_observed_nearby_travel(self):
  for fps in (15,30,60):
   m=AirMouse();run(m,point(),0);run(m,point(.01),1/fps);before=m.relative[:]
   out=run(m,None,2/fps);self.assertFalse(any(e['phase']=='cancel' for e in out));self.assertIsNotNone(m.missing_since)
   self.assertEqual(m.relative,before,'no motion while the hand is invisible')
   out+=run(m,point(.04),3/fps)
   self.assertGreater(m.relative[0],before[0]);self.assertLessEqual(m.relative[0],.0840001)
   self.assertFalse(any(e['phase'] in ('click','down','cancel') for e in out))
   self.assertEqual(m.pose,'point');self.assertIsNone(m.missing_since)
   run(m,point(.05),4/fps);self.assertGreater(m.relative[0],before[0])
   self.assertEqual(m.diagnostics['recoveries'],1)
 def test_long_missing_period_cancels_once_and_never_predicts_movement(self):
  m=AirMouse();run(m,point(),0);before=m.relative[:];out=[]
  for t in (.03,.09,.15,.21,.27,.33):out+=run(m,None,t)
  self.assertEqual(sum(e['phase']=='cancel' for e in out),1)
  self.assertEqual(m.relative,before);self.assertIsNone(m.pose)
 def test_scroll_bridges_missing_frame_and_preserves_observed_travel(self):
  m=AirMouse();run(m,scroll_grab(),0);run(m,scroll_grab(dy=-.01),.1)
  out=run(m,None,.13);self.assertTrue(all(e['phase']=='scroll' and e['dy']==0 for e in out))
  out+=run(m,scroll_grab(dy=-.04),.16)
  self.assertTrue(all(e['phase']=='scroll' and 0<=e['dy']<=.12 for e in out))
  self.assertTrue(any(e['dy']>0 for e in out))
  out=run(m,scroll_grab(dy=-.05),.2);self.assertTrue(any(e.get('dy',0)>0 for e in out))
 def test_missing_during_pinch_or_drag_releases_immediately_without_click(self):
  for drag in (False,True):
   m=AirMouse();run(m,point(),0);run(m,pinch(),.1)
   if drag:run(m,pinch(.04),.22);self.assertTrue(m.down)
   lost_at=.25 if drag else .13
   out=run(m,None,lost_at);self.assertEqual([e['phase'] for e in out],['cancel']);self.assertFalse(m.down)
   out+=run(m,pinch(),lost_at+.03);out+=run(m,point(),lost_at+.07)
   self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_valid_frame_after_time_gap_is_processed_on_first_return(self):
  m=AirMouse();run(m,point(),0);out=run(m,point(.03),.26)
  self.assertEqual(m.pose,'point');self.assertEqual([e['phase'] for e in out],['cancel','move'])
  self.assertEqual(m.diagnostics['time_gaps'],1)
 def test_disabled_or_stale_hand_input_is_a_hard_cancel_without_grace(self):
  r=HandRules();r.configure({'mode':'system_mouse'})
  r.update(point(),0,'Right');out=r.update(point(.01),.03,'Right',allow_actions=False)
  self.assertEqual([e[2]['phase'] for e in out],['cancel']);self.assertIsNone(r.mouse.missing_since)
  self.assertIsNone(r.mouse.pose)
 def test_owner_change_cannot_inherit_a_temporarily_missing_pointer(self):
  r=HandRules();r.configure({'mode':'system_mouse'})
  r.update(point(),0,'Right');r.update(None,.03,'Right');self.assertIsNotNone(r.mouse.missing_since)
  r.reset_hand('Right');self.assertIsNone(r.mouse.pose);self.assertIsNone(r.mouse.missing_since)
  self.assertEqual([e[2]['phase'] for e in r.take_pending()],['cancel'])
 def test_relative_distance_is_stable_across_frame_rates(self):
  results=[]
  for fps in (12,30,60):
   m=AirMouse();run(m,point(),0)
   for frame in range(1,fps+1):run(m,point(.1*frame/fps),frame/fps)
   for frame in range(1,10):run(m,point(.1),1+frame/fps)
   results.append(m.xy[0])
  self.assertLess(max(results)-min(results),.01)
 def test_relative_travel_continues_past_virtual_edge_and_reverses_immediately(self):
  m=AirMouse();run(m,point(),0)
  for frame in range(1,31):out=run(m,point(.01*frame),frame/30)
  self.assertEqual(m.xy[0],1.);self.assertGreater(out[-1]['relative_x'],.5)
  for frame in range(31,36):out=run(m,point(.3),frame/30)
  before=m.relative[0]
  out=run(m,point(.25),1.2)
  self.assertLess(out[-1]['relative_x'],before)
 def test_bent_index_pinch_click_is_not_misclassified_as_fist(self):
  m=AirMouse();run(m,point(),0)
  p=point();p[8]=(.43,.46);p[4]=(.45,.46)
  self.assertLess(math.dist(p[8],p[0]),math.dist(p[6],p[0])*1.12)
  run(m,p,.1);self.assertEqual(m.pose,'pinch')
  out=run(m,point(),.2);self.assertEqual(sum(e['phase']=='click' for e in out),1)
 def test_relaxed_hook_pose_arms_from_first_sight_and_moves_both_mirrors(self):
  for mirror in (False,True):
   transform=lambda p:[(1-x,y) for x,y in p] if mirror else p
   p=transform(relaxed());norm,flags=poses(p)
   self.assertFalse(flags['fist']);self.assertFalse(any(math.dist(p[t],p[0])>math.dist(p[t-2],p[0])*1.12 for t in (8,12,16,20)))
   m=AirMouse();run(m,p,0);self.assertEqual(m.pose,'point');self.assertTrue(m.point_ready)
   out=run(m,transform(relaxed(.03)),.1)
   self.assertEqual(m.pose,'point');self.assertTrue(any(e['phase']=='move' for e in out))
   self.assertGreater(abs(m.relative[0]),.03)
   out=run(m,transform(fist()),.2);self.assertEqual([e['phase'] for e in out],['cancel'])
 def test_finger_articulation_does_not_move_relative_aim_and_clicks_once(self):
  m=AirMouse();run(m,point(),0);before=m.xy[:];events=[]
  for frame in range(1,11):
   p=point();f=frame/10;p[8]=(.43,.2+.3*f);p[4]=(.2+.25*f,.55-.05*f)
   events+=run(m,p,frame/30)
  self.assertEqual(m.pose,'pinch')
  events+=run(m,relaxed(),.4)
  self.assertEqual(sum(e['phase']=='click' for e in events),1)
  self.assertEqual(m.xy,before);self.assertEqual(m.relative,[0.,0.])
 def test_finger_bending_does_not_move_wrist_aim_and_contact_rebases_on_release(self):
  for fps in (15,30,60):
   m=AirMouse();run(m,relaxed(),0);before=m.xy[:];events=[]
   for frame in range(1,round(.3*fps)+1):
    f=frame/round(.3*fps);p=relaxed();p[6]=(.43,.43+.025*f);p[8]=(.43,.50+.025*f);p[4]=(.25+.17*f,.50+.025*f)
    events+=run(m,p,frame/fps)
   self.assertEqual(m.pose,'pinch');self.assertFalse(m.down)
   events+=run(m,relaxed(),.4)
   self.assertEqual(sum(e['phase']=='click' for e in events),1)
   self.assertLess(abs(m.xy[1]-before[1]),.001)
   previous=m.xy[:];run(m,relaxed(.02),.5)
   self.assertGreater(m.xy[0],previous[0]);self.assertLess(abs(m.xy[1]-previous[1]),.001)
 def test_aborted_closure_never_clicks_and_cursor_resumes_without_jump(self):
  m=AirMouse();run(m,relaxed(),0)
  p=relaxed();p[8]=(.43,.52);p[4]=(.33,.52)
  out=run(m,p,.1);self.assertEqual(m.pose,'point')
  out+=run(m,relaxed(),.2)
  self.assertFalse(any(e['phase'] in ('click','down') for e in out))
  before=m.xy[:];run(m,relaxed(.03),.3);self.assertGreater(m.xy[0],before[0])
 def test_closed_pinch_articulation_does_not_start_drag_but_palm_movement_does(self):
  m=AirMouse();run(m,relaxed(),0)
  p=relaxed();p[4]=(.44,.50);run(m,p,.1)
  p[8]=(.43,.53);p[4]=(.44,.53);p[6]=(.43,.45)
  out=run(m,p,.25);self.assertFalse(m.down);self.assertFalse(any(e['phase']=='down' for e in out))
  translated=[(x+.04,y) for x,y in p];out=run(m,translated,.35)
  self.assertTrue(m.down);self.assertEqual(sum(e['phase']=='down' for e in out),1)
  self.assertEqual([e['phase'] for e in run(m,fist(),.45)],['cancel'])
 def test_compact_fist_near_index_knuckle_never_clicks_on_reopen(self):
  for tip in ((.47,.59),(.43,.57),(.44,.6)):
   m=AirMouse();run(m,point(),0);p=fist();p[8]=tip
   self.assertTrue(poses(p)[1]['fist'])
   out=run(m,p,.1);self.assertEqual(m.pose,'fist')
   out+=run(m,point(),.2)
   self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_held_half_closed_pose_or_tracking_loss_cannot_create_a_click(self):
  for lose_tracking in (False,True):
   m=AirMouse();run(m,relaxed(),0)
   p=relaxed();p[8]=(.43,.52);p[4]=(.33,.52)
   out=run(m,p,.1);self.assertEqual(m.pose,'point')
   if lose_tracking:out+=run(m,None,.2)
   else:
    for frame in range(2,10):out+=run(m,p,frame/10)
   self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_gradually_bending_fingers_never_freezes_moving_wrist(self):
  m=AirMouse();run(m,relaxed(),0);previous=0.
  for frame in range(1,31):
   f=frame/30;p=relaxed();p[8]=(.43,.50+.03*f);p[4]=(.25+.06*f,.50+.03*f);p[6]=(.43,.43+.04*f)
   p=[(x+.04*f,y) for x,y in p]
   out=run(m,p,frame/30)
   self.assertEqual(m.pose,'point');self.assertGreater(m.relative[0],previous)
   self.assertFalse(any(e['phase'] in ('click','down','cancel') for e in out));previous=m.relative[0]
  for frame in range(1,11):run(m,p,1+frame/30)
  self.assertAlmostEqual(m.relative[0],.084,delta=.001)
 def test_close_but_separated_fingers_are_free_aim_until_real_pinch(self):
  m=AirMouse();run(m,relaxed(),0);p=relaxed();norm=poses(p)[0]
  p[4]=(p[8][0]+norm*.30,p[8][1]);run(m,p,.1);self.assertEqual(m.pose,'point')
  p[4]=(p[8][0]+norm*.20,p[8][1]);run(m,p,.2);self.assertEqual(m.pose,'pinch')
  out=run(m,relaxed(),.3);self.assertEqual(sum(e['phase']=='click' for e in out),1)
 def test_deeply_hooked_index_with_open_thumb_is_not_a_closed_fist(self):
  m=AirMouse();p=relaxed();p[8]=(.44,.64)
  run(m,p,0);self.assertEqual(m.pose,'point')
  translated=[(x+.02,y) for x,y in p];out=run(m,translated,.1)
  self.assertGreater(m.relative[0],0);self.assertEqual(m.pose,'point')
  self.assertFalse(any(e['phase'] in ('cancel','click','down') for e in out))
 def test_pinch_release_does_not_jump_to_reopened_tip_in_absolute_mode(self):
  m=AirMouse();p=point();m.update(p,0,norm=poses(p)[0],positioning='absolute');before=m.xy[:]
  p=pinch();m.update(p,.1,norm=poses(p)[0],positioning='absolute')
  p=point(.05);out=m.update(p,.2,norm=poses(p)[0],positioning='absolute')
  self.assertEqual(sum(e['phase']=='click' for e in out),1);self.assertEqual(m.xy,before)
 def test_one_frame_false_scroll_pose_does_not_rebase_pointer(self):
  m=AirMouse();run(m,point(),0);run(m,point(.01),.033)
  p=point(.02);p[12]=(.52,.2);p[11]=(.52,.3)
  run(m,p,.066);self.assertEqual(m.pose,'point')
  out=run(m,point(.03),.1)
  self.assertGreater(m.relative[0],.025);self.assertFalse(any(e['phase']=='scroll' for e in out))
 def test_smoothing_reduces_stationary_landmark_jitter(self):
  m=AirMouse();run(m,point(),0);values=[]
  for frame in range(1,61):
   run(m,point(.003*(-1)**frame),frame/60);values.append(m.relative[0])
  self.assertLess(max(values[20:])-min(values[20:]),.003)
 def test_independent_palm_landmark_noise_is_damped_at_actual_camera_cadence(self):
  # 0.64 camera-pixel sigma per landmark, independent of the other anchors.
  # Moving every landmark together misses the old extrapolated-MCP noise bug.
  m=AirMouse();run(m,point(),0);rng=random.Random(24);values=[]
  for frame in range(1,601):
   p=point()
   for i in (0,5,9,13,17):p[i]=tuple(a+rng.gauss(0,.001) for a in p[i])
   run(m,p,frame/25)
   if frame>100:values.append(m.relative[0]*2560)
  values.sort()
  self.assertLess(values[int(len(values)*.95)]-values[int(len(values)*.05)],14.)
  self.assertEqual(m.pose,'point')
 def test_alternating_detector_misses_do_not_swallow_an_entire_stroke(self):
  m=AirMouse();run(m,point(),0);events=[];previous=0.
  for frame in range(1,61):
   events+=run(m,None if frame%2 else point(.001*frame),frame/30)
   self.assertGreaterEqual(m.relative[0],previous)
   if frame%2:self.assertEqual(m.relative[0],previous)
   previous=m.relative[0]
  self.assertGreater(m.relative[0],.115);self.assertLessEqual(m.relative[0],.1260001)
  self.assertFalse(any(e['phase'] in ('click','down','cancel') for e in events))
 def test_distant_return_after_missing_is_rebased_without_motion(self):
  m=AirMouse();run(m,point(),0);run(m,point(.01),.033);before=m.relative[:]
  run(m,None,.066);out=run(m,point(.25),.1)
  self.assertEqual(m.relative,before)
  self.assertFalse(any(e['phase'] in ('click','down') for e in out))
  run(m,point(.26),.133);self.assertGreater(m.relative[0],before[0])
 def test_relaxed_bent_hand_survives_short_loss_without_becoming_a_fist(self):
  m=AirMouse();run(m,relaxed(),0);p=relaxed();p[4]=(.37,.50)
  run(m,p,.033);self.assertEqual(m.pose,'point')
  events=run(m,None,.066)
  for frame in range(3,8):
   translated=[(x+.005*(frame-2),y) for x,y in p]
   events+=run(m,translated,frame*.033)
   self.assertEqual(m.pose,'point')
  self.assertGreater(m.relative[0],.02)
  self.assertFalse(any(e['phase'] in ('cancel','click','down') for e in events))
  events=run(m,fist(),.28);self.assertEqual([e['phase'] for e in events],['cancel'])
 def test_brief_three_finger_candidate_does_not_freeze_relaxed_aim(self):
  m=AirMouse();run(m,relaxed(),0);events=[]
  for frame in range(1,4):
   p=relaxed(.01*frame)
   if frame<3:
    p[4]=(.36+.01*frame,.50);p[12]=(.40+.01*frame,.52)
   before=m.relative[0];events+=run(m,p,frame*.04)
   self.assertEqual(m.pose,'point');self.assertGreater(m.relative[0],before)
  self.assertFalse(any(e['phase'] in ('scroll','click','down','cancel') for e in events))
 def test_slow_aim_emits_every_measured_frame_instead_of_80ms_steps(self):
  m=AirMouse();run(m,point(),0);previous=0.
  for frame in range(1,61):
   events=run(m,point(.00015*frame),frame/25)
   self.assertTrue(any(e['phase']=='move' for e in events))
   self.assertGreater(m.relative[0],previous);previous=m.relative[0]
 def test_smoothing_still_follows_a_deliberate_fast_wrist_stroke(self):
  for mirror in (False,True):
   transform=lambda p:[(1-x,y) for x,y in p] if mirror else p
   m=AirMouse();run(m,transform(point()),0)
   for frame in range(1,4):run(m,transform(point(.02*frame)),frame/30)
   self.assertGreater(abs(m.relative[0]),.11)
   self.assertLessEqual(abs(m.relative[0]),.1260001)
 def test_absolute_positioning_is_explicit_and_fist_still_freezes(self):
  r=HandRules();r.configure({'mode':'mouse','mouse_position':'absolute'})
  first=r.update(point(),0,'Right')[0][2];self.assertTrue(first['absolute']);self.assertAlmostEqual(first['x'],.4)
  r.update(fist(),.1,'Right');position=r.mouse.xy[:];self.assertIsNone(r.update(fist(),.2,'Right'));self.assertEqual(position,r.mouse.xy)
 def test_arriving_with_pinched_fingers_cannot_click_or_drag(self):
  m=AirMouse();out=run(m,pinch(),0);out+=run(m,pinch(.04),.15);out+=run(m,point(.04),.25)
  self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_scroll_and_context_menu_do_not_click(self):
  m=AirMouse();p=point();p[12]=(.5,.2);p[11]=(.5,.3)
  run(m,p,0);out=run(m,[(x,y+.04) for x,y in p],.1)
  self.assertTrue(any(e['phase']=='scroll' for e in out));self.assertFalse(any(e['phase']=='click' for e in out))
  m=AirMouse();p=point();p[4]=(.54,.68);run(m,p,0);out=run(m,p,.15)
  self.assertEqual(sum(e['phase']=='context' for e in out),1);self.assertFalse(any(e['phase']=='context' for e in run(m,p,.25)))
 def test_three_finger_grip_scrolls_like_touch_without_selecting_text(self):
  for mirror in (False,True):
   transform=lambda p:[(1-x,y) for x,y in p] if mirror else p
   m=AirMouse();run(m,transform(point()),0);before=m.xy[:]
   out=run(m,transform(scroll_grab()),.1)
   self.assertEqual(m.pose,'point','brief proximity of three fingers does not clutch')
   out+=run(m,transform(scroll_grab()),.21)
   self.assertEqual(m.pose,'scroll_grab');self.assertFalse(m.point_ready)
   self.assertFalse(any(e['phase']=='scroll' for e in out),'entry is rebased')
   out+=run(m,transform(scroll_grab(dy=-.02)),.31)
   self.assertTrue(any(e['phase']=='scroll' and e['dy']>0 for e in out))
   out+=run(m,transform(scroll_grab(dy=.02)),.41)
   self.assertTrue(any(e['phase']=='scroll' and e['dy']<0 for e in out))
   self.assertEqual(m.xy,before)
   self.assertFalse(any(e['phase'] in ('click','down','context') for e in out))
 def test_scroll_grip_contact_flicker_cannot_click_on_release(self):
  m=AirMouse();run(m,point(),0);out=run(m,scroll_grab(),.1)
  out+=run(m,scroll_grab(),.21)
  p=scroll_grab();p[12]=(.54,.45);out+=run(m,p,.3)
  self.assertEqual(m.pose,'scroll_grab','release threshold tolerates a loose contact')
  p[12]=(.57,.45);out+=run(m,p,.4);self.assertEqual(m.pose,'pinch')
  out+=run(m,point(),.5)
  self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_joining_third_finger_releases_drag_before_scrolling(self):
  m=AirMouse();run(m,point(),0);run(m,pinch(),.1);run(m,pinch(.04),.22);self.assertTrue(m.down)
  out=run(m,scroll_grab(.04),.3);self.assertEqual(out[0]['phase'],'up');self.assertFalse(m.down)
  self.assertFalse(any(e['phase']=='scroll' for e in out))
  out+=run(m,scroll_grab(.04,-.02),.4)
  self.assertTrue(any(e['phase']=='scroll' for e in out));self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_scroll_reopen_fist_and_loss_cannot_click(self):
  for release in (point(),fist(),None):
   m=AirMouse();run(m,point(),0);out=run(m,scroll_grab(),.1);out+=run(m,scroll_grab(dy=-.01),.2);out+=run(m,release,.3)
   self.assertFalse(any(e['phase'] in ('click','down') for e in out))
 def test_slow_scroll_conserves_distance_at_high_frame_rates(self):
  distances=[]
  for fps in (15,30,60):
   m=AirMouse();run(m,scroll_grab(),0);out=[]
   for frame in range(1,fps+1):out+=run(m,scroll_grab(dy=-.005*frame/fps),frame/fps)
   for frame in range(1,round(.5*fps)+1):out+=run(m,scroll_grab(dy=-.005),1+frame/fps)
   distances.append(sum(e.get('dy',0) for e in out if e['phase']=='scroll'))
   self.assertGreater(distances[-1],.0145)
   self.assertTrue(any(e['phase']=='scroll' and e['dy']==0 for e in out),'idle scroll keeps fractional pixels alive')
  self.assertLess(max(distances)-min(distances),.0003)
 def test_fast_flick_travels_farther_without_frame_rate_dependent_acceleration(self):
  results=[]
  for fps in (15,30,60):
   distances=[]
   for duration in (.15,1.2):
    m=AirMouse();run(m,point(),0,acceleration=True);frames=max(2,round(duration*fps))
    for frame in range(1,frames+1):run(m,point(.06*frame/frames),duration*frame/frames,acceleration=True)
    for frame in range(1,round(.5*fps)+1):run(m,point(.06),duration+frame/fps,acceleration=True)
    distances.append(m.relative[0])
   self.assertGreater(distances[0],distances[1]*1.4)
   results.append(distances[0])
  self.assertLess((max(results)-min(results))/min(results),.02)
 def test_precision_drag_and_absolute_aim_do_not_accelerate(self):
  self.assertEqual(pointer_gain(1.5,.2),pointer_gain(1.5,0))
  self.assertEqual(pointer_gain(1.5,100,False),pointer_gain(1.5,0))
  self.assertLessEqual(pointer_gain(1.5,100),pointer_gain(1.5,0)*6)
  def replay(acceleration,absolute=False,drag=False):
   m=AirMouse();run(m,point(),0,acceleration=acceleration,positioning='absolute' if absolute else 'relative')
   if drag:run(m,pinch(),.05,acceleration=acceleration)
   for frame in range(1,7):run(m,(pinch if drag else point)(.06*frame/6),(.05 if drag else 0)+frame/60,acceleration=acceleration,positioning='absolute' if absolute else 'relative')
   return m.xy,m.relative
  self.assertEqual(replay(True,absolute=True),replay(False,absolute=True))
  self.assertEqual(replay(True,drag=True),replay(False,drag=True))
 def test_acceleration_setting_round_trips_and_can_be_disabled(self):
  self.assertFalse(settings()['mouse_acceleration']);self.assertFalse(settings({'mouse_acceleration':False})['mouse_acceleration']);self.assertTrue(settings({'mouse_acceleration':True})['mouse_acceleration'])
  r=HandRules();r.configure({'mode':'system_mouse','mouse_acceleration':False})
  r.update(point(),0,'Right');r.update(point(.06),.1,'Right');r.update(point(.06),.2,'Right')
  self.assertLess(r.mouse.relative[0],.127)
 def test_only_selected_hand_and_no_ordinary_actions(self):
  r=HandRules();r.configure({'mode':'mouse'})
  self.assertIsNone(r.update(point(),0,'Left'))
  out=r.update(point(),0,'Right');self.assertTrue(out)
  self.assertTrue(all(e[2]['action']=='pointer' for e in out))
  out=r.update(fist(),.1,'Right');self.assertEqual(out[0][2]['phase'],'cancel')
 def test_mode_change_cancels_pointer(self):
  r=HandRules();r.configure({'mode':'mouse'});r.update(point(),0,'Right');r.configure({'mode':'discrete'})
  self.assertTrue(any(e[2]['phase']=='cancel' for e in r.take_pending()))
 def test_payload_and_relay_guard_coordinates(self):
  r=Relay();p={'action':'pointer','phase':'move','x':.5,'y':.4};self.assertTrue(valid_pointer(p));r.publish_pointer(p)
  for change in ({'x':float('nan')},{'x':True},{'x':2},{'phase':'shell'},{'relative_x':1},{'relative_x':0,'relative_y':float('nan')},{'relative_x':True,'relative_y':0}):
   self.assertFalse(valid_pointer(p|change))
   with self.assertRaises(ValueError):r.publish_pointer(p|change)
if __name__=='__main__':unittest.main()
