"""Local relative air-mouse state machine. No OS, camera, or network access."""
import math
import statistics
from collections import deque
POINTER_MODES=('mouse','system_mouse')
PHASES=('move','click','context','down','up','scroll','cancel')
def precision_factor(velocity):
 ramp=max(0.,min(1.,(velocity-.03)/.27))
 return .30+.70*ramp*ramp*(3-2*ramp)
def pointer_gain(speed,velocity,accelerated=True,precision=False):
 base=max(.5,min(3.,speed))*1.4
 if precision:base*=precision_factor(velocity)
 if not accelerated:return base
 ramp=max(0.,min(1.,(velocity-.65)/3.35))
 return base*(1+5*ramp*ramp*(3-2*ramp))
def accelerated_motion(start,target,filtered,velocity,dt,norm,speed,tau):
 # Integrate a linear camera sample at a small fixed time scale. Evaluating
 # acceleration only at the end of a 15-FPS frame over-amplifies fast flicks.
 steps=max(1,math.ceil(dt*120));h=dt/steps;direction=tuple((b-a)/dt for a,b in zip(start,target));motion=[0.,0.]
 for part in range(steps):
  raw=tuple(a+v*h*part for a,v in zip(start,direction));end=tuple(a+v*h for a,v in zip(raw,direction))
  following=tuple(b-v*tau+(f-a+v*tau)*math.exp(-h/tau) for a,b,f,v in zip(raw,end,filtered,direction))
  delta=tuple(b-a for a,b in zip(filtered,following));instant=math.hypot(*delta)/(h*norm)
  following_velocity=velocity+(1-math.exp(-h/.035))*(instant-velocity)
  gain=pointer_gain(speed,(velocity+following_velocity)/2)
  motion=[a+d*gain for a,d in zip(motion,delta)];filtered=following;velocity=following_velocity
 return filtered,velocity,motion

class AimHold:
 """Soft positional tether: estimate noise around a local straight stroke.

 Residuals, rather than total speed, distinguish landmark wobble from a slow
 consistent movement. Never round per-frame deltas or accumulate a release
 jump: only travel beyond the tether is emitted.
 """
 def __init__(self):self.reset()
 def reset(self):self.samples=deque(maxlen=24);self.position=None;self.noise=0.
 def update(self,point,now,norm,filtered=None):
  if self.position is None:self.position=point
  dt=now-self.samples[-1][0] if self.samples else 0.
  self.samples.append((now,point))
  while len(self.samples)>5 and now-self.samples[0][0]>.24:self.samples.popleft()
  samples=list(self.samples);innovations=[]
  for (ta,a),(tb,b),(tc,c) in zip(samples,samples[1:],samples[2:]):
   fraction=(tb-ta)/(tc-ta) if tc>ta else .5
   innovations.append(math.dist(b,tuple(x+(y-x)*fraction for x,y in zip(a,c))))
  # The median of short, local interpolation errors rejects a real turn or
  # stop. A least-squares residual over the whole stroke would call that noise.
  residual=statistics.median(innovations) if len(samples)>=5 else 0.
  prior_noise=self.noise*math.exp(-max(0.,dt)/.5)
  self.noise=max(residual,prior_noise)
  target=point if filtered is None else filtered
  distance=math.dist(target,self.position)
  # Apply the tether AFTER smoothing. Gating raw points would either let their
  # noise move the anchor or suppress real slow motion hidden inside that noise.
  radius=max(norm*.0002,min(norm*.015,self.noise*1.8))
  if distance>radius:self.position=tuple(a+(b-a)*(1-radius/distance) for a,b in zip(self.position,target))
  return self.position
def valid_pointer(data):
 return (data.get('action')=='pointer' and data.get('phase') in PHASES
         and all(type(data.get(k)) in (int,float) and math.isfinite(data[k]) and 0<=data[k]<=1 for k in ('x','y'))
         and (data.get('phase')!='scroll' or 'dy' in data)
         and ('absolute' not in data or type(data['absolute']) is bool)
         and (not any(k in data for k in ('relative_x','relative_y')) or all(type(data.get(k)) in (int,float) and math.isfinite(data[k]) and abs(data[k])<=1e6 for k in ('relative_x','relative_y')))
         and ('dy' not in data or (data['phase']=='scroll' and type(data['dy']) in (int,float) and math.isfinite(data['dy']) and abs(data['dy'])<=1)))

