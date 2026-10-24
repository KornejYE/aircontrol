"""Two-hand identity and corner/zoom arbitration without camera or media actions."""
import sys,runpy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_hand_tracks import HandTracks,CONNECTIONS
from core.room_gesture_rules import HandRules,settings
from core.room_gesture_zoom import PinchZoom
base=runpy.run_path(str(Path(__file__).with_name('test-corner-geometry.py')))
corner,shifted=base['corner'],base['shifted']
left=shifted(corner,x=-.2);right=shifted(corner,x=.2)
t=HandTracks()
assert t.update([(left,'Left',.99)],0)[0][0]=='Left'
# Several people can have real hands of the same side; do not invent a Right.
assert [h for h,_ in t.update([(left,'Left',.99),(right,'Left',.70)],.1)]==['Left']
assert len(t.visible)==2
# Once both physical hands were correctly seen, transient label flips are ignored.
t=HandTracks();t.update([(right,'Right',.98),(left,'Left',.98)],0)
assert [h for h,_ in t.update([(left,'Left',.99),(right,'Left',.70)],.1)]==['Right','Left']
assert [h for h,_ in t.update([(right,'Right',.98),(left,'Left',.98)],.2)]==['Right','Left']
assert t.update([(right,'Left',.75)],.3)[0][0]=='Right'
t.update([],1.)
assert t.update([(left,'Right',.99)],1.1)[0][0]=='Right','old track must expire'
# Pointer-only locks preserve the established side through a sustained model
# relabel; normal mode still performs the original delayed correction.
for locked in (False,True):
 t=HandTracks();t.update([(right,'Right',.99)],0)
 original=t.visible[0].identity
 if locked:assert t.lock_side('Right')
 assert t.update([(right,'Left',.99)],.1)[0][0]=='Right'
 if not locked:t.clear_locks()
 result=t.update([(right,'Left',.99)],.4)
 assert result[0][0]==('Right' if locked else 'Left')
 assert t.visible[0].identity==original
 if locked:
  t.clear_locks()
  assert t.update([(right,'Left',.99)],.5)[0][0]=='Right'
  assert t.update([(right,'Left',.99)],.8)[0][0]=='Left','unlock must restore delayed relabel correction'
# A sustained confident correction must recover even when the worker renews
# the pointer lock every frame. Brief label glitches remain absorbed above.
t=HandTracks();t.update([(right,'Right',.99)],0);assert t.lock_side('Right')
for now in (.1,.3,.6,.9):
 assert t.update([(right,'Left',.99)],now)[0][0]=='Right'
 assert t.lock_side('Right')
assert t.update([(right,'Left',.99)],1.11)[0][0]=='Left'
# Replacing a disappeared right hand with a left at the same location must
# not inherit the earlier physical identity or its anatomical side lock.
t=HandTracks();t.update([(right,'Right',.99)],0);original=t.visible[0].identity
assert t.lock_side('Right');t.update([],.1)
assert not t.lock_side('Right')
assert t.update([(right,'Left',.99)],.2)[0][0]=='Left'
assert t.visible[0].identity!=original
# Expired physical identities cannot pass their lock to a new detection.
t=HandTracks();assert not t.lock_side('Right');assert not t.lock_side('invalid')
t.update([(right,'Right',.99)],0);original=t.visible[0].identity;assert t.lock_side('Right')
t.update([],.6);assert t._side_locks=={}
assert t.update([(right,'Left',.99)],.61)[0][0]=='Left'
assert t.visible[0].identity!=original
# A side lock never reserves controller ownership against a larger real hand.
t=HandTracks();t.update([(right,'Right',.99)],0);original=t.visible[0].identity;assert t.lock_side('Right')
bigger=[(.3+(x-.5)*1.4,y) for x,y in corner]
result=t.update([(right,'Right',.99),(bigger,'Right',.99)],.1)
assert result[0][1] is bigger
assert t.selected_ids['Right']!=original and 'Right' in t.changed
assert set(i for edge in CONNECTIONS for i in edge)==set(range(21))
# Both zoom and corner are bound, as in the actual user settings.
c=settings();c['rules']['Left'].update(zoom_spread='zoom_in',zoom_close='zoom_out')
r=HandRules();r.configure(c)
events=[v for p,now in [(corner,0),(corner,.1),(corner,.28),(shifted(corner,y=-.12),.4)] if (v:=r.update(p,now,'Left'))]
assert [(side,gesture,action.get('action') if isinstance(action,dict) else action) for side,gesture,action in events]==[('Left','corner_up','volume_up')],events
# Pinch aperture changes produce zoom; an unmoving two-finger hand does not own input.
p=list(corner)
for tip in (12,16,20):p[tip]=p[tip-2]
p[4]=(.27,.25)
z=PinchZoom();z.update(p,0);z.update(p,.1);assert not z.active
wide=list(p);wide[4]=(.12,.25)
assert z.update(wide,.2)=='spread'
assert z.update(p,.49)=='close'
print('PASS: duplicate labels, changing detection order, second hand, expired tracks, optional side lock/unlock/expiry, larger-controller takeover, all 21 landmarks, corner with zoom enabled, spread/close.')
