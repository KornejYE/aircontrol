"""Two-finger aperture changes, normalized by palm size; no camera or input."""
import math


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