class AirMouse:
 def __init__(self):
  self.aim_hold=AimHold()
  self.relative=[0.,0.];self.candidate=None;self.candidate_since=0.
  self.velocity=0.;self.scroll_pending=0.;self.scroll_lock=False
  self.trend=(0.,0.);self.precision_trend=(0.,0.)
  self.missing_since=None;self.diagnostics=dict(missing_frames=0,recoveries=0,tracking_resets=0,time_gaps=0,fist_stops=0)
  self.absolute=False;self.point_ready=False;self.pinch_allowed=False;self.filtered=None;self.xy=[.5,.5];self.last=None;self.last_emit=-1.;self.pose=None;self.previous=None;self.since=0.;self.anchor=None;self.down=False;self.context_fired=False
 def packet(self,phase,**extra):return dict(action='pointer',phase=phase,x=self.xy[0],y=self.xy[1],relative_x=self.relative[0],relative_y=self.relative[1],absolute=self.absolute,**extra)
 def cancel(self):
  self.aim_hold.reset()
  self.precision_trend=(0.,0.)
  active=self.pose not in (None,'idle','fist') or self.down
  self.point_ready=False;self.pinch_allowed=False;self.filtered=None;self.down=False;self.pose=None;self.previous=None;self.anchor=None;self.last=None;self.context_fired=False;self.candidate=None;self.velocity=0.;self.trend=(0.,0.);self.scroll_pending=0.;self.scroll_lock=False;self.missing_since=None
  return [self.packet('cancel')] if active else []
 def tracking_snapshot(self):
  return dict(self.diagnostics,pose=self.pose or 'none',recovering=self.missing_since is not None)
 def missing(self,now):
  self.diagnostics['missing_frames']+=1
  self.precision_trend=(0.,0.)
  self.point_ready=False;self.pinch_allowed=False;self.velocity=0.
  # Never extrapolate invisible landmarks or keep a mouse button held. Only
  # free aiming/scrolling may bridge a brief detector miss at a fixed position.
  if self.down or self.pose not in ('point','scroll','scroll_grab') or self.last is None or not 0<=now-self.last<=.18:
   if self.pose not in (None,'idle','fist'):self.diagnostics['tracking_resets']+=1
   return self.cancel()
  if self.missing_since is None:self.missing_since=now
  self.scroll_lock=True
  self.last_emit=now
  return [self.packet('scroll',dy=0.) if self.pose in ('scroll','scroll_grab') else self.packet('move')]
 def update(self,p,now,*,speed=1.5,flags=None,norm=.2,positioning='relative',acceleration=False,precision=False,area=None):
  try:
   if not math.isfinite(now):raise ValueError()
   if p is None:return self.missing(now)
   if len(p)!=21 or not all(math.isfinite(v) for xy in p for v in xy):raise ValueError()
   recovered=self.missing_since is not None
   if self.last is not None and not 0<=now-self.last<=(.25 if recovered else .20):
    self.diagnostics['time_gaps']+=1
    packets=self.cancel()
    return packets+self.update(p,now,speed=speed,flags=flags,norm=norm,positioning=positioning,acceleration=acceleration,precision=precision,area=area)
   from core.room_pointer_area import pointer_area,map_point
   area=pointer_area(area)
   self.absolute=positioning=='absolute'
   flags=flags or {};norm=max(.025,norm)
   extended=[math.dist(p[t],p[0])>math.dist(p[t-2],p[0])*1.12 for t in (8,12,16,20)]
   pinch=math.dist(p[4],p[8])/norm
   reach=math.dist(p[8],p[5])/norm
   outward=sum((p[8][a]-p[5][a])*(p[5][a]-p[0][a]) for a in (0,1))/norm**2
   thumb_open=math.dist(p[4],p[5])>norm*.60 and math.dist(p[4],p[2])>norm*.40
   # Continuity of a bent pointing hand is separate from permission to click.
   # A detector miss revokes click arming, not the known relaxed hand shape.
   relaxed=(thumb_open or self.point_ready or self.pose=='point') and outward>.08 and reach>.28
   middle_reach=math.dist(p[12],p[9])/norm
   middle_outward=sum((p[12][a]-p[9][a])*(p[9][a]-p[0][a]) for a in (0,1))/norm**2
   triplet=max(math.dist(p[a],p[b]) for a,b in ((4,8),(4,12),(8,12)))/norm
   scroll_grab=(triplet<(.52 if self.pose=='scroll_grab' else .40)
    and (extended[0] or reach>.28 and outward>-.02)
    and (extended[1] or middle_reach>.28 and middle_outward>-.02))
   context=math.dist(p[4],p[12])/norm<.28 and pinch>.5 and extended[0]
   # A click bends the index: the radial finger test alone often calls that a fist.
   # A real fist keeps the index tip close to its knuckle, unlike a forward pinch.
   pinching=pinch<(.42 if self.pose=='pinch' else .26) and (extended[0] or
    (self.point_ready or self.scroll_lock) and reach>.28 and outward>-.02 and math.dist(p[8],p[0])>math.dist(p[5],p[0])*.96)
   pose=('scroll_grab' if scroll_grab else 'pinch' if pinching else 'fist' if flags.get('fist') and not relaxed and not thumb_open
         else 'context' if context else 'scroll' if all(extended[:2]) and not any(extended[2:])
         else 'point' if extended[0] or relaxed or thumb_open else 'idle')
   # Brief changes in the estimated pose must not clutch/rebase a moving pointer.
   # Fist and pinch remain immediate; scroll/menu/idle need a stable pose.
   if self.pose=='point' and pose in ('idle','scroll','scroll_grab','context'):
    if self.candidate!=pose:self.candidate=pose;self.candidate_since=now
    if now-self.candidate_since<.10:pose='point'
   else:self.candidate=None
   # Average several rigid knuckles before extending the wrist axis. A single
   # noisy index-MCP landmark must not be amplified 1.8 times on its own.
   # Finger-tip articulation still cannot steer relative aiming.
   pos=(tuple(sum(p[i][a] for i in (0,5,9,13,17))/5 for a in (0,1)) if pose in ('pinch','scroll_grab')
        else tuple((p[6][a]+p[10][a])/2 for a in (0,1)) if pose=='scroll'
        else p[8] if self.absolute else tuple(1.8*sum(p[i][a] for i in (5,9,13))/3-.8*p[0][a] for a in (0,1)))
   packets=[];dt=max(.001,min(.2,now-self.last)) if self.last is not None else 1/30;self.last=now
   if pose in ('idle','fist'):
    self.aim_hold.reset()
    self.precision_trend=(0.,0.)
    if pose=='fist' and self.pose not in (None,'idle','fist'):self.diagnostics['fist_stops']+=1
    if self.pose not in (None,'idle','fist') or self.down:packets.append(self.packet('cancel',reason=pose))
    self.point_ready=False;self.pinch_allowed=False;self.down=False;self.pose=pose;self.previous=None;self.anchor=None;self.velocity=0.;self.trend=(0.,0.);self.scroll_pending=0.;self.scroll_lock=False;self.missing_since=None;return packets
   if not recovered and pose=='point' and self.scroll_lock and pinch>.65:self.scroll_lock=False;self.point_ready=True
   if recovered:
    self.missing_since=None;self.diagnostics['recoveries']+=1
    self.velocity=0.;self.trend=(0.,0.)
    # Only a nearby, newly OBSERVED position may continue a stroke. Preserve
    # its measured travel through the filter: rebasing on every return made
    # alternating valid/missing frames discard all motion. During misses the
    # cursor stays fixed; distant returns are still rebased without a jump.
    nearby=self.previous is not None and math.dist(pos,self.previous)<=max(.025,min(.10,norm*.5))
    if pose!=self.pose or not nearby:
     self.aim_hold.reset()
     self.precision_trend=(0.,0.)
     self.previous=pos;self.filtered=pos;self.anchor=pos;self.scroll_pending=0.
     if pose==self.pose:
      packets.append(self.packet('scroll',dy=0.) if pose in ('scroll','scroll_grab') else self.packet('move'))
      self.last_emit=now;return packets
   # A bent/closing finger is still free aiming. Only real contact may clutch
   # the pointer; anticipating a click used to freeze natural relaxed poses.
   if self.pose!=pose:
    self.aim_hold.reset()
    self.precision_trend=(0.,0.)
    if pose=='point' and not self.absolute:self.aim_hold.update(pos,now,norm)
    releasing=self.pose=='pinch'
    if self.pose=='pinch':
     if self.down:packets.append(self.packet('up'));self.down=False
     elif pose=='point' and self.pinch_allowed and now-self.since>=.04:packets.append(self.packet('click'))
    if pose=='pinch':self.pinch_allowed=self.point_ready
    if pose in ('scroll','scroll_grab'):self.point_ready=False;self.pinch_allowed=False;self.scroll_lock=True
    if pose=='point':
     self.point_ready=not self.scroll_lock
     if self.absolute and not releasing:self.xy=map_point(pos,area)
    self.pose=pose;self.since=now;self.previous=pos;self.filtered=pos;self.anchor=pos;self.context_fired=False;self.velocity=0.;self.trend=(0.,0.);self.scroll_pending=0.
    packets.append(self.packet('move'));self.last_emit=now;return packets
   dx,dy=pos[0]-self.previous[0],pos[1]-self.previous[1]
   if math.hypot(dx,dy)>.22:return self.cancel()
   previous=self.previous;self.previous=pos
   # Smooth coordinates before estimating speed, so tracker jitter is not
   # amplified. Velocity is in palm widths/second rather than pixels/frame.
   # A signed vector trend cancels alternating tracker noise. Raw frame speed
   # used to treat that noise as intentional fast motion and weaken damping.
   blend=1-math.exp(-dt/.065)
   self.trend=tuple(a+blend*(b/dt-a) for a,b in zip(self.trend,(dx,dy)))
   velocity=math.hypot(*self.trend)
   tau=.012+.085*math.exp(-velocity/.08)
   if pose=='point' and acceleration and not self.absolute:
    # Keep the opt-in speed curve's calibrated integration across frame rates.
    tau=.025+.030*math.exp(-math.hypot(dx,dy)/dt/.5)
   alpha=1-math.exp(-dt/tau)
   accelerated=None
   if pose=='point' and acceleration and not self.absolute:
    filtered,self.velocity,accelerated=accelerated_motion(previous,pos,self.filtered or previous,self.velocity,dt,norm,speed,tau)
   else:filtered=tuple(a+alpha*(b-a) for a,b in zip(self.filtered or pos,pos))
   dx,dy=filtered[0]-(self.filtered or pos)[0],filtered[1]-(self.filtered or pos)[1]
   self.filtered=filtered
   precision_speed=0.
   if pose=='point' and not self.absolute:
    prior=self.aim_hold.position or filtered
    stable=self.aim_hold.update(pos,now,norm,filtered)
    if accelerated is not None:
     distance2=dx*dx+dy*dy
     integrated_gain=sum(a*b for a,b in zip(accelerated,(dx,dy)))/distance2 if distance2>1e-18 else pointer_gain(speed,self.velocity)
     accelerated=tuple((b-a)*integrated_gain for a,b in zip(prior,stable))
    dx,dy=tuple(b-a for a,b in zip(prior,stable))
    blend=1-math.exp(-dt/.12)
    self.precision_trend=tuple(a+blend*(b/dt-a) for a,b in zip(self.precision_trend,(dx,dy)))
    precision_speed=math.hypot(*self.precision_trend)/norm
    if accelerated is not None and precision:accelerated=tuple(v*precision_factor(precision_speed) for v in accelerated)
   if pose=='context':
    if not self.context_fired and now-self.since>=.12:packets.append(self.packet('context'));self.context_fired=True
   elif pose in ('scroll','scroll_grab'):
    self.scroll_pending=max(-1.,min(1.,self.scroll_pending-dy*3.))
    if now-self.since>=.08 and abs(self.scroll_pending)>=.0001:
     packets.append(self.packet('scroll',dy=self.scroll_pending));self.scroll_pending=0.;self.last_emit=now
    elif now-self.last_emit>=.08:packets.append(self.packet('scroll',dy=0.));self.last_emit=now
   else:
    if pose=='pinch' and not self.down:
     if not self.pinch_allowed or now-self.since<.10 or math.dist(pos,self.anchor)<.025:
      self.filtered=pos
      if now-self.last_emit>=.08:packets.append(self.packet('move'));self.last_emit=now
      return packets
     self.down=True;packets.append(self.packet('down'))
    gain=pointer_gain(speed,precision_speed,False,precision and pose=='point' and not self.absolute)
    if pose=='point' or self.down:
     motion=accelerated if accelerated is not None else (dx/(area[2]-area[0]),dy/(area[3]-area[1])) if self.absolute else (dx*gain,dy*gain)
     self.xy=(map_point(filtered,area) if self.absolute and pose=='point' else [max(0.,min(1.,self.xy[a]+motion[a])) for a in (0,1)])
     if not self.absolute:self.relative=[self.relative[a]+motion[a] for a in (0,1)]
    # Even small deliberate movements need one output per detected frame.
    # The former threshold bunched slow travel into 80-ms stair steps.
    if math.hypot(dx,dy)>1e-9 or now-self.last_emit>=.08:
     packets.append(self.packet('move'));self.last_emit=now
   return packets
  except (ValueError,TypeError,IndexError,OverflowError):return self.cancel()
