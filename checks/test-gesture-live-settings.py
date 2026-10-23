"""Live range changes and touch IPC; offscreen Qt, no camera or OS input."""
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from PyQt6.QtWidgets import QApplication,QWidget
from core import room_gesture_panel as panel
from core.room_gesture_rules import read_settings
from core.room_gesture_relay import Relay


class LiveSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.settings={}
        self.patches=[patch.object(panel,'DATA_DIR',Path(self.directory.name)),
                      patch.object(panel,'load_preferences',side_effect=lambda:dict(self.settings)),
                      patch.object(panel,'save_preferences',side_effect=lambda **kw:self.settings.update(kw)),
                      patch.object(panel.subprocess,'Popen',side_effect=AssertionError('No camera start/restart'))]
        for p in self.patches:p.start()
        self.parent=QWidget()

    def tearDown(self):
        controller=getattr(self.parent,'_gesture_controller',None)
        if controller:controller.process=None
        self.parent.close()
        for p in reversed(self.patches):p.stop()
        self.directory.cleanup()

    def controller(self):
        c=panel.GestureController(self.parent);c.control_mode='analog';c.ready=True
        c.process=S(poll=lambda:None,stdin=io.StringIO());c.relay=Relay()
        return c

    def test_mode_aware_slider_applies_without_camera_restart(self):
        view=panel.GesturePanel(self.parent)
        try:
            c=view.controller;c.process=S(poll=lambda:None,stdin=io.StringIO());c.tracking_command=Mock()
            view.mode_combo.setCurrentIndex(view.mode_combo.findData('analog'))
            self.assertEqual((view.distance.minimum(),view.distance.maximum()),(12,60))
            self.assertEqual(view.distance.value(),20)
            self.assertIn('одно видео',view.distance_label.text())
            view.distance.setValue(50)
            self.assertEqual(read_settings(Path(self.directory.name)/'config/gesture-actions.json')['analog_span'],.5)
            self.assertEqual(c.analog_span,.5)
            c.tracking_command.assert_called_with('reload_rules')
            original_process=c.process
            view.mode_combo.setCurrentIndex(view.mode_combo.findData('discrete'))
            self.assertEqual((view.distance.minimum(),view.distance.maximum()),(4,20))
            view.distance.setValue(16)
            self.assertEqual(self.settings['room_gesture_distance'],.16)
            self.assertIs(c.process,original_process)
            view.mode_combo.setCurrentIndex(view.mode_combo.findData('analog'))
            self.assertEqual(view.distance.value(),50)
        finally:view.close()

    def test_lifecycle_only_accepts_current_fresh_stream(self):
        c=self.controller();stamp=time.monotonic()
        def send(i,phase,position,ident='Right:1:100'):
            c.receive(dict(type='drag_scroll',id=i,mode='analog',hand='Right',gesture_id=ident,
                           phase=phase,position=position,captured_monotonic=stamp))
        send(1,'move',.4)
        self.assertEqual(c.relay.sequence,0)
        send(2,'start',0);send(3,'move',.4);send(4,'end',.4)
        rows=c.relay.snapshot(0,c.relay.session,drag=True)['events']
        self.assertEqual([r['phase'] for r in rows],['start','move','end'])
        self.assertEqual([r['position'] for r in rows],[0,.4,.4])
        send(5,'move',.9)
        self.assertEqual(c.relay.sequence,3)

    def test_mode_and_range_changes_invalidate_partial_drag(self):
        c=self.controller();old=c.relay.session
        c.receive(dict(type='drag_scroll',id=1,mode='analog',hand='Right',gesture_id='Right:1',
                       phase='start',position=0,captured_monotonic=time.monotonic()))
        c.set_analog_span(.5)
        self.assertNotEqual(c.relay.session,old)
        self.assertEqual(list(c.relay.events),[])
        self.assertIsNone(c._drag_stream)
        self.assertIn('reload_rules',c.process.stdin.getvalue())

    def test_legacy_reader_never_receives_drag_packets(self):
        relay=Relay();relay.publish_drag(hand='Right',gesture_id='Right:1',phase='start',position=0)
        self.assertEqual(relay.snapshot(0,relay.session)['events'],[])
        self.assertEqual(relay.snapshot(0,relay.session,drag=True)['events'][0]['phase'],'start')
        for position in (float('nan'),float('inf'),9,True):
            with self.assertRaises(ValueError):relay.publish_drag(hand='Right',gesture_id='Right:1',phase='move',position=position)


if __name__=='__main__':unittest.main()
