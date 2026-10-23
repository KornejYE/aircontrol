"""Replay interpolation with a fake clock/sink; never emit real mouse input."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Source'))
from core.room_pointer_motion import PointerMotion


def move(x=.5, y=.5, **extra):
    return dict(action='pointer', phase='move', x=x, y=y,
                relative_x=x, relative_y=y, absolute=False, **extra)


class Motion(unittest.TestCase):
    def fixture(self):
        events = []
        clock = [0.]
        motion = PointerMotion(lambda p: events.append((clock[0], p)), lambda: clock[0])
        return motion, events, clock

    def test_first_anchor_is_immediate(self):
        motion, events, _ = self.fixture()
        packet = move()
        motion.submit(packet)
        self.assertEqual(events, [(0., packet)])
        motion.tick(.02)
        self.assertEqual(len(events), 1)

    def test_monotone_motion_at_30_and_60_timer_fps(self):
        for fps in (30, 60):
            motion, events, clock = self.fixture()
            # 25-Hz camera input, independent of the output timer cadence.
            timeline = [(i / 25, 'input', i) for i in range(11)]
            timeline += [(i / fps, 'tick', i) for i in range(1, int(.5 * fps) + 1)]
            for now, kind, index in sorted(timeline):
                clock[0] = now
                if kind == 'input':
                    motion.submit(move(.2 + .04 * index))
                else:
                    motion.tick()
            xs = [p['relative_x'] for _, p in events]
            self.assertEqual(xs, sorted(xs))
            self.assertTrue(all(.2 <= value <= .6 + 1e-12 for value in xs))
            self.assertAlmostEqual(xs[-1], .6)
            self.assertTrue(all(p['x'] == p['relative_x'] for _, p in events))

    def test_cancel_mid_ramp_never_emits_later_ghost_movement(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
        clock[0] = .06; motion.tick()
        motion.submit(move(.3) | dict(phase='cancel'))
        before = list(events)
        for now in (.07, .1, 1.):
            motion.tick(now)
        self.assertEqual(events, before)
        self.assertEqual(events[-1][1]['phase'], 'cancel')
        self.assertAlmostEqual(events[-2][1]['x'], .4)

    def test_reset_discards_pending_without_sending_anything(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
        motion.reset(); motion.tick(.08)
        self.assertEqual(len(events), 1)

    def test_nonmove_finishes_fresh_target_before_action(self):
        for phase in ('click', 'down', 'up', 'context', 'scroll'):
            motion, events, clock = self.fixture()
            motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
            clock[0] = .05
            packet = move(.6) | dict(phase=phase)
            if phase == 'scroll':
                packet['dy'] = .01
            motion.submit(packet)
            self.assertEqual([p['phase'] for _, p in events], ['move', 'move', phase])
            self.assertEqual(events[-2][1]['relative_x'], .6)
            before = len(events); motion.tick(.1)
            self.assertEqual(len(events), before)

    def test_stale_target_is_not_replayed_before_action_or_tick(self):
        for action in (None, 'click'):
            motion, events, clock = self.fixture()
            motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
            clock[0] = .17
            if action:
                motion.submit(move(.6) | dict(phase=action))
                self.assertEqual([p['phase'] for _, p in events], ['move', 'click'])
            else:
                motion.tick()
                self.assertEqual(len(events), 1)
            motion.tick(.2)
            self.assertEqual(events[-1][1]['phase'], action or 'move')

    def test_reversal_starts_from_current_output_without_overshoot(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.8))
        clock[0] = .06; motion.submit(move(.3))
        self.assertAlmostEqual(events[-1][1]['x'], .5)
        clock[0] = .07; motion.tick()
        self.assertAlmostEqual(events[-1][1]['x'], .4)
        clock[0] = .08; motion.tick()
        self.assertAlmostEqual(events[-1][1]['x'], .3)
        self.assertTrue(all(.3 <= p['x'] <= .5 + 1e-12 for at, p in events if at >= .06))

    def test_positioning_transition_cancels_old_anchor_without_mixed_coordinates(self):
        for target in (dict(action='pointer', phase='move', x=.8, y=.7, absolute=True),
                       dict(action='pointer', phase='move', x=.8, y=.7, absolute=False)):
            motion, events, clock = self.fixture()
            motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
            clock[0] = .05; motion.submit(target)
            self.assertEqual([p['phase'] for _, p in events], ['move', 'cancel', 'move'])
            self.assertEqual(events[-1][1], target)
            before = len(events); motion.tick(.1)
            self.assertEqual(len(events), before)

    def test_relative_travel_is_unbounded_and_both_axes_are_interpolated(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.9) | dict(relative_x=2., relative_y=-2.))
        clock[0] = .04; motion.submit(move(1.) | dict(relative_x=3., relative_y=-3.))
        clock[0] = .06; motion.tick()
        self.assertAlmostEqual(events[-1][1]['relative_x'], 2.5)
        self.assertAlmostEqual(events[-1][1]['relative_y'], -2.5)
        self.assertAlmostEqual(events[-1][1]['x'], .95)

    def test_invalid_packet_does_not_mutate_live_segment(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
        broken = move(.3); del broken['relative_y']
        with self.assertRaises(ValueError):
            motion.submit(broken)
        clock[0] = .08; motion.tick()
        self.assertEqual(events[-1][1]['x'], .6)

    def test_observed_interval_has_minimum_and_maximum_bounds(self):
        for interval, duration in ((.001, .012), (.08, .04)):
            motion, events, clock = self.fixture()
            motion.submit(move(.2)); clock[0] = interval; motion.submit(move(.6))
            clock[0] += duration / 2; motion.tick()
            self.assertAlmostEqual(events[-1][1]['x'], .4)
            clock[0] += duration / 2; motion.tick()
            self.assertAlmostEqual(events[-1][1]['x'], .6)

    def test_new_sample_after_stall_does_not_replay_old_pending_target(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
        clock[0] = .3; motion.submit(move(.3))
        self.assertEqual([p['x'] for _, p in events], [.2, .3])
        motion.tick(.4)
        self.assertEqual(len(events), 2)

    def test_sink_failure_discards_pending_movement(self):
        motion, events, clock = self.fixture()
        motion.submit(move(.2)); clock[0] = .04; motion.submit(move(.6))
        original = motion._send
        def broken_sink(packet):
            raise RuntimeError('native output failed')
        motion._send = broken_sink
        with self.assertRaises(RuntimeError):
            motion.tick(.06)
        motion._send = original
        motion.tick(.08)
        self.assertEqual(len(events), 1)


if __name__ == '__main__':
    unittest.main()
