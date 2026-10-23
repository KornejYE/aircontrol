"""Qt/IPC lifecycle checks with a fake game and no camera or native input."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Source'))
from PyQt6.QtWidgets import QApplication, QWidget
from core import room_gesture_panel as panel
from core import room_game_input as game
from core.room_gesture_relay import Relay
from core.room_gesture_rules import read_settings, save_settings


class Controller(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.now = 10.;self.events = [];self.front = 'game';self.esc = False
        self.api = S(foreground=lambda:self.front, escape=lambda:self.esc,
                     key=lambda code, down:self.events.append((code, down)))
        original = game.GameInput
        def factory(config):return original(config, api_factory=lambda:self.api, clock=lambda:self.now)
        self.patches = [patch.object(panel, 'DATA_DIR', self.root),
                        patch.object(panel, 'load_preferences', return_value={}),
                        patch.object(panel.time, 'monotonic', side_effect=lambda:self.now),
                        patch.object(game, 'GameInput', side_effect=factory)]
        for p in self.patches:p.start()
        self.window = QWidget();self.c = panel.GestureController(self.window);self.c._browser_timer.stop()
        self.c.control_mode = 'joystick';self.c.ready = True
        self.c.process = S(poll=lambda:None, stdin=io.StringIO())
        save_settings(self.root/'config/gesture-actions.json',
                      {'mode':'joystick', 'mouse_hand':'Left', 'swap_hands':True,
                       'joystick':{'output':'wasd', 'target':'game'}})
        self.receive(ident=1, active=False, x=0.)
    def tearDown(self):
        self.c.release_game();self.c.process = None
        self.window.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def receive(self, ident=2, **overrides):
        packet = dict(type='joystick', action='joystick', phase='update', active=True,
                      x=1., y=0., id=ident, mode='joystick', captured_monotonic=self.now)
        packet.update(overrides);self.c.receive(packet)
    def test_fresh_input_and_watchdog_release_on_worker_stall(self):
        self.receive();self.assertEqual(self.events, [(2,True)])
        self.now += .26;self.c.poll_browser_profile()
        self.assertEqual(self.events, [(2,True),(2,False)])
        self.assertFalse(self.c.joystick_data)
    def test_epoch_mode_duplicate_and_stale_capture_cannot_press_keys(self):
        for changes in ({'_epoch':self.c.epoch-1}, {'mode':'mouse'}, {'id':0},
                        {'captured_monotonic':9.}, {'captured_monotonic':float('nan')}):
            self.receive(**changes)
        self.assertFalse(self.events)
    def test_reload_drops_inflight_old_packets_and_releases_before_reconfiguration(self):
        self.receive();self.now += .03;self.c.reload_rules()
        self.assertEqual(self.events[-1], (2,False))
        self.receive(ident=2, captured_monotonic=10.)
        self.assertEqual(len(self.events), 2)
        self.receive(ident=3);self.assertEqual(self.events[-1], (2,False))
        self.receive(ident=4, active=False, x=0.)
        self.receive(ident=5);self.assertEqual(self.events[-1], (2,True))
    def test_mode_exit_with_unused_browser_has_no_invalid_zero_revision_handshake(self):
        self.c.relay = Relay(port=0)
        self.receive();self.c.set_mode('system_mouse')
        self.assertEqual(self.events[-1], (2,False))
        self.c.poll_browser_profile()
        self.assertEqual(self.c._browser_revision, 0)
        self.assertTrue(self.c._worker_profile_ready)
        self.assertNotIn('runtime_config', self.c.process.stdin.getvalue())
        config = read_settings(self.root/'config/gesture-actions.json')
        self.assertEqual(config['mouse_hand'], 'Left');self.assertTrue(config['swap_hands'])
    def test_browser_overlay_cannot_override_game_or_route_game_input_to_browser(self):
        self.c.relay = Relay(port=0)
        self.c.relay.offer_browser_profile('mouse', target='window:3')
        self.c._browser_mode = 'mouse';self.c.poll_browser_profile()
        self.assertEqual(self.c.effective_mode, 'joystick')
        self.receive();self.assertEqual(self.events[-1], (2,True))
        self.assertFalse(self.c.relay.events)
    def test_calibration_and_error_ended_paths_release_input(self):
        self.receive();self.c.calibrate()
        self.assertEqual(self.events[-1], (2,False))
        self.receive(ident=2);self.assertEqual(len(self.events), 2)


if __name__ == '__main__':unittest.main()
