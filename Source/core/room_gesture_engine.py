"""Local grab/drag and stationary-palm media gestures; no camera or network."""
import math

PALM_HOLD_SECONDS = 1.0
PALM_TRACKING_GRACE = .16


class GestureEngine:
    def __init__(self, hold=.08, distance=.085, cooldown=.8, profile=None, relative_floor=.28):
        self.profile = profile or {}
        self.hold = hold
        self.distance = distance
        self.relative_floor = relative_floor
        self.cooldown = cooldown
        self.last_event = -100.
        self.feedback = {}
        self._needs_grab_release = False
        self._media_wait_release = False
        self._media_absent_since = None
        self.reset()

    def _cancel_drag(self):
        self.start = None
        self.origin = None
        self.previous = None
        self.fired = False

    def reset(self):
        # Preserve release latches: a tracking glitch must not repeat an action.
        self._cancel_drag()
        self.armed = False
        self.hand = None
        self._have_hand = False
        self._last_frame = None
        self._media_start = None
        self._media_points = None
        self._media_last_valid = None
        self._media_gap = False
        self._media_absent_since = None

    def require_media_release(self):
        """After a palm action/calibration, require a lowered or absent hand."""
        self._media_wait_release = True
        self._media_start = None
        self._media_points = None
        self._media_last_valid = None
        self._media_gap = False
        self._media_absent_since = None

    def _palm_event(self, p, now, norm, allow_media):
        centre = tuple(sum(p[i][a] for i in (0, 5, 9, 13, 17))/5 for a in (0, 1))
        if not allow_media:
            self.require_media_release()
            return None, False, 0.
        # Lowering the hand is deliberate rearming, not an ordinary finger release.
        if centre[1] > .80:
            self._media_wait_release = False
            self._media_start = None
            self._media_points = None
            self._media_last_valid = None
            self._media_gap = False
            return None, False, 0.
        extended = []
        for base in (5, 9, 13, 17):
            length = sum(math.dist(p[i], p[i+1]) for i in range(base, base+3))
            extended.append(
                math.dist(p[base], p[base+3]) > norm*.45
                and math.dist(p[base+3], p[0]) > math.dist(p[base+1], p[0])*1.04
                and math.dist(p[base], p[base+3])/max(.01, length) > .75)
        palm = (all(extended) and math.dist(p[5], p[17]) > .04
                and math.dist(p[8], p[20]) > norm*.40)
        if not palm or self._media_wait_release:
            if (not self._media_wait_release and self._media_last_valid is not None
                    and 0 <= now-self._media_last_valid <= PALM_TRACKING_GRACE):
                self._media_gap = True
                return None, palm, 0.
            self._media_start = None
            self._media_points = None
            self._media_last_valid = None
            self._media_gap = False
            return None, palm, 0.
        sample = tuple(p[i] for i in (0, 5, 9, 13, 17))
        if self._media_gap and self._media_start is not None:
            gap = now-self._media_last_valid
            if 0 <= gap <= PALM_TRACKING_GRACE:
                # Unknown frames do not count toward the one-second hold.
                self._media_start += gap
            else:
                self._media_start = None
        if (self._media_start is None
                or max(math.dist(a, b) for a, b in zip(sample, self._media_points)) > max(.018, norm*.18)):
            self._media_start = now
            self._media_points = sample
        self._media_last_valid = now
        self._media_gap = False
        progress = min(1., max(0., (now-self._media_start+1e-9)/PALM_HOLD_SECONDS))
        if progress < 1.:
            return None, palm, progress
        self.require_media_release()
        self.last_event = now
        return 'play_pause', palm, 1.

    def update(self, landmarks, now, hand='hand', allow_media=True):
        try:
            now = float(now)
            count = len(landmarks) if landmarks is not None else 0
            if not math.isfinite(now):
                raise ValueError('timestamp')
        except (TypeError, ValueError, OverflowError):
            self.reset(); self.require_media_release(); self.feedback = {'hand': False}
            return None
        if count == 0:
            absent = self._media_absent_since
            keep_palm = (allow_media and not self._media_wait_release
                         and self._media_last_valid is not None
                         and 0 <= now-self._media_last_valid <= PALM_TRACKING_GRACE)
            hold = (self._media_start, self._media_points, self._media_last_valid,
                    self.hand, self._last_frame)
            self.reset()
            if keep_palm:
                (self._media_start, self._media_points, self._media_last_valid,
                 self.hand, self._last_frame) = hold
                self._have_hand = True
                self._media_gap = True
            self._media_absent_since = now if absent is None else absent
            if allow_media and now-self._media_absent_since >= .35:
                self._media_wait_release = False
            elif not allow_media:
                self.require_media_release()
            self.feedback = {'hand': False}
            return None
        try:
            if count != 21:
                raise ValueError('landmarks')
            p = [(float(v.x), float(v.y)) if hasattr(v, 'x') else (float(v[0]), float(v[1])) for v in landmarks]
            if not all(math.isfinite(v) for xy in p for v in xy):
                raise ValueError('landmarks')
        except (AttributeError, TypeError, ValueError, IndexError, OverflowError):
            self.reset(); self.require_media_release(); self.feedback = {'hand': False}
            return None
        if self._have_hand and (hand != self.hand or now < self._last_frame or now-self._last_frame > .5):
            self.reset(); self.require_media_release(); self.feedback = {'hand': True, 'phase': 'Покажите руку снова'}
            return None
        self._have_hand = True
        self.hand = hand
        self._last_frame = now
        self._media_absent_since = None
        norm = max(math.dist(p[5], p[17]), math.dist(p[0], p[9])*.65, .025)
        index = math.dist(p[4], p[8])/norm
        middle = math.dist(p[4], p[12])/norm
        flex = max(math.dist(p[tip], p[0])/max(.01, math.dist(p[pip], p[0])) for tip, pip in ((8,6),(12,10)))
        curled = flex < self.profile.get('curl_limit', 1.05)
        closed = index < self.profile.get('index_limit', .9) and middle < self.profile.get('middle_limit', 1.1) and curled
        opened = (index > self.profile.get('open_index', 1.05)
                  or middle > self.profile.get('open_middle', 1.2)
                  or (not curled and (index > .92 or middle > 1.06)))
        event, palm, progress = self._palm_event(p, now, norm, allow_media)
        phase = ('Разожмите пальцы для следующего свайпа' if self._needs_grab_release
                 else 'Потяните руку' if self.start is not None else 'Сомкните три пальца и потяните')
        if palm and not self._media_wait_release:
            phase = f'Ладонь: держите неподвижно 1 с · {round(progress*100)}%'
        elif palm and self._media_wait_release:
            phase = 'Для ладони-паузы сначала опустите руку'
        self.feedback = dict(hand=True, grip=closed, grip_open=opened, armed=self.armed, palm=palm,
                             media_wait_release=self._media_wait_release, media_progress=round(progress,2),
                             index=round(index,2), middle=round(middle,2), flex=round(flex,2), phase=phase)
        if event:
            self._cancel_drag(); self.armed = False
            self.feedback['phase'] = 'Пауза / воспроизведение. Опустите руку для повтора'
            return event
        pos = tuple(sum(p[i][a] for i in (4,8,12))/3 for a in (0,1))
        if opened:
            self._cancel_drag(); self._needs_grab_release = False; self.armed = True
            self.feedback['armed'] = True
            return None
        if not closed:
            self._cancel_drag()
            return None
        if self._needs_grab_release or self.fired or now-self.last_event < self.cooldown:
            return None
        # A closed hand entering the frame is already a valid grab. Only an
        # action that actually fired requires opening before the next one.
        self.armed = True
        if self.start is None:
            self.start = now; self.origin = pos; self.previous = pos
            return None
        if math.dist(pos, self.previous) > .55 or now-self.start > 2.5:
            self.reset(); self.require_media_release()
            return None
        self.previous = pos
        if now-self.start < self.hold:
            # Keep the first position: fast natural motion must not be erased.
            return None
        dx, dy = pos[0]-self.origin[0], pos[1]-self.origin[1]
        major, minor = max(abs(dx),abs(dy)), min(abs(dx),abs(dy))
        if major < max(self.distance,norm*self.relative_floor) or major < minor*1.35:
            return None
        direction = ('right' if dx > 0 else 'left') if abs(dx) > abs(dy) else ('down' if dy > 0 else 'up')
        self.fired = True; self.armed = False; self._needs_grab_release = True; self.last_event = now
        self._media_start = None
        self._media_points = None
        return direction

def calibrated_profile(open_samples,closed_samples):
 """Learn only numerical geometry, never frames; reject indistinguishable poses."""
 import statistics
 if min(len(open_samples),len(closed_samples))<12:raise ValueError('Мало устойчивых кадров руки. Держите ладонь в кадре.')
 centres=lambda samples:[statistics.median(v[k] for v in samples) for k in ('index','middle','flex')]
 opened,closed=centres(open_samples),centres(closed_samples)
 if opened[0]-closed[0]<.18 or opened[1]-closed[1]<.2 or opened[2]-closed[2]<.12:
  raise ValueError('Положения слишком похожи. Покажите раскрытую ладонь, затем согните три пальца в захват.')
 index=min(1.3,closed[0]+(opened[0]-closed[0])*.38);middle=min(1.45,closed[1]+(opened[1]-closed[1])*.38)
 if closed[0]>=index or closed[1]>=middle or closed[2]>=1.4:raise ValueError('Захват слишком открыт. Сведите три пальца ближе.')
 return dict(index_limit=index,middle_limit=middle,curl_limit=min(1.4,closed[2]+.12),open_index=index+.13,open_middle=middle+.13)
