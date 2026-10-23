"""Headless application checks without a camera, models or system input."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Source'))
from PyQt6.QtWidgets import QApplication
from core import preferences
from core import room_gesture_panel as panel
from core.room_gesture_relay import Relay
from core.room_camera_lease import CameraLease
import main

class Standalone(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name);self.windows=[]
  self.patches=[patch.object(preferences,'DATA_DIR',self.root),patch.object(panel,'DATA_DIR',self.root),
    patch.object(main,'DATA_DIR',self.root),patch.object(panel,'Relay',side_effect=lambda **kw:Relay(port=0)),
    patch.object(panel.subprocess,'Popen',side_effect=AssertionError('No camera or background subprocess'))]
  for p in self.patches:p.start()
 def tearDown(self):
  for window in self.windows:window.controller.shutdown();window.close()
  for p in reversed(self.patches):p.stop()
  self.directory.cleanup()
 def window(self):
  window=main.AirControlWindow();self.windows.append(window);return window
 def test_main_window_does_not_load_assistant_or_start_camera(self):
  window=self.window();self.assertEqual(window.windowTitle(),'AirControl')
  self.assertIsNone(window.controller.process);self.assertFalse(window.controller.camera_snapshot()['running'])
  self.assertNotIn('memory.config_manager',sys.modules)
  for name in ('google.genai','openai','core.room_speech','core.room_person_vision'):self.assertNotIn(name,sys.modules)
  self.assertIn('Включить',window.start_button.text())
 def test_searchable_settings_have_gestures_only(self):
  window=self.window();view=window.settings('mouse')
  self.assertEqual(set(view.settings_workspace.sections),{'overview','mouse','scroll','bindings','camera','guide'})
  self.assertFalse(hasattr(view,'person_mode_box'))
  view.mouse_acceleration.setChecked(True)
  saved=json.loads((self.root/'config/gesture-actions.json').read_text())
  self.assertTrue(saved['mouse_acceleration']);self.assertEqual(saved['mouse_speed'],1.5)
  view.close()
 def test_preferences_reject_credentials_and_keep_data_local(self):
  preferences.save_preferences(room_gesture_camera=2,gemini_api_key='do-not-store',fish_api_key='do-not-store')
  path=self.root/'config/preferences.json'
  self.assertEqual(json.loads(path.read_text()),{'room_gesture_camera':2})
  self.assertEqual(preferences.load_preferences(),{'room_gesture_camera':2})
 def test_browser_extension_uses_separate_port_and_namespace(self):
  manifest=json.loads((ROOT/'BrowserGestures/manifest.json').read_text())
  self.assertEqual(manifest['host_permissions'],['http://127.0.0.1:8767/*'])
  self.assertIn('AirControl',manifest['name'])
  text=(ROOT/'BrowserGestures/content.js').read_text()
  self.assertIn('__airControlGestures',text);self.assertNotIn('__jarvisGestures',text)
 def test_camera_lease_blocks_competing_app_and_releases_cleanly(self):
  first=CameraLease(0,'Jarvis Room',folder=self.root).acquire()
  try:
   with self.assertRaisesRegex(RuntimeError,'Jarvis Room'):CameraLease(0,'AirControl',folder=self.root).acquire()
   other=CameraLease(1,'AirControl',folder=self.root).acquire();other.release()
  finally:first.release()
  retry=CameraLease(0,'AirControl',folder=self.root).acquire();retry.release();retry.release()

if __name__=='__main__':unittest.main()
