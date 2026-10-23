"""Replays geometry and native input with fakes; never sends real game input."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Source'))
from core.room_hand_joystick import HandJoystick, game_settings, valid_stick
from core.room_game_input import GameInput
from core.room_gesture_rules import HandRules, settings
from core.room_gesture_worker import runtime_settings


def hand(dx=0., dy=0., *, pinch=True):
    p = [(.5, .65)] * 21
    p[0] = (.5, .7)
    p[5], p[9], p[13], p[17] = (.45, .55), (.49, .53), (.53, .55), (.57, .58)
    p[4], p[8], p[12] = (.42, .42), (.425 if pinch else .50, .42), (.49, .26)
    return [(x+dx, y+dy) for x, y in p]


def packet(x=0., y=0., active=True):
    return dict(action='joystick', phase='update', active=active, x=x, y=y)


class Geometry(unittest.TestCase):
    def setUp(self):
        self.s = HandJoystick()

    def engage(self):
        self.assertFalse(self.s.update(hand(), 1.)['active'])
        return self.s.update(hand(), 1.2)

    def test_pinch_dwell_then_neutral_and_proportional_deflection(self):
        self.assertTrue(self.engage()['active'])
        for i in range(8):
            out = self.s.update(hand(.09, -.06), 1.23+i*.03)
        self.assertGreater(out['x'], .15)
        self.assertLess(out['y'], -.05)
        self.assertTrue(valid_stick(out))
        self.assertLessEqual(math.hypot(out['x'], out['y']), 1.001)

    def test_release_loss_invalid_or_clock_gap_clears_old_center(self):
        for interruption in ('release', 'missing', 'nan', 'gap'):
            self.s.reset();self.engage()
            self.s.update(hand(.15), 1.23)
            if interruption == 'release':out = self.s.update(hand(pinch=False), 1.26)
            elif interruption == 'missing':out = self.s.update(None, 1.26)
            elif interruption == 'nan':out = self.s.update([(math.nan, 0)]*21, 1.26)
            else:out = self.s.update(hand(.15), 1.8)
            self.assertFalse(out['active'], interruption)
            self.assertEqual((out['x'], out['y']), (0, 0))
            at = 1.83 if interruption == 'gap' else 1.30
            self.s.update(hand(.15), at)
            resumed = self.s.update(hand(.15), at+.20)
            self.assertTrue(resumed['active'])
            self.assertEqual((resumed['x'], resumed['y']), (0, 0))

    def test_neutral_has_deadzone_and_axes_invert(self):
        self.engage()
        self.assertEqual(self.s.update(hand(.001, .001), 1.23)['x'], 0)
        self.assertLess(self.s.update(hand(0, .1), 1.26, {'invert_y': True})['y'], 0)

    def test_config_is_bounded_and_invalid_packets_fail_closed(self):
        config = game_settings(dict(output='shell', radius=float('nan'), deadzone=-10, target=['app']))
        self.assertEqual(config['output'], 'preview')
        self.assertEqual(config['radius'], 1.4)
        self.assertEqual(config['deadzone'], .05)
        self.assertEqual(config['target'], '')
        for bad in (packet(math.nan), packet(2), packet(.5, active=False), dict(packet(), x=True), dict(packet(), phase='cancel')):
            self.assertFalse(valid_stick(bad))

    def test_joystick_is_separate_from_pointer_and_browser_overlay(self):
        self.assertEqual(settings({'mouse_hand': 'Left'})['joystick']['hand'], 'Left')
        s = HandRules();s.configure({'mode': 'joystick', 'swap_hands': True, 'joystick': {'hand': 'Left'}})
        s.take_pending()
        self.assertIsNone(s.update(hand(), 1., 'Left'))
        self.assertEqual(s.update(hand(), 1., 'Right')[0][1], 'joystick')
        s.update(hand(), 1.2, 'Right');s.reset_hand('Right')
        self.assertFalse(s.take_pending()[0][2]['active'])
        self.assertEqual(runtime_settings({'mode': 'joystick'}, {'mode': 'mouse', 'span': .2})['mode'], 'joystick')


class FakeAPI:
    def __init__(self):
        self.events = [];self.front = 'game';self.esc = False;self.pos = (500, 400)
    def foreground(self):return self.front
    def escape(self):return self.esc
    def key(self, code, down):self.events.append(('key', code, down))
    def position(self):return self.pos
    def stick_bounds(self):return (500, 400, 800)
    def move(self, position):self.events.append(('move', position));self.pos = position


class NativeInput(unittest.TestCase):
    def setUp(self):self.now = 10.;self.api = FakeAPI()
    def input(self, output='wasd', target='game'):
        sink = GameInput(dict(output=output, target=target), api_factory=lambda:self.api, clock=lambda:self.now)
        sink.send(packet(active=False), self.now)
        return sink
    def send(self, sink, x=0., y=0., active=True, captured=None):
        sink.send(packet(x,y,active), self.now if captured is None else captured)

    def test_default_preview_and_unselected_target_do_not_load_native_api(self):
        def forbidden():raise AssertionError('No OS input')
        for config in ({}, {'output':'wasd'}):
            sink = GameInput(config, api_factory=forbidden, clock=lambda:self.now)
            self.send(sink, 1.)
            self.assertIsNone(sink.api)

    def test_new_live_output_cannot_inherit_an_old_active_grip(self):
        sink = GameInput(dict(output='wasd', target='game'), api_factory=lambda:self.api, clock=lambda:self.now)
        self.send(sink, 1.)
        self.assertFalse(self.api.events)
        self.send(sink, active=False);self.send(sink, 1.)
        self.assertEqual(self.api.events, [('key',2,True)])

    def test_held_directions_no_repeat_hysteresis_and_balanced_diagonal(self):
        sink = self.input();self.send(sink, 1., -1.)
        self.assertEqual(sink.held, {'right', 'up'})
        for _ in range(20):self.send(sink, .25, -.25)
        self.assertEqual(len(self.api.events), 2)
        self.send(sink, -1., 0.)
        self.assertEqual(sink.held, {'left'})
        self.assertEqual(self.api.events[2:4], [('key',2,False),('key',13,False)])
        self.send(sink, active=False)
        self.assertFalse(sink.held)
        for code in (0, 2, 13):
            events = [event[2] for event in self.api.events if event[:2]==('key',code)]
            self.assertEqual(events, [True, False])

    def test_stall_releases_and_requires_regrip(self):
        sink = self.input();self.send(sink, 1.)
        self.now += .26;sink.poll()
        self.assertFalse(sink.held)
        self.send(sink, 1.)
        self.assertFalse(sink.held)
        self.send(sink, active=False);self.send(sink, 1.)
        self.assertEqual(sink.held, {'right'})

    def test_focus_loss_cannot_type_into_other_apps_or_resume_a_held_grip(self):
        sink = self.input();self.send(sink, 1.)
        self.api.front = 'browser';sink.poll()
        self.assertFalse(sink.held)
        events = list(self.api.events)
        self.send(sink, 1.)
        self.assertEqual(self.api.events, events)
        self.api.front = 'game';self.send(sink, 1.)
        self.assertFalse(sink.held)
        self.send(sink, active=False);self.send(sink, 1.)
        self.assertTrue(sink.held)

    def test_escape_latches_until_controller_recreated(self):
        sink = self.input();self.send(sink, 1.)
        self.api.esc = True;sink.poll();self.api.esc = False
        self.assertFalse(sink.held)
        self.send(sink, active=False);self.send(sink, 1.)
        self.assertFalse(sink.held)
        self.assertTrue(sink.escaped)

    def test_old_future_and_malformed_capture_times_cannot_hold_keys(self):
        for captured in (9., 11., float('nan'), True):
            sink = self.input();self.send(sink, 1.)
            self.send(sink, 1., captured=captured)
            self.assertFalse(sink.held)

    def test_failed_partial_key_down_is_released(self):
        sink = self.input();original = self.api.key
        def fail(code, down):
            original(code, down)
            if code == 13 and down:raise RuntimeError('post failed')
        self.api.key = fail
        with self.assertRaises(RuntimeError):self.send(sink, 1., -1.)
        self.assertFalse(sink.held)
        self.assertCountEqual(self.api.events[-2:], [('key',2,False),('key',13,False)])

    def test_mouse_joystick_maps_smooth_axes_and_returns_to_neutral(self):
        sink = self.input('mouse');self.send(sink, .5, -.5)
        self.assertEqual(self.api.pos, (620.,280.))
        self.send(sink, active=False)
        self.assertEqual(self.api.pos, (500,400))
        self.assertFalse(any(event[0]=='key' for event in self.api.events))

    def test_mouse_has_physical_priority_and_focus_loss_does_not_warp_other_app(self):
        sink = self.input('mouse');self.send(sink, .5)
        self.api.pos = (100,100);self.send(sink, .8)
        self.assertEqual(self.api.pos, (100,100))
        self.assertTrue(sink.blocked)
        self.send(sink, active=False);self.send(sink, .5)
        self.api.front = 'browser';before = list(self.api.events);sink.poll()
        self.assertEqual(self.api.events, before)


if __name__ == '__main__':unittest.main()
