"""Installer checks without installing packages or making requests."""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aircontrol_setup',ROOT/'scripts/setup.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

class Installer(unittest.TestCase):
 def test_wrong_platform_does_not_create_a_runtime(self):
  with patch.object(sys,'argv',['setup.py']),patch.object(setup.sys,'platform','linux'),patch.object(setup.venv,'EnvBuilder') as builder:
   with self.assertRaisesRegex(SystemExit,'macOS'):setup.main()
   builder.assert_not_called()
 def test_invalid_model_cannot_replace_an_existing_installation(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'hand_landmarker.task';target.write_bytes(b'existing-model')
   with patch.object(setup.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt-download')):
    with self.assertRaisesRegex(RuntimeError,'checksum'):setup.download_model(target)
   self.assertEqual(target.read_bytes(),b'existing-model')
   self.assertEqual([p.name for p in target.parent.iterdir()],['hand_landmarker.task'])
 def test_verified_download_is_atomic_and_keeps_tls_verification(self):
  import hashlib,ssl
  data=b'test-model'
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'models/hand_landmarker.task'
   with patch.object(setup,'MODEL_SHA256',hashlib.sha256(data).hexdigest()),patch.object(setup.urllib.request,'urlopen',return_value=io.BytesIO(data)) as request:
    setup.download_model(target)
   self.assertEqual(target.read_bytes(),data)
   context=request.call_args.kwargs['context']
   self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(context.check_hostname)
   self.assertEqual([p.name for p in target.parent.iterdir()],['hand_landmarker.task'])

if __name__=='__main__':unittest.main()
