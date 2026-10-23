"""Optional isolated camera worker; bounded latest-frame input and JSON IPC."""
import argparse,base64,json,sys,time,os,threading,queue,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.room_gesture_engine import GestureEngine,calibrated_profile
from core.room_gesture_rules import HandRules,read_settings
from core.room_hand_tracks import HandTracks,CONNECTIONS,MAX_HANDS
from core.room_paths import DATA_DIR

PREVIEW_INTERVAL = 1 / 30
_emit_lock = threading.RLock()


def browser_runtime_config(data):
 """Only a finite mode/span overlay may arrive through the local pipe."""
 mode=data.get('mode');span=data.get('span');revision=data.get('revision');distance=data.get('distance')
 if (mode not in (None,'analog','discrete','mouse','system_mouse') or type(revision) is not int or not 0<revision<2**53
     or (span is not None and (type(span) not in (int,float) or not math.isfinite(span) or not .12<=span<=.60))
     or (distance is not None and (type(distance) not in (int,float) or not math.isfinite(distance) or not .04<=distance<=.20))):
  raise ValueError('browser profile')
 return dict(mode=mode,span=span,revision=revision,distance=distance)


def runtime_settings(saved,overlay):
 """Overlay only browser timing/mode; never write or replace saved bindings."""
 config=dict(saved)
 if overlay:
  config['mode']=overlay['mode']
  if overlay['span'] is not None:config['analog_span']=overlay['span']
 return config


def runtime_distance(saved,overlay):
 value=overlay['distance'] if overlay and overlay.get('distance') is not None else saved
 return max(.04,min(.20,value)) if type(value) in (int,float) and math.isfinite(value) else .085


def emit(kind,**data):
 # Scene completion comes from its inference thread. Never interleave a JPEG
 # line and a presence line on the shared pipe.
 with _emit_lock:print(json.dumps(dict(type=kind,**data),ensure_ascii=False),flush=True)


class LatestFrame:
 """One replaceable frame, never a growing queue of old camera images."""
 def __init__(self,camera):
  self.camera=camera;self.condition=threading.Condition();self.stopping=threading.Event();self.latest=None;self.sequence=0;self.error=None
  self.thread=threading.Thread(target=self._capture,daemon=True,name='GestureLatestFrame');self.thread.start()
 def _capture(self):
  last_good=time.monotonic()
  try:
   while not self.stopping.is_set():
    ok,frame=self.camera.read();captured=time.monotonic()
    with self.condition:
     if not ok:
      if time.monotonic()-last_good<3:
       self.condition.wait(timeout=.04);continue
      self.error='Камера перестала передавать изображение.';self.condition.notify_all();return
     last_good=captured
     self.sequence+=1;self.latest=(self.sequence,captured,frame);self.condition.notify_all()
  except Exception:
   with self.condition:self.error='Не удалось получить изображение камеры.';self.condition.notify_all()
  finally:self.camera.release()
 def read_after(self,after,timeout=3.):
  with self.condition:
   ready=self.condition.wait_for(lambda:self.error or (self.latest is not None and self.latest[0]>after) or self.stopping.is_set(),timeout)
   if self.error:raise RuntimeError(self.error)
   if not ready or self.stopping.is_set():raise RuntimeError('Камера не передала новый кадр. Проверьте подключение.')
   return self.latest
 def close(self):
  self.stopping.set()
  with self.condition:self.condition.notify_all()
  self.thread.join(timeout=1.)


