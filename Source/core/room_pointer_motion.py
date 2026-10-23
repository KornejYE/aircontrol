"""Interpolate received native pointer positions; never predict hand motion.

Call ``submit`` for validated pointer packets and ``tick`` from the UI timer.
Only ``move`` packets are delayed. A click/drag/scroll boundary first
finishes the latest fresh, received target, then sends the action immediately.
This can make the final small step visible, but keeps the action at its intended
position rather than clicking an intermediate interpolated point.
"""
import math
import time

from core.room_air_mouse import valid_pointer


class PointerMotion:
    MIN_INTERVAL = .012
    MAX_INTERVAL = .040
    STALE_AFTER = .120

    def __init__(self, send, clock=time.monotonic):
        self._send = send
        self._clock = clock
        self.reset()

    def reset(self):
        """Discard queued movement without emitting input of any kind."""
        self._output = None
        self._target = None
        self._start = None
        self._start_at = None
        self._duration = None
        self._last_arrival = None

    @property
    def pending(self):
        return self._target is not None

    def _now(self, now):
        now = self._clock() if now is None else now
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError('Invalid pointer time')
        return now

    @staticmethod
    def _mode(packet):
        return bool(packet.get('absolute')), 'relative_x' in packet

    @staticmethod
    def _coordinates(packet):
        return ('x', 'y', 'relative_x', 'relative_y') if 'relative_x' in packet else ('x', 'y')

    def _emit(self, packet):
        packet = dict(packet)
        try:
            self._send(dict(packet))
        except Exception:
            self.reset()
            raise
        self._output = packet

    def _clear_pending(self):
        self._target = self._start = self._start_at = self._duration = None

    def _finish(self, now):
        target = self._target
        fresh = target is not None and 0 <= now - self._start_at <= self.STALE_AFTER
        self._clear_pending()
        if fresh:
            self._emit(target)

    def submit(self, packet, now=None):
        """Receive a packet; the first position and all actions go out at once."""
        if not isinstance(packet, dict) or not valid_pointer(packet):
            raise ValueError('Invalid pointer packet')
        now = self._now(now)
        packet = dict(packet)
        if packet['phase'] == 'cancel':
            self.reset()
            self._emit(packet)
            return

        if self._output is not None and self._mode(packet) != self._mode(self._output):
            # A normalized absolute coordinate and accumulated relative travel
            # cannot share a segment or a native anchor.
            cancel = dict(self._output, phase='cancel')
            cancel.pop('dy', None)
            self.reset()
            self._emit(cancel)
            self._output = None

        if packet['phase'] != 'move':
            self._finish(now)
            self._last_arrival = None
            self._emit(packet)
            return

        previous_arrival = self._last_arrival
        if previous_arrival is not None and now < previous_arrival:
            self.reset()
            previous_arrival = None
        self.tick(now)
        self._last_arrival = now
        if (self._output is None or previous_arrival is None
                or now - previous_arrival > self.STALE_AFTER):
            self._clear_pending()
            self._emit(packet)
            return

        coordinates = self._coordinates(packet)
        if all(packet[key] == self._output[key] for key in coordinates):
            self._clear_pending()
            self._emit(packet)  # Keep stationary tracking heartbeats alive.
            return
        self._start = dict(self._output)
        self._target = packet
        self._start_at = now
        self._duration = max(self.MIN_INTERVAL,
                             min(self.MAX_INTERVAL, now - previous_arrival))

    def tick(self, now=None):
        """Output a point on the received segment, without extrapolation."""
        now = self._now(now)
        if self._target is None:
            return
        elapsed = now - self._start_at
        if elapsed < 0:
            return
        if elapsed > self.STALE_AFTER:
            self._clear_pending()
            return
        fraction = min(1., elapsed / self._duration)
        if fraction <= 0:
            return
        packet = dict(self._target)
        for key in self._coordinates(packet):
            packet[key] = self._start[key] + fraction * (self._target[key] - self._start[key])
        if fraction == 1.:
            # Copy the original endpoint exactly; avoid tiny floating drift.
            packet = self._target
            self._clear_pending()
        self._emit(packet)
