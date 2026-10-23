"""Finite, displacement-proportional gesture deltas; no camera or input API."""
import math

CONTINUOUS_LIMITS = {'up': 3., 'down': 3., 'left': 20., 'right': 20.,
                     'volume_up': .3, 'volume_down': .3}


def valid_amount(action, amount):
    return (type(amount) in (int, float) and math.isfinite(amount)
            and 0 < amount <= CONTINUOUS_LIMITS.get(action, 0))


class ViewportDrag:
    """Touch-style vertical drag, expressed as absolute viewport displacement."""
    def __init__(self,hand):
        self.hand=hand;self.sequence=0;self.gesture_id=None;self.position=0.;self.pose=None

    def finish(self,phase='end'):
        if self.gesture_id is None:return None
        packet=self._packet(phase,self.position);self.gesture_id=None;self.position=0.;self.pose=None
        return packet

    def _packet(self,phase,position):
        return dict(action='drag_scroll',phase=phase,gesture_id=self.gesture_id,position=position)

    def move(self,pos,now,*,origin=None,span=.20,invert=1.,pose='grab'):
        """Start only after the caller confirms a deliberate vertical drag.

        The original grab anchor is retained, including motion during the short
        gesture confirmation. Returning to the anchor returns position to zero.
        """
        try:
            y=float(pos[1]);now=float(now)
            if not all(math.isfinite(v) for v in (y,now,span,invert)) or span<=0:raise ValueError()
            if self.gesture_id is None:
                anchor=float(origin[1])
                if not math.isfinite(anchor):raise ValueError()
        except (ValueError,TypeError,IndexError,OverflowError):
            packet=self.finish('cancel');return [packet] if packet else []
        packets=[]
        if self.gesture_id is None:
            self.sequence+=1;self.gesture_id=f'{self.hand}:{self.sequence}:{round(now*1e9)}'
            self.anchor=anchor;self.span=span;self.invert=invert;self.position=0.;self.pose=pose
            self.last_emit=now
            packets.append(self._packet('start',0.))
        position=max(-8.,min(8.,(self.anchor-y)/self.span*self.invert))
        # Only the emission is suppressed for sub-pixel jitter: the anchor and
        # total position never walk with camera FPS or accumulate rounding drift.
        if abs(position-self.position)>=.002 or now-self.last_emit>=.10:
            self.position=position;packets.append(self._packet('move',position))
            self.last_emit=now
        return packets


class AnalogDrag:
    """Measure deliberate travel, never time spent holding an offset.

    Every result is a small finite delta, never a latched scrolling command.
    Missing frames, release, pose changes and time discontinuities re-anchor.
    """
    def __init__(self,distance=.085,relative_floor=.28):
        self.distance=max(.04,min(.2,distance))
        self.relative_floor=relative_floor
        self.fallback_fired=False
        self.reset()

    def release(self):
        self.fallback_fired=False;self.reset()

    def reset(self):
        self.pose=None;self.origin=None;self.previous=None
        self.since=None;self.last=None;self.emitted=None;self.armed=False
        self.axis=None;self.direction=None;self.remainder=0.

    def update(self, pos, now, pose, norm=.2, speed=1.):
        try:
            now=float(now);pos=tuple(float(v) for v in pos)
            if (len(pos)!=2 or not all(math.isfinite(v) for v in (*pos,now,norm,speed))
                    or pose not in ('grab','corner')):raise ValueError()
        except (ValueError,TypeError,OverflowError):
            self.reset();return None
        if (self.pose!=pose or self.last is None or not 0 <= now-self.last <= .20
                or math.dist(pos,self.previous)>.35):
            self.reset();self.pose=pose;self.origin=pos;self.previous=pos
            self.since=self.last=self.emitted=now
            return None
        self.last=now
        if not self.armed:
            if pose=='corner' and math.dist(pos,self.origin)>max(.015,norm*.10):
                self.origin=pos;self.since=now
                self.previous=pos
                return None
            if now-self.since < (.25 if pose=='corner' else .08):return None
            self.armed=True
        if now-self.emitted<.045:return None
        dx,dy=pos[0]-self.previous[0],pos[1]-self.previous[1]
        if self.axis is None:
            if pose=='corner':self.axis=1
            elif max(abs(dx),abs(dy))>=.015 and max(abs(dx),abs(dy))>=min(abs(dx),abs(dy))*1.25:
                self.axis=1 if abs(dy)>=abs(dx) else 0
            else:return None
        delta=dy if self.axis else dx
        direction=('up' if delta<0 else 'down') if self.axis else ('left' if delta<0 else 'right')
        # Keep the accepted position while jittering, so slow deliberate travel
        # accumulates instead of disappearing between camera frames.
        dead=.018 if self.direction and direction!=self.direction else .007
        if abs(delta)<dead:return None
        if direction!=self.direction:self.remainder=0.
        self.direction=direction;self.previous=pos;self.emitted=now
        travel=abs(delta)*max(.25,min(2.,speed))
        step=max(.055 if pose=='corner' else self.distance,norm*self.relative_floor)
        self.remainder+=travel
        steps=min(4,int((self.remainder+1e-9)/step))
        self.remainder-=steps*step
        return direction,travel/step,steps


def command(action, distance_steps, steps):
    # Units are viewport heights, media seconds, and volume fractions.
    if (type(distance_steps) not in (int,float) or not math.isfinite(distance_steps)
            or distance_steps<=0 or type(steps) is not int or not 0<=steps<=4):return None
    units=(.7 if action in ('up','down') else 5. if action in ('left','right')
           else .05 if action in ('volume_up','volume_down') else 0.)
    amount=min(CONTINUOUS_LIMITS.get(action,0),distance_steps*units)
    return {'action':action,'amount':amount,'steps':steps,'continuous':True} if valid_amount(action,amount) else None
