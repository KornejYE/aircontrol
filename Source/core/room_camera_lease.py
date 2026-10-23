"""One gesture controller per camera, including the standalone AirControl app."""
import json
import os
import sys
from pathlib import Path

class CameraLease:
 def __init__(self,camera,owner,folder=None):
  root=(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local')) if sys.platform=='win32' else Path.home()/'Library/Caches' if sys.platform=='darwin' else Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache')))
  self.path=Path(folder) / f'camera-{int(camera)}.lock' if folder is not None else root/'GestureCamera'/f'camera-{int(camera)}.lock'
  self.owner=owner;self.handle=None
 def acquire(self):
  self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  handle=self.path.open('a+',encoding='utf-8')
  try:
   if sys.platform=='win32':
    import msvcrt
    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError:
   handle.seek(0)
   try:owner=json.loads(handle.read(256)).get('owner','другом приложении')
   except (ValueError,AttributeError):owner='другом приложении'
   handle.close()
   raise RuntimeError(f'Камера уже используется в {owner}. Выключите там управление жестами, затем включите здесь.') from None
  try:
   handle.seek(0);handle.truncate();json.dump(dict(owner=self.owner,pid=os.getpid()),handle);handle.flush()
  except Exception:handle.close();raise
  self.handle=handle;return self
 def release(self):
  if self.handle is not None:self.handle.close();self.handle=None
