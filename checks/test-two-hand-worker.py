"""Replay both grips through camera-worker arbitration and JSON serialization."""
import contextlib,io,json,runpy,sys,tempfile
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/('Source' if (ROOT/'Source').exists() else 'desktop/Source')))
from core import room_gesture_worker as worker
from mediapipe.tasks.python import vision
pair=runpy.run_path(str(ROOT/'checks/test-two-hand-zoom.py'))['pair']
class Camera:
    def isOpened(self):return True
    def set(self,*args):return True
class Frames:
    index=0;now=10.
    def __init__(self,camera):Frames.index=0;Frames.now=10.
    def read_after(self,*args):
        Frames.index+=1
        if Frames.index>40:raise KeyboardInterrupt
        Frames.now=10+Frames.index/25
        return Frames.index,Frames.now,np.zeros((360,640,3),dtype=np.uint8)
    def close(self):pass
class Detector:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def detect_for_video(self,*args):
        hands=pair(.4+min(.2,max(0,Frames.index-6)*.01),grip=Frames.index<36)
        return S(hand_landmarks=[[S(x=x,y=y,z=0.) for x,y in p] for _,p in hands],
                 handedness=[[S(category_name=side,score=.99)] for side,_ in hands])
output=io.StringIO()
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'config').mkdir();(root/'config/gesture-actions.json').write_text(json.dumps({'mode':'system_mouse'}))
    with patch.object(worker,'DATA_DIR',root),patch.object(worker,'LatestFrame',Frames),patch('cv2.VideoCapture',return_value=Camera()),patch.object(vision.HandLandmarker,'create_from_options',return_value=Detector()),patch.object(worker.os,'nice'),patch.object(worker.time,'monotonic',side_effect=lambda:Frames.now+.005),patch.object(sys,'argv',['worker','--model','unused.task']),patch.object(sys,'stdin',io.StringIO()),contextlib.redirect_stdout(output):
        try:worker.main()
        except KeyboardInterrupt:pass
rows=[json.loads(line) for line in output.getvalue().splitlines()]
zooms=[r for r in rows if r['type']=='action']
assert len(zooms)>=2,zooms
assert all(r['gesture']=='two_hand_zoom' and r['action']=='zoom_in' and r['hand']=='Both' for r in zooms)
assert all(not(r['type']=='pointer' and r['phase'] in ('click','down','scroll')) for r in rows)
assert any('Обе руки' in r.get('feedback',{}).get('phase','') for r in rows if r['type']=='preview')
assert all(r['detected_hands']==2 for r in rows if r['type']=='preview')
print('PASS: real worker emits two-hand zoom, keeps both hand previews and suppresses individual clicks/scroll; no real camera/model/input.')
