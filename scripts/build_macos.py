"""Build a local Mac app using this project's runtime and sources only."""
import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path.home()/'Applications/AirControl.app');args=parser.parse_args()
bundle=args.output.expanduser()
if bundle.exists():raise SystemExit('Папка уже существует; сохраните предыдущую сборку перед заменой: '+str(bundle))
if not (ROOT/'Runtime/bin/python').exists():raise SystemExit('Сначала запустите scripts/setup.py')
resources=bundle/'Contents/Resources';macos=bundle/'Contents/MacOS';resources.mkdir(parents=True);macos.mkdir()
for name in ('Source','BrowserGestures','Models','Runtime'):
    source=ROOT/name;destination=resources/name
    result=subprocess.run(['cp','-cR',str(source),str(destination)],capture_output=True)
    if result.returncode:
        # Clone-copy is fast on APFS; ordinary copying also supports other
        # volumes. Only this new build's partial output is replaced.
        if destination.exists():shutil.rmtree(destination)
        shutil.copytree(source,destination,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('LICENSE','NOTICE.md','README.md','README.ru.md','PRIVACY.md','UPSTREAM.json','CHANGELOG.md'):shutil.copy2(ROOT/name,resources/name)
shutil.copytree(ROOT/'docs',resources/'docs')
# Recreate the virtual environment's entry points at their installed location.
# The Python installation is the system/Homebrew installation, never Jarvis.
subprocess.run([str(ROOT/'Runtime/bin/python'),'-m','venv','--without-pip',str(resources/'Runtime')],check=True)
# A signed bundle cannot contain a symlink escaping into Homebrew. Copy the
# small executable; its linked Python framework remains the installed Python.
for entry in (resources/'Runtime/bin').iterdir():
    if entry.is_symlink() and entry.readlink().is_absolute():
        resolved=entry.resolve();entry.unlink();shutil.copy2(resolved,entry)
subprocess.run(['/usr/bin/swiftc',str(ROOT/'Native/AirControl.swift'),'-framework','AppKit','-framework','AVFoundation','-o',str(macos/'AirControl')],check=True)
info=dict(CFBundleName='AirControl',CFBundleDisplayName='AirControl',CFBundleIdentifier='local.aircontrol.desktop',CFBundleExecutable='AirControl',CFBundlePackageType='APPL',CFBundleShortVersionString='1.3.2',CFBundleVersion='8',CFBundleIconFile='AirControl.icns',NSCameraUsageDescription='Распознавать движения рук и выбранный предмет для управления компьютером. Кадры обрабатываются локально.',NSHighResolutionCapable=True)
with (bundle/'Contents/Info.plist').open('wb') as handle:plistlib.dump(info,handle)
# Render the code-native icon using Qt; no image-generation dependency.
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage,QPainter
from PyQt6.QtSvg import QSvgRenderer
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6.QtWidgets import QApplication
app=QApplication.instance() or QApplication([])
iconset=ROOT/'artifacts/AirControl.iconset';iconset.mkdir(parents=True,exist_ok=True)
renderer=QSvgRenderer(str(ROOT/'Source/assets/aircontrol.svg'))
for size in (16,32,128,256,512):
    for scale in (1,2):
        image=QImage(size*scale,size*scale,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);renderer.render(painter);painter.end()
        image.save(str(iconset/f'icon_{size}x{size}{"@2x" if scale==2 else ""}.png'))
subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(resources/'AirControl.icns')],check=True)
sys_path = str(ROOT/'Source')
import sys
sys.path.insert(0, sys_path)
from core.room_app_identity import prepare_host
prepare_host(resources/'Runtime', 'AirControl', 'local.aircontrol.desktop.interface', resources/'AirControl.icns')
subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(bundle)],check=True)
print(bundle)
