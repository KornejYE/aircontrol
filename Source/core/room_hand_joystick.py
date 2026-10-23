"""A clutched hand stick. Pure geometry: no camera, game or system input."""
from __future__ import annotations

import math


def _number(value, default, low, high):
    return max(low, min(high, value)) if type(value) in (int, float) and math.isfinite(value) else default


def game_settings(value=None):
    value = value if isinstance(value, dict) else {}
    target = value.get('target', '')
    return dict(
        output=value.get('output') if value.get('output') in ('wasd', 'mouse') else 'preview',
        hand='Left' if value.get('hand') == 'Left' else 'Right',
        grip='pinch' if value.get('grip') == 'pinch' else 'fist',
        motion='translate' if value.get('motion') == 'translate' else 'tilt',
        tilt_degrees=_number(value.get('tilt_degrees'), 30., 10., 60.),
        radius=_number(value.get('radius'), 1.4, .6, 3.),
        deadzone=_number(value.get('deadzone'), .15, .05, .4),
        invert_y=value.get('invert_y') is True,
        mouse_range=_number(value.get('mouse_range'), .3, .1, .45),
        target=target if isinstance(target, str) and len(target) <= 256 and '\0' not in target else '',
    )


def valid_stick(packet):
    return (isinstance(packet, dict) and packet.get('action') == 'joystick'
            and packet.get('phase') in ('update', 'cancel')
            and type(packet.get('active')) is bool
            and (packet['phase'] != 'cancel' or not packet['active'])
            and all(type(packet.get(k)) in (int, float) and math.isfinite(packet[k])
                    and -1 <= packet[k] <= 1 for k in ('x', 'y'))
            and (packet['active'] or (packet['x'] == 0 and packet['y'] == 0)))


class HandJoystick:
    """Hold the chosen grip briefly to place neutral, release it to stop.

    Each new grip chooses a new neutral. Missing, stale or invalid input ends
    the grip immediately; no old displacement survives reacquisition.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.center = None
        self.since = None
        self.last = None
        self.xy = (0., 0.)
        self.radius = 1.
        self.state = 'idle'
        self.basis = None
        self.geometry_source = None

    def cancel(self, state='idle'):
        self.reset()
        self.state = state
        return dict(action='joystick', phase='cancel', active=False, x=0., y=0., state=state)

    def update(self, points, now, config=None):
        config = game_settings(config)
        try:
            points = list(points)
            p = [(float(v.x) * 16 / 9, float(v.y)) if hasattr(v, 'x')
                 else (float(v[0]) * 16 / 9, float(v[1])) for v in points]
            if len(p) != 21 or not all(math.isfinite(v) for xy in p for v in xy):
                raise ValueError('landmarks')
            world = [getattr(v, 'world', None) for v in points]
            if all(v is not None and len(v)==3 and all(math.isfinite(float(c)) for c in v) for v in world):
                geometry = [tuple(float(c) for c in v) for v in world]
                source = 'world'
            else:
                geometry = [(p[i][0], p[i][1], float(getattr(v,'z',0.)) * 16/9
                             if hasattr(v,'x') else float(v[2]) * 16/9 if len(v)>2 else 0.)
                            for i,v in enumerate(points)]
                source = 'normalized'
                if not all(math.isfinite(c) for v in geometry for c in v):raise ValueError('depth')
            if type(now) not in (int, float) or not math.isfinite(now):
                raise ValueError('clock')
        except (TypeError, ValueError, IndexError, AttributeError):
            return self.cancel('lost')
        if self.last is not None and not 0 < now - self.last <= .25:
            self.reset()
        if self.geometry_source is not None and self.geometry_source != source:self.reset()
        self.geometry_source = source
        dt = min(.08, now - self.last) if self.last is not None else .033
        self.last = now
        norm = max(.025, math.dist(p[5], p[17]), math.dist(p[0], p[9]) * .65)
        pinched = (math.dist(p[4], p[8]) < norm * (.50 if self.center else .34)
                   and math.dist(p[4], p[12]) > norm * .55)
        if config['grip']=='fist':
            folded, extended = finger_curls(geometry)
            engaged = (folded>=3 and extended==0) or (self.center is not None and folded>=2 and extended==0)
        else:engaged = pinched
        if not engaged:
            return self.cancel()
        palm = tuple(sum(p[i][axis] for i in (0, 5, 9, 13, 17)) / 5 for axis in (0, 1))
        lever = unit(tuple((geometry[5][a]+geometry[9][a]-geometry[0][a]-geometry[17][a])/2 for a in range(3)))
        if config['motion']=='tilt' and lever is None:return self.cancel('lost')
        if self.center is None:
            if self.since is None:
                self.since = now
            self.state = 'arming'
            if now - self.since < .18:
                return dict(action='joystick', phase='update', active=False, x=0., y=0., state=self.state)
            self.center = palm
            self.radius = norm * config['radius']
            self.xy = (0., 0.)
            if config['motion']=='tilt':
                # Two tangents to the neutral lever: screen-right and depth.
                # Whole-hand translation does not alter these angular axes.
                right = unit(tuple((1. if a==0 else 0.)-lever[a]*lever[0] for a in range(3)))
                if right is None:return self.cancel('lost')
                forward = (lever[1]*right[2]-lever[2]*right[1],
                           lever[2]*right[0]-lever[0]*right[2],
                           lever[0]*right[1]-lever[1]*right[0])
                if forward[2]<0:forward=tuple(-v for v in forward)
                self.basis = (lever,right,forward)
        if config['motion']=='tilt':
            normal,right,forward = self.basis
            reference = sum(a*b for a,b in zip(lever,normal))
            span = math.radians(config['tilt_degrees'])
            raw = tuple(math.atan2(sum(a*b for a,b in zip(lever,axis)),reference)/span for axis in (right,forward))
        else:raw = tuple((palm[i] - self.center[i]) / self.radius for i in (0, 1))
        magnitude = math.hypot(*raw)
        scale = (max(0., min(1., (magnitude - config['deadzone']) /
                              (1 - config['deadzone']))) ** 1.25 / magnitude) if magnitude else 0.
        desired = (raw[0] * scale, raw[1] * scale * (-1 if config['invert_y'] else 1))
        alpha = 1 - math.exp(-max(.001, dt) / .035)
        self.xy = tuple(a + (b - a) * alpha for a, b in zip(self.xy, desired))
        self.state = 'active'
        return dict(action='joystick', phase='update', active=True,
                    x=round(self.xy[0], 4), y=round(self.xy[1], 4), state=self.state)


def unit(vector):
    length=math.sqrt(sum(v*v for v in vector))
    return tuple(v/length for v in vector) if length>1e-6 else None


def finger_curls(points):
    """Rotation-invariant finger folding, including a fist seen edge-on."""
    folded=extended=0
    for base in (5,9,13,17):
        length=sum(math.dist(points[i],points[i+1]) for i in range(base,base+3))
        if length<1e-6:continue
        reach=math.dist(points[base],points[base+3])/length
        first=unit(tuple(points[base+1][a]-points[base][a] for a in range(3)))
        last=unit(tuple(points[base+3][a]-points[base+1][a] for a in range(3)))
        turn=sum(a*b for a,b in zip(first,last)) if first and last else 1.
        if reach<.76 or turn<.3:folded+=1
        elif reach>.88 and turn>.75:extended+=1
    return folded,extended
