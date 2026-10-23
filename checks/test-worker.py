"""Replay detector outputs through the real worker and preview JSON path."""
import contextlib,io,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core import room_gesture_worker as worker
from mediapipe.tasks.python import vision
palm=[(.500,.780),(.444,.716),(.388,.660),(.348,.612),(.316,.572),(.420,.588),(.396,.476),(.364,.364),(.332,.252),(.500,.572),(.508,.444),(.532,.316),(.556,.188),(.572,.604),(.580,.484),(.588,.372),(.596,.260),(.636,.636),(.660,.540),(.684,.444),(.708,.348)]
def points(offset=0,scale=1):return [S(x=.5+(x-.5)*scale+offset,y=.5+(y-.5)*scale,z=0.) for x,y in palm]
class Camera:
 def isOpened(self):return True
 def set(self,*args):return True
class Frames:
 def __init__(self,camera):self.sequence=0
 def read_after(self,*args):
  self.sequence+=1
  if self.sequence>4:raise KeyboardInterrupt
  return self.sequence,10.+self.sequence*.2,np.zeros((360,640,3),dtype=np.uint8)
 def close(self):pass
class Detector:
 def __init__(self):self.sequence=0
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def detect_for_video(self,*args):
  self.sequence+=1
  labels={1:['Right'],2:['Right','Left'],3:['Right','Right','Left','Left','Right','Left'],4:['Right','Left']*4}[self.sequence]
  return S(hand_landmarks=[points(-.35+.10*i,.35+.04*i) for i in range(len(labels))],handedness=[[S(category_name=h,score=.99)] for h in labels])
clock=iter(10.+i*.1 for i in range(1000));output=io.StringIO()
with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'DATA_DIR',Path(tmp)),patch.object(worker,'LatestFrame',Frames),patch('cv2.VideoCapture',return_value=Camera()),patch.object(vision.HandLandmarker,'create_from_options',return_value=Detector()),patch.object(worker.os,'nice'),patch.object(worker.time,'monotonic',side_effect=lambda:next(clock)),patch.object(sys,'argv',['worker','--model','unused.task']),patch.object(sys,'stdin',io.StringIO()),contextlib.redirect_stdout(output):
 try:worker.main()
 except KeyboardInterrupt:pass
rows=[json.loads(line) for line in output.getvalue().splitlines()]
previews=[r for r in rows if r['type']=='preview']
assert len(previews)==4,rows
assert all(r['image'] and r['hand'] for r in previews)
assert {len(r['feedback']['hands']) for r in previews}=={1,2}
assert [r['detected_hands'] for r in previews]==[1,2,6,8]
assert all(len(r['active_hands'])<=2 for r in previews)
assert all(set(r['active_hands'])=={'Right','Left'} for r in previews[1:])
assert all(r['feedback'] not in r['feedback']['hands'] for r in previews)
print('PASS: actual worker processes and serializes four frames with one/two/six/eight visible hands, at most two controllers and full landmark drawing; no camera or model inference.')
