"""Private application data; never reads Jarvis settings or API keys."""
import os
import sys
from pathlib import Path

if os.environ.get('AIRCONTROL_DATA_DIR'):
    DATA_DIR=Path(os.environ['AIRCONTROL_DATA_DIR']).expanduser()
elif sys.platform=='darwin':
    DATA_DIR=Path.home()/'Library/Application Support/AirControl'
elif sys.platform=='win32':
    DATA_DIR=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'AirControl'
else:
    DATA_DIR=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'AirControl'
