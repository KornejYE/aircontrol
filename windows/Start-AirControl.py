"""Launch the local UI without a console; keep startup failures in a local log."""
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT=Path(__file__).resolve().parent
source=ROOT/'Source'
logs=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'AirControl/Logs'
logs.mkdir(parents=True,exist_ok=True)
log=logs/'app.log'
if log.exists() and log.stat().st_size>4_000_000:
    previous=log.with_suffix('.previous.log')
    if previous.exists():previous.unlink()
    log.replace(previous)
sys.stdout=sys.stderr=log.open('a',encoding='utf-8',buffering=1)
os.environ.setdefault('PYTHONUNBUFFERED','1')
os.environ.setdefault('PYTHONDONTWRITEBYTECODE','1')
sys.path.insert(0,str(source));os.chdir(ROOT)
sys.argv=[str(source/'main.py')]
try:runpy.run_path(str(source/'main.py'),run_name='__main__')
except SystemExit:raise
except Exception:
    traceback.print_exc()
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,'AirControl не удалось запустить. Подробности: '+str(log),'AirControl',0x10)
    raise