def main():
 p=argparse.ArgumentParser();p.add_argument('--camera',type=int,default=0);p.add_argument('--model',required=True);p.add_argument('--distance',type=float,default=.085);a=p.parse_args()
 if sys.platform!='win32':os.nice(5)
 os.environ.setdefault('OMP_NUM_THREADS','2')
 import cv2,mediapipe as mp
 cv2.setNumThreads(2)
 from mediapipe.tasks import python
 from mediapipe.tasks.python import vision
 options=vision.HandLandmarkerOptions(base_options=python.BaseOptions(model_asset_path=a.model),running_mode=vision.RunningMode.VIDEO,num_hands=MAX_HANDS,min_hand_detection_confidence=.65,min_hand_presence_confidence=.50,min_tracking_confidence=.50)
 camera=cv2.VideoCapture(a.camera,cv2.CAP_DSHOW if sys.platform=='win32' else cv2.CAP_AVFOUNDATION if sys.platform=='darwin' else cv2.CAP_ANY)
 if not camera.isOpened():camera.release();raise RuntimeError('Камера недоступна. Проверьте разрешение и закройте приложения, занявшие её.')
 camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,360);camera.set(cv2.CAP_PROP_FPS,30)
 # Driver hint plus latest-frame replacement: a slow inference cannot build lag.
 camera.set(cv2.CAP_PROP_BUFFERSIZE,1)
 frames=LatestFrame(camera)
 profile_path=DATA_DIR/'config/gesture-profile.json'
 try:profile=json.loads(profile_path.read_text(encoding='utf-8'))
 except (OSError,ValueError):profile=None
 engine=GestureEngine(distance=max(.04,min(.2,a.distance)),profile=profile);commands=queue.Queue(maxsize=3);calibration=None
 runtime_lock=threading.Lock();pending_runtime=None;runtime_overlay=None;runtime_revision=0
 def read_commands():
  nonlocal pending_runtime
  for line in sys.stdin:
   try:
    data=json.loads(line)
    if data.get('command')=='runtime_config':
     validated=browser_runtime_config(data)
     with runtime_lock:
      if pending_runtime is None or validated['revision']>=pending_runtime['revision']:pending_runtime=validated
    elif data.get('command') in ('calibrate','reload_rules'):commands.put_nowait(data['command'])
   except (ValueError,TypeError,AttributeError,queue.Full):pass
 threading.Thread(target=read_commands,daemon=True).start()
 router=HandRules(distance=max(.04,min(.2,a.distance)),profile=profile);rules_path=DATA_DIR/'config/gesture-actions.json';last_rules=0
 def reload_rules():
  from core.preferences import load_preferences
  router.set_distance(runtime_distance(load_preferences().get('room_gesture_distance',.085),runtime_overlay))
  router.configure(runtime_settings(read_settings(rules_path),runtime_overlay))
 tracks=HandTracks()
 last_stamp=0;started=time.monotonic();last_sequence=0;media_sequence=0
 next_preview=started+PREVIEW_INTERVAL/2
 stats_start=started;stats_count=0;stats_capture=0;stats_detect=stats_prep=stats_preview=0.;stats_skipped=0
 try:
  with vision.HandLandmarker.create_from_options(options) as detector:
   emit('status',text='Камера включена. Сомкните три пальца и потяните. Неподвижная открытая ладонь — пауза / воспроизведение.')
   while True:
    sequence,captured,frame=frames.read_after(last_sequence)
    stats_skipped+=max(0,sequence-last_sequence-1);last_sequence=sequence
    cycle=time.monotonic();prep_start=cycle
    frame=cv2.flip(frame,1)
    if frame.shape[1]!=640 or frame.shape[0]!=360:frame=cv2.resize(frame,(640,360))
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);prep_end=time.monotonic()
    stamp=max(last_stamp+1,int((captured-started)*1000));last_stamp=stamp
    result=detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb),stamp)
    detect_end=time.monotonic()
    detections=[(landmarks,result.handedness[index][0].category_name,result.handedness[index][0].score)
                for index,landmarks in enumerate(result.hand_landmarks) if index<len(result.handedness) and result.handedness[index]]
    tracked=tracks.update(detections,captured)
    for side in tracks.changed:router.reset_hand(side)
    closest=max((h for h in tracks.visible if h.active),key=lambda h:h.size,default=None)
    points=closest.landmarks if closest else None
    hand=closest.side if closest else None
    with runtime_lock:
     requested,pending_runtime=pending_runtime,None
    if requested is not None and requested['revision']>=runtime_revision:
     runtime_revision=requested['revision'];runtime_overlay=requested if requested['mode'] is not None else None
     reload_rules();last_rules=cycle
     emit('profile_applied',revision=runtime_revision,mode=router.config['mode'])
    try:
     while True:
      command=commands.get_nowait()
      if command=='calibrate':
       calibration={'stage':'open','start':cycle,'open':[],'closed':[]};engine.reset();engine.require_media_release()
      elif command=='reload_rules':reload_rules();last_rules=cycle
    except queue.Empty:pass
    if calibration is not None:
     if 'track_id' not in calibration:calibration['track_id']=closest.identity if closest else None
     chosen=next((h for h in tracks.visible if h.identity==calibration['track_id']),None)
     points=chosen.landmarks if chosen else None;hand=chosen.side if chosen else None
    event=engine.update(points,captured,hand,allow_media=False);calibration_text=''
    if cycle-last_rules>1:
     reload_rules();last_rules=cycle
    actions=router.take_pending();seen=set();feedbacks=[]
    for side,landmarks in tracked:
     seen.add(side)
     fresh=router.config['mode']=='discrete' or 0<=detect_end-captured<=.25
     action=router.update(landmarks,captured,side,allow_actions=calibration is None and fresh)
     feedbacks.append(dict(router.feedback))
     if action:actions.extend(action if isinstance(action,list) else [action])
    for side in ('Right','Left'):
     if side not in seen:
      action=router.update(None,captured,side,allow_actions=calibration is None)
      if action:actions.extend(action if isinstance(action,list) else [action])
    if router.config['mode'] in ('mouse','system_mouse'):
     if router.mouse.point_ready:
      source_side=router.config['mouse_hand']
      if router.config['swap_hands']:source_side='Left' if source_side=='Right' else 'Right'
      tracks.lock_side(source_side)
    else:tracks.clear_locks()
    if feedbacks and calibration is None:
     # Show the hand doing a gesture, not whichever detection happened to be last.
     # Copy the selected hand before adding the list: otherwise the list
     # contains this very dict and JSON serialization kills the camera worker.
     engine.feedback=dict(max(feedbacks,key=lambda f: (float(f.get('media_progress',0)),bool(f.get('corner_armed')),bool(f.get('grip')))))
     engine.feedback['hands']=feedbacks
    if calibration is not None:
     c=calibration;elapsed=cycle-c['start']
     calibration_text=('Покажите раскрытую ладонь' if c['stage']=='open' else 'Сведите три пальца в захват и удерживайте')+' · '+str(max(1,5-int(elapsed)))+' с'
     if points and elapsed>1:c[c['stage']].append(dict(engine.feedback))
     if elapsed>=5:
      if c['stage']=='open':
       if len(c['open'])<12:
        emit('calibration',text='Не вижу устойчивую руку. Повторите обучение в хорошем освещении.');calibration=None;engine.reset();engine.require_media_release()
       else:c['stage']='closed';c['start']=cycle
      else:
       try:
        profile=calibrated_profile(c['open'],c['closed']);profile_path.parent.mkdir(parents=True,exist_ok=True);profile_path.write_text(json.dumps(profile),encoding='utf-8');profile_path.chmod(0o600)
        engine=GestureEngine(distance=max(.04,min(.2,a.distance)),profile=profile);emit('calibration',text='Захват настроен. Сомкните три пальца и потяните. Для ладони-паузы сначала опустите руку.')
       except ValueError as error:emit('calibration',text=str(error))
       calibration=None;engine.reset();engine.require_media_release();router=HandRules(distance=max(.04,min(.2,a.distance)),profile=profile);reload_rules()
       for hand_engine in router.engines.values():hand_engine.require_media_release()
    for side,gesture,action in actions:
     payload=action if isinstance(action,dict) else {'action':action}
     drag=payload.get('action')=='drag_scroll';pointer=payload.get('action')=='pointer'
     if calibration is not None and not (drag and payload.get('phase') in ('end','cancel')):continue
     media_sequence+=1;emit('pointer' if pointer else 'drag_scroll' if drag else 'action',**payload,id=media_sequence,hand=side,gesture=gesture,mode=router.config['mode'],profile_revision=runtime_revision,captured_monotonic=detect_end if drag and payload.get('phase')=='cancel' else captured)
    preview_start=time.monotonic()
    if cycle>=next_preview:
     # Keep a clock phase instead of restarting the interval on every frame.
     # Otherwise small timing jitter turns a 30 FPS source into ~20 FPS.
     next_preview+=(int((cycle-next_preview)/PREVIEW_INTERVAL)+1)*PREVIEW_INTERVAL
     for visible_hand in tracks.visible:
      side,landmarks=visible_hand.side,visible_hand.landmarks
      active=visible_hand.active
      actual=('Left' if side=='Right' else 'Right') if router.config['swap_hands'] else side
      colour=((125,220,70) if actual=='Right' else (235,170,80)) if active else (125,135,140)
      xy=[(int(p.x*640),int(p.y*360)) for p in landmarks]
      for first,second in CONNECTIONS:cv2.line(frame,xy[first],xy[second],colour,2 if active else 1,cv2.LINE_AA)
      for index,point in enumerate(xy):cv2.circle(frame,point,(5 if index in (0,4,8,12,16,20) else 3) if active else 2,colour,-1,cv2.LINE_AA)
      centre=tuple(round(sum(xy[i][axis] for i in (0,5,9,13,17))/5) for axis in (0,1))
      cv2.circle(frame,centre,5,(255,255,255),-1,cv2.LINE_AA)
      cv2.putText(frame,actual+(' ACTIVE' if active else '')+' #'+str(visible_hand.identity),(xy[0][0]-20,xy[0][1]+22),cv2.FONT_HERSHEY_SIMPLEX,.6,colour,2,cv2.LINE_AA)
     thumb=frame;ok,jpg=cv2.imencode('.jpg',thumb,[cv2.IMWRITE_JPEG_QUALITY,65])
     if ok:emit('preview',image=base64.b64encode(jpg).decode('ascii'),hand=bool(points),feedback=engine.feedback,calibration=calibration_text,detected_hands=len(tracks.visible),active_hands=[('Left' if side=='Right' else 'Right') if router.config['swap_hands'] else side for side,_ in tracked],pointer_diagnostics=router.mouse.tracking_snapshot() if router.config['mode'] in ('mouse','system_mouse') else {})
    finished=time.monotonic();stats_count+=1;stats_prep+=prep_end-prep_start;stats_detect+=detect_end-prep_end;stats_preview+=finished-preview_start
    if finished-stats_start>=2:
     span=finished-stats_start;capture_sequence=frames.sequence
     emit('performance',fps=round(stats_count/span,1),capture_fps=round((capture_sequence-stats_capture)/span,1),detection_ms=round(stats_detect*1000/stats_count,1),preparation_ms=round(stats_prep*1000/stats_count,1),preview_ms=round(stats_preview*1000/stats_count,1),skipped=stats_skipped)
     stats_start=finished;stats_capture=capture_sequence;stats_count=0;stats_detect=stats_prep=stats_preview=0.;stats_skipped=0
 finally:
  for side in ('Right','Left'):
   packet=router.scroll[side].finish('cancel')
   if packet:
    media_sequence+=1;emit('drag_scroll',**packet,id=media_sequence,hand=side,gesture='grab_scroll',mode=router.config['mode'],profile_revision=runtime_revision,captured_monotonic=time.monotonic())
  frames.close()


if __name__=='__main__':
 if sys.stdout:sys.stdout.reconfigure(encoding='utf-8')
 try:main()
 except (BrokenPipeError,KeyboardInterrupt):pass
 except Exception as error:emit('error',text=str(error)[:240]);sys.exit(1)
