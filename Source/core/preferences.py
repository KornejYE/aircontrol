"""Only gesture preferences; atomic writes, no assistant credentials."""
import json
import os
import tempfile
import threading
from core.room_paths import DATA_DIR

_lock=threading.RLock()
_allowed={'room_gestures_browser_media','room_gesture_distance','room_gesture_camera','room_gestures_autostart'}

def load_preferences():
    with _lock:
        try:
            value=json.loads((DATA_DIR/'config/preferences.json').read_text())
            return {key:item for key,item in value.items() if key in _allowed} if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

def save_preferences(**changes):
    with _lock:
        value=load_preferences();value.update({key:item for key,item in changes.items() if key in _allowed})
        folder=DATA_DIR/'config';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        descriptor,name=tempfile.mkstemp(prefix='.preferences-',suffix='.tmp',dir=folder)
        try:
            with os.fdopen(descriptor,'w') as handle:json.dump(value,handle,ensure_ascii=False,indent=2)
            os.replace(name,folder/'preferences.json')
        finally:
            try:os.unlink(name)
            except FileNotFoundError:pass
