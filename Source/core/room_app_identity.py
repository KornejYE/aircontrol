"""Give the GUI its own macOS bundle instead of Homebrew's Python.app.

The small host executable uses the existing Python framework and virtualenv;
the outer launcher and its permission/keychain identity remain untouched.
"""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


def prepare_host(runtime, name, identifier, icon=None):
    runtime = Path(runtime)
    framework = Path(sys.base_prefix).resolve()
    source = framework / 'Resources/Python.app/Contents/MacOS/Python'
    if not source.is_file():
        raise RuntimeError('A macOS framework Python is required')
    bundle = runtime / 'Applications' / (name + '.app')
    executable = bundle / 'Contents/MacOS' / name.replace(' ', '')
    executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, executable)
    info = dict(CFBundleName=name, CFBundleDisplayName=name,
                CFBundleIdentifier=identifier, CFBundleExecutable=executable.name,
                CFBundlePackageType='APPL', NSHighResolutionCapable=True,
                NSCameraUsageDescription='Распознавание жестов локально на компьютере.',
                NSMicrophoneUsageDescription='Голосовое управление помощником.')
    if icon and Path(icon).is_file():
        resources = bundle / 'Contents/Resources'
        resources.mkdir(exist_ok=True)
        shutil.copy2(icon, resources / Path(icon).name)
        info['CFBundleIconFile'] = Path(icon).name
    (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(bundle)],
                   check=True, capture_output=True)
    return executable


def reexec_named_host(name, app_environment):
    if sys.platform != 'darwin' or not os.environ.get(app_environment):
        return
    host = Path(sys.prefix) / 'Applications' / (name + '.app') / 'Contents/MacOS' / name.replace(' ', '')
    if not host.is_file() or os.environ.get('ROOM_NAMED_HOST') == str(host):
        return
    environment = dict(os.environ)
    # CPython's supported macOS launcher variable preserves pyvenv.cfg lookup
    # after the executable moves into its named GUI bundle.
    environment['__PYVENV_LAUNCHER__'] = sys.executable
    environment['ROOM_NAMED_HOST'] = str(host)
    os.execve(str(host), [str(host), *sys.argv], environment)
