"""Install the local Mac runtime and a checksum-pinned hand model."""
import argparse
import hashlib
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import venv

ROOT=Path(__file__).resolve().parents[1]
MODEL_URL='https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_SHA256='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'

def download_model(target):
    # Homebrew Python may not have its own CA bundle configured. Use the
    # operating system's trusted certificates without disabling verification.
    ca_file=os.environ.get('SSL_CERT_FILE') or '/etc/ssl/cert.pem'
    context=ssl.create_default_context(cafile=ca_file if Path(ca_file).is_file() else None)
    with urllib.request.urlopen(MODEL_URL,timeout=60,context=context) as response:
        data=response.read()
    if hashlib.sha256(data).hexdigest()!=MODEL_SHA256:
        raise RuntimeError('The hand model checksum did not match; nothing was installed.')
    target.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.hand-model-',dir=target.parent)
    try:
        with os.fdopen(descriptor,'wb') as handle:handle.write(data)
        os.replace(name,target)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if sys.platform!='darwin':raise SystemExit('This installer currently supports macOS only.')
    if sys.version_info[:2]!=(3,11):raise SystemExit('Run this installer with Python 3.11: python3.11 scripts/setup.py')
    runtime=ROOT/'Runtime'
    venv.EnvBuilder(with_pip=True).create(runtime)
    subprocess.run([str(runtime/'bin/python'),'-m','pip','install','-r',str(ROOT/'requirements-macos.lock')],check=True)
    download_model(ROOT/'Models/gestures/hand_landmarker.task')
    print('Ready. Run Runtime/bin/python Source/main.py')
    print('Build an app with Runtime/bin/python scripts/build_macos.py')

if __name__=='__main__':main()
