"""Replay L poses and tracking interruptions; never access a camera/media API."""
import math
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_gesture_rules import HandRules,poses,settings

# Bent fingers aimed partly toward the camera: their tips are beyond their
# PIP joints relative to the wrist despite the visible bend at DIP/PIP.
corner=[(.50,.82),(.43,.74),(.36,.66),(.28,.63),(.18,.61),
        (.43,.59),(.43,.45),(.43,.33),(.43,.23),
        (.50,.59),(.52,.50),(.54,.43),(.52,.44),
        (.57,.61),(.59,.52),(.62,.46),(.59,.47),
        (.63,.65),(.65,.56),(.68,.52),(.65,.53)]

def shifted(p,x=0,y=0):return [(a+x,b+y) for a,b in p]
def transformed(p,angle=0,scale=1,mirror=1):
 c,s=math.cos(angle),math.sin(angle)
 return [(.5+scale*((x-.5)*mirror*c-(y-.5)*s),
          .5+scale*((x-.5)*mirror*s+(y-.5)*c)) for x,y in p]
def events(trace,hand='Left',config=None):
 r=HandRules()
 if config:r.configure(config)
 result=[v for p,t in trace if (v:=r.update(p,t,hand))]
 return r,result

# This natural foreshortened pose was rejected by the old all-curled test.
assert any(math.dist(corner[t],corner[0])>=math.dist(corner[t-2],corner[0])*1.12 for t in (12,16,20))
count=0
for angle in (-1.1,-.5,0,.5,1.1):
 for scale in (.65,1.,1.3):
  for mirror in (-1,1):
   p=transformed(corner,angle,scale,mirror)
   assert poses(p)[1]['corner'],(angle,scale,mirror)
   r,out=events([(p,0),(p,.1),(p,.27),(shifted(p,y=-.12),.37)])
   assert [v[2]['action'] for v in out]==['volume_up'],(angle,scale,mirror,out)
   count+=1

# A pause to arm is still required, so merely waving an L cannot change sound.
_,out=events([(shifted(corner,x=i*.035),i*.05) for i in range(9)])
assert out==[]
point=list(corner);point[4]=(.43,.64);point[3]=(.42,.68)
two_fingers=list(corner)
two_fingers[10:13]=[(.50,.44),(.50,.32),(.50,.20)]
fist=list(corner);fist[8]=(.44,.65)
for p in (point,two_fingers,fist):
 assert not poses(p)[1]['corner']
 _,out=events([(p,0),(p,.3),(shifted(p,y=-.15),.4)])
 assert out==[]

# One uncertain frame during a valid L neither fires nor restarts the hold.
uncertain=list(corner);uncertain[8]=(.44,.65)
r,out=events([(corner,0),(corner,.1),(uncertain,.13),(corner,.20),
              (corner,.28),(shifted(corner,y=-.12),.38)])
assert [v[2]['action'] for v in out]==['volume_up']
assert r.feedback['corner_armed']

# A longer loss requires a new stable pose and discards motion while unseen.
r,out=events([(corner,0),(corner,.26),(None,.29),(None,.40),
              (shifted(corner,y=-.12),.43),(shifted(corner,y=-.12),.70)])
assert out==[]
assert r.update(shifted(corner,y=-.24),.80,'Left')[2]['action']=='volume_up'

# Tracking resumes safely after a late false pose, hand changes and calibration.
r,out=events([(corner,0),(corner,.27),(uncertain,.3),(uncertain,.44),
              (shifted(corner,y=-.12),.48)])
assert out==[] and 'зафиксируйте' in r.feedback['phase']
r=HandRules();r.update(corner,0,'Left');r.update(corner,.27,'Left')
assert r.update(shifted(corner,y=-.12),.37,'Right') is None
assert r.update(shifted(corner,y=-.12),.38,'Left',allow_actions=False) is None
assert r.update(shifted(corner,y=-.24),.40,'Left') is None

# Explicit feedback distinguishes candidate, rejected, stabilizing and ready.
r=HandRules();r.update(point,0,'Left')
assert 'Отведите большой палец' in r.feedback['phase']
r.update(corner,.1,'Left');assert 'обнаружен' in r.feedback['phase']
r.update(corner,.2,'Left');assert 0<r.feedback['corner_progress']<1
r.update(corner,.37,'Left');assert r.feedback['corner_armed']

c=settings();c['swap_hands']=True
_,out=events([(corner,0),(corner,.27),(shifted(corner,y=.12),.37)],hand='Right',config=c)
assert len(out)==1 and out[0][:2]==('Left','corner_down') and out[0][2]['action']=='volume_down'
print(f'PASS: {count} rotated/scaled/mirrored L replays; curl ambiguity, hold, short/long tracking loss, hand isolation, calibration, feedback and swap. No camera or media keys used.')
