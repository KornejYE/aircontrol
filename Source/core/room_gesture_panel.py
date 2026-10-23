"""Camera opt-in, isolated tracking process and a readable local preview."""
import base64,json,math,os,re,subprocess,sys,threading,time
from collections import deque
from pathlib import Path
from PyQt6.QtCore import QObject,pyqtSignal,Qt,QTimer
from PyQt6.QtGui import QFont,QPixmap,QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSpinBox,QSlider,QScrollArea,QWidget,QCheckBox,QComboBox,QTabWidget,QFormLayout
from core.room_paths import DATA_DIR
from core.room_gesture_relay import Relay,BROWSER_ACTIONS
from core.preferences import load_preferences,save_preferences
ROOT=Path(__file__).resolve().parents[2]
class GestureController(QObject):
 message=pyqtSignal(dict)
 request_signal=pyqtSignal(object)
 def __init__(self,parent):
  super().__init__(parent);self.process=None;self.relay=None;self.epoch=0;self.status='Камера выключена';self.frame=None;self.last_gesture='Последний жест: пока нет';self.performance='';self._last_media_id=0;self._calibrating=False;self.ready=False;self.ready_event=threading.Event();self.browser_media=bool(load_preferences().get('room_gestures_browser_media',False));self.message.connect(self.receive);self.request_signal.connect(self.execute)
  from core.room_gesture_rules import read_settings
  config=read_settings(DATA_DIR/'config/gesture-actions.json');self.control_mode=config['mode'];self.analog_span=config.get('analog_span',.20)
  value=load_preferences().get('room_gesture_distance',.085)
  self.discrete_distance=max(.04,min(.2,value)) if type(value) in (int,float) and math.isfinite(value) else .085
  self._drag_stream=None;self._drag_seen=deque(maxlen=64);self._drag_after=0.;self._drag_captured=0.
  self._pointer_error='';self._pointer_native=None;self._pointer_motion=None;self._pointer_at=0.;self._pointer_captured=0.;self._pointer_id=0;self._pointer_diagnostics={}
  self._pointer_timer=QTimer(self);self._pointer_timer.setInterval(16);self._pointer_timer.setTimerType(Qt.TimerType.PreciseTimer);self._pointer_timer.timeout.connect(self.tick_pointer)
  self._browser_mode=None;self._browser_revision=0;self._worker_profile_ready=True
  self._camera_lease=None
  self._browser_timer=QTimer(self);self._browser_timer.setInterval(50);self._browser_timer.timeout.connect(self.poll_browser_profile);self._browser_timer.start()
 @property
 def effective_mode(self):return self._browser_mode or self.control_mode
 def release_pointer(self):
  if getattr(self,'_pointer_timer',None):self._pointer_timer.stop()
  if getattr(self,'_pointer_motion',None):self._pointer_motion.reset()
  if self._pointer_native:self._pointer_native.cancel()
  self._pointer_at=0.;self._pointer_captured=0.
 def tick_pointer(self):
  if (self.effective_mode!='system_mouse' or not self.ready or self._calibrating
      or self.process is None or not self._pointer_at
      or not 0<=time.monotonic()-self._pointer_at<=.12
      or not 0<=time.monotonic()-self._pointer_captured<=.30):
   self.release_pointer();return
  try:
   self._pointer_motion.tick()
   if not self._pointer_motion.pending:self._pointer_timer.stop()
  except Exception as error:
   self.release_pointer();self._pointer_error=str(error);self.last_gesture=str(error)
 def poll_browser_profile(self):
  if self._pointer_native and self._pointer_native.check_escape():self._pointer_error='Мышь остановлена клавишей Esc. Выключите и снова включите управление.'
  if self._pointer_at and time.monotonic()-self._pointer_at>.35:self.release_pointer()
  if self.relay is None or self.process is None:return
  profile=self.relay.browser_profile();revision=profile['revision']
  if revision==self._browser_revision:return
  self.release_pointer();self._clear_drag();self._browser_revision=revision;self._browser_mode=profile['mode'];self._worker_profile_ready=False
  command=dict(command='runtime_config',mode=profile['mode'],span=profile['span'],revision=revision)
  if profile.get('distance') is not None:command['distance']=profile['distance']
  try:self.worker_command(command)
  except Exception as error:self.status='Режим браузера не применён: '+str(error)
 def current_profile_event(self,data):
  if self.relay is not None and self.relay.browser_profile()['revision']!=self._browser_revision:return False
  return self._worker_profile_ready and (self._browser_revision==0 or data.get('profile_revision')==self._browser_revision)
 def ensure_relay(self):
  if self.relay is not None:return self.relay
  relay=Relay(port=8767);relay.camera_control=self.browser_camera;relay.camera_mode=self.browser_mouse_mode;relay.camera_status=self.camera_snapshot
  try:relay.start()
  except OSError:raise RuntimeError('Порт жестов 8767 занят. Закройте вторую копию AirControl.') from None
  self.relay=relay;return relay
 def browser_mouse_mode(self,mode):
  request={'action':'mode_'+mode,'done':threading.Event()};self.request_signal.emit(request)
  if not request['done'].wait(3):return dict(ok=False,error='Интерфейс занят.')
  return dict(ok=not bool(request.get('error')),error=request.get('error',''))
 def camera_snapshot(self):
  process=self.process;running=process is not None and process.poll() is None
  ready=running and self.ready
  return dict(pointer_error=self._pointer_error,mode=self.effective_mode,running=running,ready=ready,state='on' if ready else 'starting' if running else 'off',tracking=self._pointer_diagnostics,physical_pauses=getattr(self._pointer_native,'physical_pauses',0),physical_pause=bool(self._pointer_native and self._pointer_native.paused_until>time.monotonic()),performance=self.performance)
 def browser_camera(self,enabled):
  request={'action':'browser_on' if enabled else 'browser_off','done':threading.Event()}
  self.request_signal.emit(request)
  if not request['done'].wait(3):return dict(ok=False,error='Интерфейс занят. Попробуйте снова.')
  if request.get('error'):return dict(ok=False,error=request['error'])
  if enabled:
   self.ready_event.wait(6)
   if not self.ready:return dict(ok=False,error='Камера ещё не готова: '+self.status)
  return dict(ok=True,camera=self.ready)
 def shutdown(self):
  self.stop()
  if self.relay:self.relay.stop();self.relay=None
 def start(self,camera=None):
  if self.process is not None:return
  if camera is None:camera=int(load_preferences().get('room_gesture_camera',0))
  self.ready=False;self.ready_event.clear();self.status='Запускаю распознавание руки…';self.performance='';self._last_media_id=0;self._calibrating=False;self._pointer_diagnostics={}
  self._clear_drag()
  runtime=Path(sys.executable)
  model=ROOT/'Models/gestures/hand_landmarker.task'
  if not runtime.exists() or not model.exists():raise RuntimeError('Модуль камеры не установлен. Запустите «Установить жесты» из папки приложения.')
  relay=self.ensure_relay()
  from core.room_camera_lease import CameraLease
  lease=CameraLease(camera,'AirControl').acquire()
  logs=DATA_DIR/'State';logs.mkdir(parents=True,exist_ok=True)
  self.epoch+=1;epoch=self.epoch
  try:
   with open(logs/'camera.log','a') as log:
    self.process=subprocess.Popen([str(runtime),'-u',str(Path(__file__).with_name('room_gesture_worker.py')),'--model',str(model),'--camera',str(camera),'--distance',str(load_preferences().get('room_gesture_distance',.085))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1,creationflags=0x08004000 if sys.platform=='win32' else 0)
  except Exception:lease.release();raise
  self._camera_lease=lease
  self.relay=relay;process=self.process
  def reader():
   for line in process.stdout:
    if epoch!=self.epoch:break
    try:data=json.loads(line)
    except ValueError:continue
    if data.get('type')=='gesture' and data.get('direction') in ('up','down','left','right'):relay.publish(data['direction'])
    data['_epoch']=epoch;data['_received_monotonic']=time.monotonic();self.message.emit(data)
   process.wait()
   if epoch==self.epoch:self.message.emit({'type':'ended','text':'Камера остановлена. Подробности: camera.log.','_epoch':epoch})
  threading.Thread(target=reader,daemon=True,name='GestureCameraIPC').start()
 def receive(self,data):
  if data.get('_epoch',self.epoch)!=self.epoch:return
  kind=data.get('type')
  if kind in ('action','media','drag_scroll') and '_received_monotonic' in data:
   received=data['_received_monotonic']
   if not isinstance(received,(int,float)) or not 0<=time.monotonic()-received<=1.2:return
  if kind=='profile_applied':
   if (type(data.get('revision')) is int and data['revision']==self._browser_revision
       and data.get('mode')==self.effective_mode):
    self._worker_profile_ready=True
    if self.relay:self.relay.acknowledge_browser_profile(data['revision'])
  elif kind=='status':self.status=data.get('text','');self.ready=True;self.ready_event.set()
  elif kind=='preview':
   diagnostic=data.get('pointer_diagnostics',{})
   if isinstance(diagnostic,dict):
    self._pointer_diagnostics={key:diagnostic[key] for key in ('missing_frames','recoveries','tracking_resets','time_gaps','fist_stops') if type(diagnostic.get(key)) is int and 0<=diagnostic[key]<2**53}
    if diagnostic.get('pose') in ('none','point','pinch','scroll','scroll_grab','fist','context','idle'):self._pointer_diagnostics['pose']=diagnostic['pose']
    self._pointer_diagnostics.update(recovering=diagnostic.get('recovering') is True)
   if data.get('calibration'):self.status=data['calibration']
   elif self.effective_mode in ('mouse','system_mouse'):self.status=data.get('feedback',{}).get('phase','Мышь рукой: покажите выбранную руку')
   elif not data.get('hand'):self.status='Рука не видна — команды не выполняются.'
   elif data.get('feedback',{}).get('palm'):self.status=data['feedback'].get('side','Рука')+'. '+data['feedback'].get('phase','Держите ладонь неподвижно 1 с.')
   elif data.get('feedback',{}).get('grip'):self.status='Захват обнаружен — потяните руку.'
   else:self.status=data.get('feedback',{}).get('side','Рука')+'. '+data.get('feedback',{}).get('phase','Соедините три пальца.')
   if type(data.get('detected_hands')) is int:
    self.status+=' · Рук в кадре: '+str(data['detected_hands'])+'; управляют ближайшие правая и левая.'
  elif kind=='gesture':self.last_gesture='Последний жест: '+{'up':'вверх ↑','down':'вниз ↓','left':'влево ←','right':'вправо →'}.get(data.get('direction'),'')
  elif kind=='drag_scroll':
   event_id=data.get('id')
   if type(event_id) is not int or event_id<=self._last_media_id:return
   self._last_media_id=event_id
   if not self.ready or self.process is None or self._calibrating or self.effective_mode!='analog' or data.get('mode')!='analog' or self.relay is None or not self.current_profile_event(data):return
   hand=data.get('hand');gesture_id=data.get('gesture_id');phase=data.get('phase');position=data.get('position');captured=data.get('captured_monotonic')
   if (hand not in ('Right','Left') or not isinstance(gesture_id,str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,96}',gesture_id)
       or phase not in ('start','move','end','cancel') or type(position) not in (int,float) or not math.isfinite(position) or not -8<=position<=8
       or type(captured) not in (int,float) or not math.isfinite(captured) or not 0<=time.monotonic()-captured<=.30 or captured<max(self._drag_after,self._drag_captured)):return
   key=(hand,gesture_id);stream=self._drag_stream
   # A dropped terminal packet must not permanently latch a hand. Stationary
   # drags send absolute-position heartbeats every100ms; 400ms is a lost stream.
   if stream is not None and time.monotonic()-stream['captured']>.4:
    try:self.relay.publish_drag(hand=stream['key'][0],gesture_id=stream['key'][1],phase='cancel',position=stream['position'])
    except Exception:pass
    self._drag_stream=None;stream=None
   if phase=='start':
    if stream is not None or key in self._drag_seen or position!=0:return
   elif (stream is None or stream['key']!=key or captured<stream['captured']
         or (phase in ('end','cancel') and not math.isclose(position,stream['position'],abs_tol=1e-6))):return
   try:
    self.relay.publish_drag(hand=hand,gesture_id=gesture_id,phase=phase,position=position)
    if phase=='start':self._drag_seen.append(key)
    self._drag_stream=None if phase in ('end','cancel') else dict(key=key,captured=captured,position=position)
    self._drag_captured=captured
    self.last_gesture=('Правая' if hand=='Right' else 'Левая')+' · '+('Прокрутка завершена' if phase=='end' else 'Прокрутка отменена' if phase=='cancel' else 'Тянете страницу рукой')
   except Exception as error:self.last_gesture='Прокрутка не отправлена: '+str(error)
  elif kind=='pointer':
   from core.room_air_mouse import valid_pointer
   event_id=data.get('id');captured=data.get('captured_monotonic')
   if (type(event_id) is not int or event_id<=self._pointer_id or not valid_pointer(data)
       or not self.ready or self.process is None or self._calibrating
       or self.effective_mode not in ('mouse','system_mouse') or data.get('mode')!=self.effective_mode
       or not self.current_profile_event(data) or type(captured) not in (int,float)
       or not 0<=time.monotonic()-captured<=.30):return
   self._pointer_id=event_id;self._pointer_at=time.monotonic();self._pointer_captured=captured
   packet={key:data[key] for key in ('action','phase','x','y','dy','reason','absolute','relative_x','relative_y') if key in data}
   try:
    if self.effective_mode=='mouse':
     if self.relay:self.relay.publish_pointer(packet)
    else:
     if self._pointer_native is None:
      from core.room_air_mouse_native import NativeAirMouse
      from core.room_pointer_motion import PointerMotion
      self._pointer_native=NativeAirMouse()
      self._pointer_motion=PointerMotion(self._pointer_native.send)
     self._pointer_motion.submit(packet)
     if self._pointer_motion.pending and not self._pointer_timer.isActive():self._pointer_timer.start()
     elif not self._pointer_motion.pending:self._pointer_timer.stop()
    self._pointer_error='';self.last_gesture='Мышь рукой · '+data['phase']
   except Exception as error:self.release_pointer();self._pointer_error=str(error);self.last_gesture=str(error)
  elif kind=='action':
   event_id=data.get('id');action=data.get('action')
   from core.room_gesture_rules import ACTIONS
   if type(event_id) is not int or event_id<=self._last_media_id or action not in ACTIONS or action=='none':return
   self._last_media_id=event_id
   if not self.ready or self.process is None or self._calibrating or not self.current_profile_event(data):return
   if data.get('mode',self.effective_mode)!=self.effective_mode:return
   try:
    if 'swipe_steps' in data:
     count=data['swipe_steps'];captured=data.get('captured_monotonic')
     if (self.effective_mode!='discrete' or action not in ('up','down','left','right','volume_up','volume_down')
         or data.get('continuous') is True or type(count) is not int or not 1<=count<=4
         or type(captured) not in (int,float) or not math.isfinite(captured)
         or not 0<=time.monotonic()-captured<=.30):return
     if action in ('volume_up','volume_down') and not (self.browser_media or self._browser_mode is not None):
      from core.room_media_keys import dispatch_action
      for _ in range(count):dispatch_action(action)
     elif self.relay:self.relay.publish(action,swipe_steps=count)
    elif data.get('continuous') is True:
     from core.room_gesture_analog import valid_amount
     captured=data.get('captured_monotonic');steps=data.get('steps',0)
     if (self.effective_mode!='analog' or not valid_amount(action,data.get('amount'))
         or type(steps) is not int or not 0<=steps<=4 or type(captured) not in (int,float)
         or not 0<=time.monotonic()-captured<=.30):return
     # Continuous deltas belong only to the selected browser target. Never send
     # repeated global media keys to the game or another foreground application.
     if self.relay:self.relay.publish(action,amount=data['amount'],steps=steps)
    elif action in ('up','down','left','right') or ((self.browser_media or self._browser_mode is not None) and action in BROWSER_ACTIONS):
     if self.relay:self.relay.publish(action)
    else:
     from core.room_media_keys import dispatch_action
     dispatch_action(action)
    side='Правая' if data.get('hand')=='Right' else 'Левая'
    self.last_gesture=side+' · '+ACTIONS[action]
   except Exception as error:self.last_gesture='Не удалось выполнить: '+str(error)
  elif kind=='media':
   event_id=data.get('id')
   if data.get('action')!='play_pause' or type(event_id) is not int or event_id<=self._last_media_id:return
   self._last_media_id=event_id
   if not self.ready or self.process is None or self._calibrating or not self.current_profile_event(data):return
   try:
    if self.browser_media or self._browser_mode is not None:
     if self.relay:self.relay.publish('play_pause')
    else:
     from core.room_media_keys import toggle_play_pause
     toggle_play_pause()
    self.last_gesture='Последний жест: пауза / воспроизведение'
   except Exception as error:self.last_gesture='Медиакоманда не отправлена: '+str(error)
  elif kind=='performance':
   fps=data.get('fps')
   if isinstance(fps,(int,float)) and 0<=fps<1000:self.performance=f'Распознавание: {fps:g} кадров/с'
  elif kind=='calibration':self._calibrating=False;self.last_gesture=data.get('text','')
  elif kind in ('error','ended'):
   self.stop();self.status=data.get('text','Камера остановлена.');self.ready_event.set()
 def execute(self,request):
  try:
   action=request['action']
   if action=='browser_on':self.start()
   elif action=='browser_off':self.stop()
   elif action=='off':self.stop();save_preferences(room_gestures_autostart=False)
   elif action in ('on','always_on'):
    self.start()
    if action=='always_on':save_preferences(room_gestures_autostart=True)
   elif action=='always_off':save_preferences(room_gestures_autostart=False)
   elif action in ('mode_analog','mode_discrete','mode_mouse','mode_system_mouse','mode_restore'):self.set_mode(action.removeprefix('mode_'))
   elif action!='status':raise ValueError('Неизвестная команда жестов.')
   request['result']=self.status
  except Exception as error:request['error']=str(error)
  finally:request['done'].set()
 def request(self,action):
  request={'action':action,'done':threading.Event()};self.request_signal.emit(request)
  if not request['done'].wait(3):return 'Интерфейс пока занят. Команда жестов не подтверждена.'
  if request.get('error'):return 'Жесты не удалось включить: '+request['error']
  if action in ('on','always_on'):
   self.ready_event.wait(6)
   if not self.ready:return 'Камера ещё не готова: '+self.status
   target='выбранной вкладкой расширения' if self.browser_media else 'системным проигрывателем'
   return 'Режим жестов включён. '+('Выбор сохранён: камера будет запускаться вместе с AirControl. ' if action=='always_on' else '')+'Видеоряд остаётся локальным. Направления управляют выбранной вкладкой расширения; ладонь и громкость — '+target+'.'
  if action=='off':return 'Жесты и камера выключены. Автоматический запуск тоже отключён.'
  if action=='always_off':return 'Автоматический запуск жестов отключён. Текущий режим камеры сохранён.'
  if action in ('mode_analog','mode_discrete','mode_mouse','mode_system_mouse','mode_restore'):return ('Аналоговое управление: страница следует за движением руки. Размах на одно видео настраивается ползунком; неподвижная кисть не продолжает прокрутку.' if action=='mode_analog' else 'Обычное управление: короткий мах переключает один ролик, длинный — несколько. Удержание руки на месте не листает.')+(' Камера включена.' if self.ready else ' Чтобы управлять, включите камеру.')
  return ('Камера включена. ' if self.ready else 'Камера выключена или запускается. ')+self.status+(' Автозапуск включён.' if load_preferences().get('room_gestures_autostart') else ' Автозапуск выключен.')
 def tracking_command(self,command):
  self.worker_command({'command':command})
 def worker_command(self,command):
  if not self.process or self.process.poll() is not None:raise RuntimeError('Сначала включите камеру.')
  self.process.stdin.write(json.dumps(command)+'\n');self.process.stdin.flush()
 def set_mode(self,mode):
  self.release_pointer();self._pointer_native=None;self._pointer_error=''
  from core.room_gesture_rules import read_settings,save_settings
  path=DATA_DIR/'config/gesture-actions.json';config=read_settings(path)
  if mode=='restore':mode=config.get('mouse_return_mode','discrete')
  if mode in ('mouse','system_mouse') and config['mode'] not in ('mouse','system_mouse'):config['mouse_return_mode']=config['mode']
  config['mode']=mode if mode in ('analog','mouse','system_mouse') else 'discrete';save_settings(path,config)
  self.control_mode=config['mode']
  self.reload_rules()
 def _clear_drag(self):
  self._drag_stream=None;self._drag_seen.clear();self._drag_after=time.monotonic();self._drag_captured=self._drag_after
 def reload_rules(self):
  self.release_pointer();self._clear_drag()
  if self.relay:self.relay.invalidate()
  if self.process and self.process.poll() is None:self.tracking_command('reload_rules')
 def set_analog_span(self,value):
  if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Некорректный размах движения.')
  from core.room_gesture_rules import read_settings,save_settings
  path=DATA_DIR/'config/gesture-actions.json';config=read_settings(path)
  self.analog_span=max(.12,min(.60,value));config['analog_span']=self.analog_span;save_settings(path,config)
  self.reload_rules()
 def set_discrete_distance(self,value):
  if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Некорректный размах движения.')
  self.discrete_distance=max(.04,min(.20,value));save_preferences(room_gesture_distance=self.discrete_distance)
  self.reload_rules()
 def calibrate(self):
  if not self.process or self.process.poll() is not None:raise RuntimeError('Сначала включите камеру.')
  self._calibrating=True
  self._clear_drag()
  if self.relay:self.relay.invalidate()
  try:self.process.stdin.write(json.dumps({'command':'calibrate'})+'\n');self.process.stdin.flush()
  except Exception:self._calibrating=False;raise
 def stop(self):
  self.release_pointer();self._pointer_native=None;self._pointer_error='';self._pointer_id=0
  self.epoch+=1;process=self.process;self.process=None;self.ready=False;self.performance='';self._calibrating=False
  self._clear_drag()
  if process:
   try:process.terminate();process.wait(timeout=3)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
   except OSError:pass
  if self._camera_lease:self._camera_lease.release();self._camera_lease=None
  if self.relay:self.relay.invalidate()
  self._browser_mode=None;self._browser_revision=0;self._worker_profile_ready=True
  self.frame=None;self.status='Камера выключена'
class GesturePanel(QDialog):
 def __init__(self,parent):
  super().__init__(parent)
  from core.room_shell import BUTTON,BG,PANEL,EDGE,CYAN,TEXT,DIM
  from PyQt6.QtWidgets import QFrame,QSizePolicy
  self.setObjectName('GesturePanel');self.setWindowTitle('AirControl • Жесты');self.resize(860,700);self.setMinimumSize(620,520)
  self.setStyleSheet(f'''QDialog#GesturePanel,QWidget#GestureContent{{background:{BG};color:{TEXT};font:17px Arial;}}
QLabel{{color:{TEXT};background:transparent;border:0;font:17px Arial;}}
QFrame#GestureCard{{background:{PANEL};border:1px solid {EDGE};border-radius:18px;}}
QScrollArea{{border:0;background:transparent;}} QScrollBar:vertical{{background:transparent;width:7px;margin:5px 0;}} QScrollBar::handle:vertical{{background:#24505f;border-radius:3px;min-height:32px;}} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
QComboBox{{background:#0b2530;color:{TEXT};border:1px solid #24505f;border-radius:8px;padding:7px;font:16px Arial;}} QComboBox QAbstractItemView{{background:#0b2530;color:{TEXT};selection-background-color:#075064;}}
QSpinBox{{background:#0b2530;color:{TEXT};border:1px solid #24505f;border-radius:10px;padding:8px 12px;font:18px Arial;min-height:28px;}}
QCheckBox{{color:{TEXT};font:17px Arial;spacing:12px;padding:7px 0;}} QCheckBox::indicator{{width:21px;height:21px;background:#181e21;border:1px solid #36616d;border-radius:6px;}} QCheckBox::indicator:checked{{background:#009fbb;border-color:{CYAN};}}
QSlider::groove:horizontal{{height:6px;background:#163d49;border-radius:3px;}} QSlider::sub-page:horizontal{{background:#008da8;border-radius:3px;}} QSlider::handle:horizontal{{width:20px;margin:-7px 0;background:{CYAN};border-radius:10px;}}
'''+BUTTON+f'QPushButton#GesturePrimary{{background:#075064;color:{TEXT};border-color:#00a8c8;}} QPushButton:focus{{border:2px solid {CYAN};}} QSpinBox:focus{{border-color:{CYAN};}}')
  self.setStyleSheet(self.styleSheet()+f'QTabWidget::pane{{border:0;}} QTabBar::tab{{background:{BG};color:{DIM};padding:11px 16px;border-bottom:2px solid transparent;font:16px Arial;}} QTabBar::tab:selected{{color:{CYAN};border-bottom-color:{CYAN};}}')
  outer=QVBoxLayout(self);outer.setContentsMargins(24,24,24,18);outer.setSpacing(18)
  header=QHBoxLayout();heading=QVBoxLayout();heading.setSpacing(7)
  eyebrow=QLabel('ДЖАРВИС  /  УПРАВЛЕНИЕ');eyebrow.setStyleSheet(f'color:{DIM};font-size:12px;font-weight:600;');heading.addWidget(eyebrow)
  title=QLabel('Жесты без касаний');title.setStyleSheet('font-size:28px;font-weight:600;');heading.addWidget(title)
  subtitle=QLabel('Переключайте видео и прокручивайте страницы движением руки.');subtitle.setWordWrap(True);subtitle.setStyleSheet(f'color:{DIM};font-size:16px;');heading.addWidget(subtitle)
  header.addLayout(heading,1);done=QPushButton('Готово');done.setAutoDefault(False);done.setAccessibleName('Закрыть настройки жестов');done.clicked.connect(self.close);header.addWidget(done,0,Qt.AlignmentFlag.AlignTop);outer.addLayout(header)
  scroll=QScrollArea();self.scroll=scroll;scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setAccessibleName('Настройки управления жестами')
  content=QWidget();content.setObjectName('GestureContent');scroll.setWidget(content)
  self.pages=QTabWidget();self.pages.setAccessibleName('Разделы управления жестами');self.pages.addTab(scroll,'Камера и настройки');outer.addWidget(self.pages,1)
  layout=QVBoxLayout(content);layout.setContentsMargins(0,0,12,0);layout.setSpacing(16);self._settings_cards={}
  def card(title,description=None):
   frame=QFrame();frame.setObjectName('GestureCard');box=QVBoxLayout(frame);box.setContentsMargins(20,20,20,20);box.setSpacing(14)
   name=QLabel(title);name.setStyleSheet('font-size:20px;font-weight:600;');box.addWidget(name)
   if description:
    note=QLabel(description);note.setWordWrap(True);note.setStyleSheet(f'color:{DIM};font-size:16px;');box.addWidget(note)
   layout.addWidget(frame);self._settings_cards[title]=frame;return box
  def action(text,callback,primary=False):
   button=QPushButton(text);button.setAutoDefault(False);button.setMinimumHeight(46);button.setAccessibleName(text)
   if primary:button.setObjectName('GesturePrimary')
   button.clicked.connect(callback);return button
  camera_box=card('Камера','Показаны до 8 рук: 21 точка и центр каждой ладони. Управляют самая крупная правая и левая — они яркие и помечены ACTIVE. Остальные руки серые. Зеркальное превью: Right — правая, Left — левая.')
  self.preview=QLabel('Камера выключена\nИзображение появится после включения');self.preview.setWordWrap(True);self.preview.setFixedHeight(240);self.preview.setMinimumWidth(0);self.preview.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setAccessibleName('Локальное изображение камеры');self.preview.setStyleSheet(f'background:{BG};color:{DIM};border:1px solid {EDGE};border-radius:12px;font-size:16px;');camera_box.addWidget(self.preview)
  row=QHBoxLayout();row.setSpacing(12);camera_label=QLabel('Номер камеры');row.addWidget(camera_label)
  self.camera=QSpinBox();self.camera.setRange(0,9);self.camera.setValue(int(load_preferences().get('room_gesture_camera',0)));self.camera.setMaximumWidth(110);self.camera.setAccessibleName('Номер камеры для жестов');camera_label.setBuddy(self.camera);self.camera.valueChanged.connect(lambda v:save_preferences(room_gesture_camera=v));row.addWidget(self.camera);row.addStretch()
  self.toggle=action('Включить камеру',self.switch,True);row.addWidget(self.toggle);camera_box.addLayout(row)
  self.notice=QLabel();self.notice.setWordWrap(True);self.notice.setAccessibleName('');self.notice.setStyleSheet(f'color:{DIM};font-size:16px;');camera_box.addWidget(self.notice)
  self.last=QLabel('Последний жест: пока нет');self.last.setWordWrap(True);self.last.setStyleSheet(f'color:{CYAN};font-size:18px;font-weight:600;');camera_box.addWidget(self.last)
  media_box=card('Пауза и воспроизведение','Поднимите открытую ладонь и держите её неподвижно около секунды. Выберите ниже, управлять видео во вкладке или системным проигрывателем.')
  media_note=QLabel('Раскройте ладонь и удерживайте неподвижно 1 секунду. Для повтора опустите руку или уберите её из кадра. Короткое разжимание после свайпа не переключает видео.');media_note.setWordWrap(True);media_note.setStyleSheet(f'color:{DIM};font-size:16px;');media_box.addWidget(media_note)
  guide_box=card('Захватите и потяните','Можно войти в кадр уже с захватом. В обычном режиме длинный мах переключает несколько роликов; аналоговый плавно тянет страницу за рукой.')
  for number,text in [('1','Сомкните большой, указательный и средний пальцы.'),('2','Сразу потяните руку в нужную сторону — медленная подготовка не нужна.'),('3','Разожмите пальцы перед следующим махом.')]:
   step=QHBoxLayout();step.setSpacing(13);badge=QLabel(number);badge.setFixedSize(30,30);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);badge.setStyleSheet(f'background:#293e40;color:{CYAN};border-radius:15px;font-size:16px;font-weight:600;');step.addWidget(badge,0,Qt.AlignmentFlag.AlignTop);instruction=QLabel(text);instruction.setWordWrap(True);step.addWidget(instruction,1);guide_box.addLayout(step)
  mapping=QLabel('Shorts: ↑ следующее видео · ↓ предыдущее\nСтраницы: ↑↓ прокрутка · ←→ видео ±5 секунд');mapping.setWordWrap(True);mapping.setStyleSheet(f'color:{DIM};font-size:16px;');guide_box.addWidget(mapping)
  guide_box.addWidget(action('Настроить захват · 10 секунд',self.calibrate))
  self.build_bindings(card,action)
  camera_box.addWidget(action('Настроить руки и назначения',lambda:self.settings_workspace.select('bindings')))
  tuning=card('Подстройте под себя')
  self.always=QCheckBox('Включать жесты вместе с AirControl');self.always.setAccessibleName('Автоматически включать камеру жестов при запуске AirControl');self.always.setChecked(bool(load_preferences().get('room_gestures_autostart')));self.always.toggled.connect(self.autostart);tuning.addWidget(self.always)
  self.distance_label=QLabel('Размах движения');tuning.addWidget(self.distance_label)
  self.distance_value=QLabel();self.distance_value.setAccessibleName('Текущий размах движения');self.distance_value.setStyleSheet(f'color:{CYAN};font-size:18px;');tuning.addWidget(self.distance_value)
  self.distance=QSlider(Qt.Orientation.Horizontal);self.distance.setRange(4,20);self.distance.setMinimumHeight(32);self.distance.setAccessibleName('Необходимый размах движения руки');self.distance_label.setBuddy(self.distance);self.distance.valueChanged.connect(self.set_distance);tuning.addWidget(self.distance)
  scale=QHBoxLayout();short=QLabel('Короткое движение');short.setStyleSheet(f'color:{DIM};font-size:16px;');scale.addWidget(short);scale.addStretch();wide=QLabel('Уверенный размах');wide.setStyleSheet(f'color:{DIM};font-size:16px;');scale.addWidget(wide);tuning.addLayout(scale)
  self.distance_note=QLabel('Размах применяется сразу, без перезапуска камеры. Больше значение — меньше чувствительность.');self.distance_note.setWordWrap(True);self.distance_note.setStyleSheet(f'color:{DIM};font-size:16px;');tuning.addWidget(self.distance_note)
  browser=card('Подключите страницу','В Chrome или Edge выберите окно в расширении. Жесты следуют за его активной вкладкой, включая переходы между сайтами.')
  self.browser_media=QCheckBox('Медиажесты и масштаб управляют выбранной вкладкой');self.browser_media.setAccessibleName('Медиажесты управляют выбранной вкладкой');self.browser_media.setChecked(bool(load_preferences().get('room_gestures_browser_media',False)));self.browser_media.toggled.connect(self.set_browser_media);browser.addWidget(self.browser_media)
  browser_note=QLabel('Для игры на другом экране включите в расширении «Продолжать управление, когда активна игра». Перемотка, пауза и громкость применяются к выбранному видео без переключения окон.');browser_note.setWordWrap(True);browser_note.setStyleSheet(f'color:{DIM};font-size:16px;');browser.addWidget(browser_note)
  browser.addWidget(action('Открыть расширение для Chrome / Edge',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'BrowserGestures')))))
  layout.addStretch()
  from core.room_gesture_guide import GestureGuide
  def show_bindings():
   self.settings_workspace.select('bindings')
  self.guide=GestureGuide(show_bindings);self.pages.addTab(self.guide,'Справочник жестов')
  camera_box.addWidget(action('Как выполнять жесты',lambda:self.settings_workspace.select('guide')))
  privacy=QLabel('Кадры обрабатываются только на этом компьютере.');privacy.setWordWrap(True);privacy.setStyleSheet(f'color:{DIM};font-size:16px;');outer.addWidget(privacy)
  install_controller(parent)
  self.controller=parent._gesture_controller;self.last.setText(self.controller.last_gesture);self.controller.message.connect(self.receive);self.refresh()
  self.sync_timer=QTimer(self);self.sync_timer.setInterval(250);self.sync_timer.timeout.connect(self.refresh);self.sync_timer.start()
  from core.room_gesture_settings import install
  install(self)
 def build_bindings(self,card,button):
  from core.room_gesture_rules import ACTIONS,EVENTS,read_settings,save_settings,settings
  path=DATA_DIR/'config/gesture-actions.json';self.bindings=read_settings(path);self.binding_combos=[]
  box=card('Режим управления','Обычный режим выполняет команды махом; аналоговый тянет страницу; мышь управляет курсором.')
  self.bindings_card=box.parentWidget()
  self.mode_combo=QComboBox();self.mode_combo.setAccessibleName('Способ управления жестами')
  self.mode_combo.addItem('Обычное · длиннее мах — больше роликов','discrete');self.mode_combo.addItem('Аналоговое · тянуть страницу рукой','analog');self.mode_combo.addItem('Мышь рукой · выбранная страница','mouse');self.mode_combo.addItem('Мышь рукой · весь Mac','system_mouse')
  self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.bindings['mode']));box.addWidget(self.mode_combo)
  note=QLabel('Аналоговое: сомкните пальцы и тяните страницу, как на сенсорном экране. Небольшое движение сдвигает её частично; размах на одно видео задаётся ползунком ниже. Неподвижная кисть не продолжает прокрутку. Влево/вправо — перемотка, левый уголок — громкость. Эти действия идут только в выбранную вкладку расширения, даже во время игры.');note.setWordWrap(True);box.addWidget(note)
  def mode_changed():
   self.controller.set_mode(self.mode_combo.currentData());self.bindings=read_settings(path)
   self.refresh()
  self.mode_combo.currentIndexChanged.connect(mode_changed)
  box=card('Мышь рукой','Положение кисти управляет курсором. Скорость постоянная, пока вы сами не включите ускорение.')
  pointer_note=QLabel('Мышь рукой: указательный — курсор; большой + указательный — клик или выделение. Сведите большой, указательный и средний и ведите кисть вверх/вниз, чтобы прокручивать как пальцем по экрану. Два вытянутых пальца тоже прокручивают. Большой и средний вместе, указательный вытянут — правый клик. Кулак отпускает кнопку; Esc останавливает. Ускорение выключено по умолчанию; его можно включить флажком «Ускорять курсор». Если расширение активно, выбирайте режим в его меню ⋯.');pointer_note.setWordWrap(True);box.addWidget(pointer_note)
  hand_choice=QComboBox();hand_choice.setAccessibleName('Управляющая рука для мыши');hand_choice.addItem('Мышь · правая рука','Right');hand_choice.addItem('Мышь · левая рука','Left');hand_choice.setCurrentIndex(hand_choice.findData(self.bindings.get('mouse_hand','Right')));box.addWidget(hand_choice)
  positioning=QComboBox();positioning.setAccessibleName('Способ позиционирования мыши рукой');positioning.addItem('Как тачпад · относительное движение','relative');positioning.addItem('Как указатель · прямое наведение','absolute');positioning.setCurrentIndex(positioning.findData(self.bindings.get('mouse_position','relative')));box.addWidget(positioning)
  mouse_speed=QSlider(Qt.Orientation.Horizontal);mouse_speed.setRange(5,30);mouse_speed.setValue(round(self.bindings.get('mouse_speed',1.5)*10));mouse_speed.setAccessibleName('Скорость мыши рукой');speed_value=QLabel('Скорость курсора · '+str(mouse_speed.value()/10)+' ×');box.addWidget(speed_value);box.addWidget(mouse_speed)
  mouse_acceleration=QCheckBox('Ускорять курсор при быстрых движениях');mouse_acceleration.setChecked(self.bindings.get('mouse_acceleration',False));mouse_acceleration.setToolTip('Выключено по умолчанию. Только относительное наведение. Перетаскивание и прокрутка остаются линейными.');box.addWidget(mouse_acceleration)
  self.mouse_hand=hand_choice;self.mouse_position=positioning;self.mouse_speed=mouse_speed;self.mouse_acceleration=mouse_acceleration
  box.removeWidget(pointer_note);box.addWidget(pointer_note)
  def pointer_settings():
   speed_value.setText('Скорость курсора · '+str(mouse_speed.value()/10)+' ×')
   config=read_settings(path);config['mouse_hand']=hand_choice.currentData();config['mouse_speed']=mouse_speed.value()/10;config['mouse_position']=positioning.currentData();config['mouse_acceleration']=mouse_acceleration.isChecked();self.bindings.update(mouse_hand=config['mouse_hand'],mouse_speed=config['mouse_speed'],mouse_position=config['mouse_position'],mouse_acceleration=config['mouse_acceleration']);save_settings(path,config);self.controller.reload_rules()
  positioning.currentIndexChanged.connect(pointer_settings);hand_choice.currentIndexChanged.connect(pointer_settings);mouse_speed.valueChanged.connect(pointer_settings);mouse_acceleration.toggled.connect(pointer_settings)

  box=card('Назначения жестов','Выберите руку и назначьте действие. Поиск сверху находит любой жест и открывает нужную строку.');self.bindings_card=box.parentWidget()
  swap=QCheckBox('Поменять левую и правую руку местами');swap.setChecked(self.bindings['swap_hands']);box.addWidget(swap);self.swap_hands=swap
  def swapped(value):self.bindings['swap_hands']=value;save_settings(path,self.bindings)
  swap.toggled.connect(swapped);tabs=QTabWidget();box.addWidget(tabs);self.binding_tabs=tabs
  for hand,title in [('Right','Правая рука'),('Left','Левая рука')]:
   page=QWidget();form=QFormLayout(page);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
   for event,label in EVENTS.items():
    combo=QComboBox();combo.setMinimumHeight(38);combo.setAccessibleName(title+' · '+label)
    for key,name in ACTIONS.items():combo.addItem(name,key)
    combo.setCurrentIndex(combo.findData(self.bindings['rules'][hand][event]));form.addRow(label,combo);self.binding_combos.append((hand,event,combo))
    def changed(index,h=hand,e=event,c=combo):self.bindings['rules'][h][e]=c.currentData();save_settings(path,self.bindings)
    combo.currentIndexChanged.connect(changed)
   tabs.addTab(page,title)
  def defaults():
   self.bindings=settings();swap.blockSignals(True);swap.setChecked(False);swap.blockSignals(False)
   for control,update in [(hand_choice,lambda:hand_choice.setCurrentIndex(0)),(positioning,lambda:positioning.setCurrentIndex(0)),(mouse_speed,lambda:mouse_speed.setValue(15)),(mouse_acceleration,lambda:mouse_acceleration.setChecked(False))]:
    control.blockSignals(True);update();control.blockSignals(False)
   speed_value.setText('Скорость курсора · 1.5 ×')
   self.mode_combo.blockSignals(True);self.mode_combo.setCurrentIndex(0);self.mode_combo.blockSignals(False)
   for hand,event,combo in self.binding_combos:
    combo.blockSignals(True);combo.setCurrentIndex(combo.findData(self.bindings['rules'][hand][event]));combo.blockSignals(False)
   save_settings(path,self.bindings)
   self.controller.set_mode('discrete')
   self.controller.analog_span=self.bindings.get('analog_span',.20)
   self.refresh()
  box.addWidget(button('Вернуть стандартные жесты',defaults))
 def refresh(self):
  if hasattr(self,'mode_combo') and self.mode_combo.currentData()!=self.controller.control_mode:
   self.bindings['mode']=self.controller.control_mode;self.mode_combo.blockSignals(True);self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.controller.control_mode));self.mode_combo.blockSignals(False)
  self.refresh_distance()
  running=self.controller.camera_snapshot()['running']
  if not running:self.preview.clear();self.preview.setText('Камера выключена')
  self.toggle.setText('Выключить камеру' if running else 'Включить камеру');self.toggle.setAccessibleName(self.toggle.text());self.camera.setEnabled(not running);self.notice.setText(self.controller.status+('\n'+self.controller.performance if self.controller.performance else ''));self.last.setText(self.controller.last_gesture)
  self.always.blockSignals(True);self.always.setChecked(bool(load_preferences().get('room_gestures_autostart')));self.always.blockSignals(False)
 def refresh_distance(self):
  analog=self.controller.control_mode=='analog'
  value=self.controller.analog_span if analog else self.controller.discrete_distance
  self.bindings['analog_span']=self.controller.analog_span
  self.distance.blockSignals(True)
  try:self.distance.setRange(12,60) if analog else self.distance.setRange(4,20);self.distance.setValue(round(value*100))
  finally:self.distance.blockSignals(False)
  self.distance_label.setText('Размах на одно видео' if analog else 'Размах обычного свайпа')
  self.distance_value.setText(str(self.distance.value())+'% кадра')
  self.distance.setAccessibleName(self.distance_label.text())
  self.distance.setToolTip('Больше размах — меньше чувствительность. Применяется сразу, без перезапуска камеры.')
 def set_distance(self,value):
  try:
   if self.controller.control_mode=='analog':
    self.bindings['analog_span']=value/100;self.controller.set_analog_span(value/100)
   else:self.controller.set_discrete_distance(value/100)
  except Exception as error:self.controller.status='Размах сохранён, но не удалось обновить распознавание: '+str(error)
  self.refresh()
 def switch(self):
  try:
   if self.controller.process:self.controller.stop();save_preferences(room_gestures_autostart=False);self.preview.clear();self.preview.setText('Камера выключена')
   else:self.controller.start(self.camera.value());self.controller.status='Запускаю распознавание руки…'
  except Exception as error:self.controller.status=str(error)
  self.refresh()
 def autostart(self,enabled):
  save_preferences(room_gestures_autostart=bool(enabled))
  if enabled and not self.controller.process:self.switch()
 def set_browser_media(self,enabled):
  self.controller.browser_media=bool(enabled);save_preferences(room_gestures_browser_media=bool(enabled))
 def calibrate(self):
  try:
   if not self.controller.process:self.switch()
   self.controller.calibrate()
  except Exception as error:self.controller.status=str(error);self.refresh()
 def receive(self,data):
  if data.get('_epoch',self.controller.epoch)!=self.controller.epoch and data.get('type') not in ('error','ended'):return
  if data.get('type')=='preview':
   pix=QPixmap();pix.loadFromData(base64.b64decode(data['image']));self.preview.setPixmap(pix)
  elif data.get('type') in ('error','ended'):self.preview.clear()
  self.refresh()

def install_controller(window):
 if hasattr(window,'_gesture_controller'):return window._gesture_controller
 controller=GestureController(window);window._gesture_controller=controller
 from PyQt6.QtWidgets import QApplication
 QApplication.instance().aboutToQuit.connect(controller.shutdown)
 try:controller.ensure_relay()
 except Exception as error:controller.status=str(error)
 if load_preferences().get('room_gestures_autostart'):
  def automatic():
   try:controller.start()
   except Exception as error:controller.status=str(error)
  QTimer.singleShot(750,automatic)
 return controller

def open_panel(window,section=None,setting=None):
 existing=getattr(window,'_gesture_panel',None)
 if not existing:window._gesture_panel=GesturePanel(window)
 view=window._gesture_panel
 if section:view.settings_workspace.select(section,getattr(view,setting,None) if setting else None)
 view.show();view.raise_();return view
