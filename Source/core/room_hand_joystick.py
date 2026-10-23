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
    """Pinch briefly to place neutral, move the palm, release to stop.

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

    def cancel(self, state='idle'):
        self.reset()
        self.state = state
        return dict(action='joystick', phase='cancel', active=False, x=0., y=0., state=state)

    def update(self, points, now, config=None):
        config = game_settings(config)
        try:
            p = [(float(v.x) * 16 / 9, float(v.y)) if hasattr(v, 'x')
                 else (float(v[0]) * 16 / 9, float(v[1])) for v in points]
            if len(p) != 21 or not all(math.isfinite(v) for xy in p for v in xy):
                raise ValueError('landmarks')
            if type(now) not in (int, float) or not math.isfinite(now):
                raise ValueError('clock')
        except (TypeError, ValueError, IndexError, AttributeError):
            return self.cancel('lost')
        if self.last is not None and not 0 < now - self.last <= .25:
            self.reset()
        dt = min(.08, now - self.last) if self.last is not None else .033
        self.last = now
        norm = max(.025, math.dist(p[5], p[17]), math.dist(p[0], p[9]) * .65)
        # A fist does not engage: the middle fingertip must stay away from the
        # thumb. Hysteresis keeps a relaxed pinch stable after engagement.
        pinched = (math.dist(p[4], p[8]) < norm * (.50 if self.center else .34)
                   and math.dist(p[4], p[12]) > norm * .55)
        if not pinched:
            return self.cancel()
        palm = tuple(sum(p[i][axis] for i in (0, 5, 9, 13, 17)) / 5 for axis in (0, 1))
        if self.center is None:
            if self.since is None:
                self.since = now
            self.state = 'arming'
            if now - self.since < .18:
                return dict(action='joystick', phase='update', active=False, x=0., y=0., state=self.state)
            self.center = palm
            self.radius = norm * config['radius']
            self.xy = (0., 0.)
        raw = tuple((palm[i] - self.center[i]) / self.radius for i in (0, 1))
        magnitude = math.hypot(*raw)
        scale = (max(0., min(1., (magnitude - config['deadzone']) /
                              (1 - config['deadzone']))) ** 1.25 / magnitude) if magnitude else 0.
        desired = (raw[0] * scale, raw[1] * scale * (-1 if config['invert_y'] else 1))
        alpha = 1 - math.exp(-max(.001, dt) / .035)
        self.xy = tuple(a + (b - a) * alpha for a, b in zip(self.xy, desired))
        self.state = 'active'
        return dict(action='joystick', phase='update', active=True,
                    x=round(self.xy[0], 4), y=round(self.xy[1], 4), state=self.state)
