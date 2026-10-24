"""Two-finger aperture changes, normalized by palm size; no camera or input."""
import math

BIMANUAL_EVENTS = {'both_spread': 'Обе руки · развести захваты',
                   'both_close': 'Обе руки · сблизить захваты'}


class PinchZoom:
    def __init__(self):
        self.reset()

    def reset(self):
        self.sample = None
        self.last = -100.
        self.active = False

    def update(self, p, now):
        self.active = False
        if p is None:
            self.reset()
            return None
        norm = max(.025, math.dist(p[5], p[17]), math.dist(p[0], p[9])*.65)
        # A three-finger grip and an open palm keep their original meanings.
        folded = [math.dist(p[t], p[0]) < math.dist(p[t-2], p[0])*1.12
                  for t in (12, 16, 20)]
        gap = math.dist(p[4], p[8])/norm
        valid = (all(folded) and math.dist(p[4], p[12])/norm > .65
                 and .04 < gap < 2.8)
        if not valid:
            self.reset()
            return None
        centre = tuple(sum(p[i][a] for i in (0, 5, 9, 13, 17))/5 for a in (0, 1))
        old = self.sample
        if (old is None or now < old['time'] or now-old['time'] > .3
                or abs(norm/old['norm']-1) > .22
                or math.dist(centre, old['centre']) > norm*.5):
            self.sample = dict(time=now, since=now, norm=norm, centre=centre, gap=gap)
            return None
        old['time'] = now
        delta = gap-old['gap']
        # A stationary L also has two separated fingers. It must remain
        # available to the corner recognizer until aperture actually changes.
        self.active = abs(delta) >= .12
        if now-old['since'] < .08 or now-self.last < .28 or abs(delta) < .30:
            return None
        old['gap'] = gap
        self.last = now
        return 'spread' if delta > 0 else 'close'


class TwoHandZoom:
    """Frame-level two-grip clutch; only the selected right/left pair counts."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.engaged = self.consume = False
        self.waiting = set()
        self.absent = {}
        self.last = self.since = None
        self.identities = self.norms = None
        self.filtered = self.anchor = None
        self.last_emit = -100.
        self.feedback = ''

    @staticmethod
    def geometry(landmarks, held=False):
        try:
            p = [(float(v.x)*16/9, float(v.y)) if hasattr(v, 'x') else
                 (float(v[0])*16/9, float(v[1])) for v in landmarks]
            if len(p) != 21 or not all(math.isfinite(v) for xy in p for v in xy):
                return None
            norm = max(.025, math.dist(p[5], p[17]), math.dist(p[0], p[9])*.65)
            gap = math.dist(p[4], p[8])/norm
            reach = math.dist(p[8], p[5])/norm
            outward = sum((p[8][a]-p[5][a])*(p[5][a]-p[0][a]) for a in (0, 1))/norm**2
            tips = tuple(sum(p[i][a] for i in (4, 8, 12))/3 for a in (0, 1))
            triplet = max(math.dist(p[a], p[b]) for a,b in ((4,8),(4,12),(8,12)))/norm
            distinct = max(math.dist(p[i], tips) for i in (16,20))/norm > .35
            # The existing three-finger grab may curl toward the palm. Keep
            # accepting it, while a fist's four clustered fingertips stay idle.
            grip = gap < (.56 if held else .42) and (
                reach > .28 and outward > -.04 or triplet < (.75 if held else .60) and distinct)
            centre = tuple(sum(p[i][a] for i in (0, 5, 9, 13, 17))/5 for a in (0, 1))
            return dict(grip=grip, norm=norm, centre=centre)
        except (TypeError, ValueError, AttributeError, IndexError, OverflowError):
            return None

    def interrupt(self):
        if self.engaged:
            self.waiting = {'Right', 'Left'}
            self.absent = {}
        self.engaged = False
        self.consume = bool(self.waiting)
        self.feedback = 'Масштаб завершён · разожмите захват обеих рук'

    def update(self, tracked, now, *, identities=None, step=.12):
        hands = {side: self.geometry(p, self.engaged) for side, p in tracked if side in ('Right', 'Left')}
        hands = {side: value for side, value in hands.items() if value is not None}
        if type(now) not in (int, float) or not math.isfinite(now):
            self.interrupt()
            return []
        if self.waiting:
            for side in tuple(self.waiting):
                if side in hands:
                    self.absent.pop(side, None)
                    if not hands[side]['grip']:
                        self.waiting.remove(side)
                else:
                    self.absent.setdefault(side, now)
                    if now-self.absent[side] >= .35:
                        self.waiting.remove(side)
            # Consume the release frame too; it cannot finish an old click.
            self.consume = True
            return []
        both = len(hands) == 2 and all(h['grip'] for h in hands.values())
        if not both:
            if self.engaged:
                self.interrupt()
            else:
                self.consume = False
            return []
        norms = tuple(hands[s]['norm'] for s in ('Right', 'Left'))
        distance = math.dist(hands['Right']['centre'], hands['Left']['centre'])
        if distance < max(norms)*.8 or max(norms)/min(norms) > 2.5:
            if self.engaged:
                self.interrupt()
            return []
        pair = tuple((identities or {}).get(s) for s in ('Right', 'Left'))
        value = math.log(distance/math.sqrt(norms[0]*norms[1]))
        if self.engaged and (pair != self.identities or not 0 < now-self.last <= .25
                             or any(abs(a/b-1) > .35 for a, b in zip(norms, self.norms))):
            self.interrupt()
            return []
        self.consume = True
        if not self.engaged:
            self.engaged = True
            self.identities, self.norms = pair, norms
            self.last = self.since = now
            self.filtered = self.anchor = value
            self.feedback = 'Обе руки: держите захваты и разводите или сближайте кисти'
            return []
        dt = now-self.last
        self.last = now
        self.filtered += (1-math.exp(-dt/.04))*(value-self.filtered)
        if now-self.since < .12:
            self.anchor = self.filtered
            return []
        step = math.log1p(max(.06, min(.35, step)))
        delta = self.filtered-self.anchor
        count = int((abs(delta)+1e-9)/step)
        if not count or now-self.last_emit < .10:
            return []
        action = 'zoom_in' if delta > 0 else 'zoom_out'
        self.anchor += math.copysign(count*step, delta)
        self.last_emit = now
        self.feedback = 'Обе руки · '+('увеличение' if delta > 0 else 'уменьшение')
        return [action]*min(3, count)
