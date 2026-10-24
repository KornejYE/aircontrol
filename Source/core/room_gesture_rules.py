"""Per-hand gesture bindings. Numerical landmarks only; no input or camera API."""
import json, math
from pathlib import Path
from core.room_gesture_engine import GestureEngine
from core.room_gesture_zoom import PinchZoom
from core.room_gesture_analog import AnalogDrag,ViewportDrag,command

ACTIONS = {'none':'Ничего', 'up':'Следующее Shorts / прокрутить вниз',
 'down':'Предыдущее Shorts / прокрутить вверх', 'left':'Назад на 5 секунд',
 'right':'Вперёд на 5 секунд', 'play_pause':'Пауза / продолжить',
 'volume_up':'Громкость +', 'volume_down':'Громкость −', 'mute':'Выключить / включить звук',
 'next_track':'Следующий трек', 'previous_track':'Предыдущий трек', 'zoom_in':'Увеличить масштаб', 'zoom_out':'Уменьшить масштаб'}
POSES = {'grab':'Захват тремя пальцами', 'corner':'Уголок: большой и указательный',
 'pinch':'Щипок двумя пальцами', 'point':'Указательный палец',
 'palm':'Открытая ладонь', 'fist':'Кулак', 'thumb_up':'Большой палец вверх',
 'thumb_down':'Большой палец вниз'}
EVENTS = {'zoom_spread':'Два пальца · развести', 'zoom_close':'Два пальца · свести', **{p+'_'+d:POSES[p]+' · '+label for p in ('grab','corner','pinch','point')
 for d,label in [('up','вверх'),('down','вниз'),('left','влево'),('right','вправо')]},
 **{p+'_hold':POSES[p]+' · удержать' for p in ('palm','fist','thumb_up','thumb_down')}}
DEFAULTS = {'Right':{'zoom_spread':'zoom_in','zoom_close':'zoom_out',**{'grab_'+d:d for d in ('up','down','left','right')},'palm_hold':'play_pause'},
 'Left':{**{'grab_'+d:d for d in ('up','down','left','right')},'palm_hold':'play_pause','corner_up':'volume_up','corner_down':'volume_down'}}

def settings(value=None):
 from core.room_hand_joystick import game_settings
 value=value if isinstance(value,dict) else {}
 rules=value.get('rules',{})
 speed=value.get('analog_speed',1.)
 if type(speed) not in (int,float) or not math.isfinite(speed):speed=1.
 span=value.get('analog_span',.20)
 if type(span) not in (int,float) or not math.isfinite(span):span=.20
 return {'mode':value.get('mode') if value.get('mode') in ('analog','mouse','system_mouse','joystick') else 'discrete',
  'joystick':game_settings(value.get('joystick',{'hand':value.get('mouse_hand')})),
  'mouse_return_mode':'analog' if value.get('mouse_return_mode')=='analog' else 'discrete',
  'mouse_position':'absolute' if value.get('mouse_position')=='absolute' else 'relative',
  'mouse_acceleration':value.get('mouse_acceleration') is True,
  'mouse_precision':value.get('mouse_precision',True) is not False,
  'mouse_speed':max(.5,min(3.,value.get('mouse_speed',1.5))) if type(value.get('mouse_speed',1.5)) in (int,float) and math.isfinite(value.get('mouse_speed',1.5)) else 1.5,
 'mouse_hand':'Left' if value.get('mouse_hand')=='Left' else 'Right',
 'analog_span':max(.12,min(.60,span)),
  'analog_speed':max(.25,min(2.,speed)), 'swap_hands':value.get('swap_hands') is True,'rules':{
  hand:{event:(rules.get(hand,{}).get(event,DEFAULTS.get(hand,{}).get(event,'none'))
    if rules.get(hand,{}).get(event,DEFAULTS.get(hand,{}).get(event,'none')) in ACTIONS else 'none')
   for event in EVENTS} for hand in ('Right','Left')}}

def read_settings(path):
 try:return settings(json.loads(Path(path).read_text(encoding='utf-8')))
 except (OSError,ValueError):return settings()

def save_settings(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(settings(value),ensure_ascii=False),encoding='utf-8')
 temporary.chmod(0o600);temporary.replace(path)

def _corner_geometry(p,norm):
 # A finger folded toward the camera can still have its tip farther from the
 # wrist than its PIP joint. Use the joint chain as well as that radial test.
 def finger(base):
  length=sum(math.dist(p[i],p[i+1]) for i in range(base,base+3))
  straight=math.dist(p[base],p[base+3])/max(1e-6,length)
  radial=math.dist(p[base+3],p[0])/max(1e-6,math.dist(p[base+1],p[0]))
  reach=math.dist(p[base],p[base+3])/norm
  return straight,radial,reach
 index=finger(5);others=[finger(base) for base in (9,13,17)]
 index_open=index[0]>=.78 and index[1]>1.06 and index[2]>.58
 # A straight middle finger means a different pose, even when two other
 # fingers are hidden. Mild foreshortening of one curled finger is allowed.
 folded=[radial<1.12 or straight<.80 for straight,radial,reach in others]
 other_open=[straight>=.86 and radial>1.15 and reach>.65 for straight,radial,reach in others]
 closed_others=sum(folded)>=2 and not any(other_open)
 thumb_open=math.dist(p[4],p[5])>norm*.60 and math.dist(p[4],p[2])>norm*.50
 # Use each digit's own base: moving the thumb across the palm must not
 # change a genuine right angle into a point merely because MCP5 moved.
 a=(p[4][0]-p[2][0],p[4][1]-p[2][1]);b=(p[8][0]-p[5][0],p[8][1]-p[5][1])
 cosine=sum(x*y for x,y in zip(a,b))/max(1e-6,math.hypot(*a)*math.hypot(*b))
 angle_ok=-.76<cosine<.70
 corner=index_open and closed_others and thumb_open and angle_ok and math.dist(p[4],p[8])>norm*.8
 candidate=index_open and (closed_others or thumb_open)
 reason=('Согните средний, безымянный и мизинец' if not closed_others else
         'Отведите большой палец в сторону' if not thumb_open or not angle_ok else '')
 return corner,candidate,reason

def poses(p):
 dist=lambda a,b:math.dist(p[a],p[b])
 norm=max(.025,dist(5,17),dist(0,9)*.65)
 extended=[dist(t,0)>dist(t-2,0)*1.12 and dist(t-3,t)>norm*.55 for t in (8,12,16,20)]
 curled=[dist(t,0)<dist(t-2,0)*1.12 for t in (8,12,16,20)]
 thumb=dist(4,5)>norm*.65 and dist(4,2)>norm*.6
 corner,corner_candidate,corner_reason=_corner_geometry(p,norm)
 pinch=dist(4,8)<norm*.4 and dist(4,12)>norm*.55
 point=extended[0] and all(curled[1:]) and not corner and not pinch
 fist=all(curled) and not thumb
 thumb_up=all(curled) and thumb and p[4][1]<p[2][1]-norm*.35
 thumb_down=all(curled) and thumb and p[4][1]>p[2][1]+norm*.35
 return norm,dict(corner=corner,pinch=pinch,point=point,fist=fist,thumb_up=thumb_up,thumb_down=thumb_down,
                  corner_candidate=corner_candidate,corner_reason=corner_reason)

class HandRules:
 def __init__(self,distance=.085,profile=None):
  from core.room_air_mouse import AirMouse
  from core.room_hand_joystick import HandJoystick
  self.mouse=AirMouse()
  self.joystick=HandJoystick()
  self.config=settings();self.engines={h:GestureEngine(distance=distance,profile=profile,relative_floor=0.) for h in ('Right','Left')}
  self.zoom={h:PinchZoom() for h in self.engines};self.states={h:{} for h in self.engines};self.feedback={};self.last_hand=''
  self.analog={h:AnalogDrag(distance=distance) for h in self.engines}
  self.stepped={h:AnalogDrag(distance=distance,relative_floor=0.) for h in self.engines}
  self.scroll={h:ViewportDrag(h) for h in self.engines};self._pending=[]
 def _finish_scroll(self,hand,phase='cancel'):
  packet=self.scroll[hand].finish(phase)
  return [(hand,'grab_scroll',packet)] if packet else []
 def take_pending(self):
  pending,self._pending=self._pending,[]
  return pending
 def set_distance(self,value):
  if type(value) not in (int,float) or not math.isfinite(value):return
  distance=max(.04,min(.2,value))
  if all(engine.distance==distance for engine in self.engines.values()):return
  for hand,engine in self.engines.items():
   self._pending.extend(self._finish_scroll(hand));engine.distance=distance;engine.reset()
   self.analog[hand].distance=distance;self.analog[hand].reset();self.zoom[hand].reset()
   self.stepped[hand].distance=distance;self.stepped[hand].reset()
  self.states={hand:{} for hand in self.engines}
 def configure(self,value):
  updated=settings(value)
  if updated==self.config:return
  for packet in self.mouse.cancel():self._pending.append((self.config['mouse_hand'],'pointer',packet))
  if self.config['mode']=='joystick':self._pending.append((self.config['joystick']['hand'],'joystick',self.joystick.cancel()))
  else:self.joystick.reset()
  for hand in self.engines:self._pending.extend(self._finish_scroll(hand))
  self.config=updated
  for z in self.zoom.values():z.reset()
  for e in self.engines.values():e.reset()
  for a in self.analog.values():a.reset()
  for a in self.stepped.values():a.reset()
  self.states={h:{} for h in self.engines}
 def reset_hand(self,hand):
  """A new physical controller cannot inherit the previous person's gesture."""
  if self.config['swap_hands']:hand='Left' if hand=='Right' else 'Right'
  self._pending.extend(self._finish_scroll(hand))
  if hand==self.config['mouse_hand']:
   for packet in self.mouse.cancel():self._pending.append((hand,'pointer',packet))
  if self.config['mode']=='joystick' and hand==self.config['joystick']['hand']:
   self._pending.append((hand,'joystick',self.joystick.cancel('lost')))
  previous=self.engines[hand]
  self.engines[hand]=GestureEngine(hold=previous.hold,distance=previous.distance,
                                 cooldown=previous.cooldown,profile=previous.profile,relative_floor=previous.relative_floor)
  self.states[hand]={};self.zoom[hand].reset()
  self.analog[hand].reset()
  self.stepped[hand].reset()
 def update(self,landmarks,now,hand,allow_actions=True):
  if hand not in self.engines:return None
  if self.config['swap_hands']:hand='Left' if hand=='Right' else 'Right'
  if self.config['mode']=='joystick':
   if self.config['joystick']['source']=='object':return None
   if hand!=self.config['joystick']['hand']:return None
   packet=(self.joystick.update(landmarks,now,self.config['joystick']) if allow_actions else self.joystick.cancel('lost'))
   fist=self.config['joystick']['grip']=='fist'
   labels={'idle':'Сожмите кулак и держите прямо 0,2 секунды' if fist else 'Сомкните большой и указательный пальцы',
           'arming':'Удерживайте захват · задаю нейтраль',
           'active':('Кулак: наклоняйте кисть как джойстик; раскройте ладонь для остановки' if self.config['joystick']['motion']=='tilt' else 'Джойстик: двигайте кисть; разожмите пальцы для остановки'),
           'lost':'Рука не видна · ввод отпущен'}
   self.feedback=dict(side='Правая' if hand=='Right' else 'Левая',grip=packet['active'],phase=labels[self.joystick.state])
   return [(hand,'joystick',packet)]
  if self.config['mode'] in ('mouse','system_mouse'):
   if hand!=self.config['mouse_hand']:return None
   hard_cancel=not allow_actions
   try:
    p=[(float(v.x),float(v.y)) if hasattr(v,'x') else (float(v[0]),float(v[1])) for v in landmarks] if landmarks is not None and allow_actions else None
    norm,flags=poses(p) if p is not None else (.2,{})
   except (ValueError,TypeError,IndexError,AttributeError):p=None;norm=.2;flags={};hard_cancel=True
   packets=(self.mouse.cancel() if hard_cancel else self.mouse.update(p,now,speed=self.config['mouse_speed'],flags=flags,norm=norm,positioning=self.config['mouse_position'],acceleration=self.config['mouse_acceleration'],precision=self.config['mouse_precision']))
   if self.config['mode']=='system_mouse' and self.config['mouse_position']=='relative' and any(packet['phase']=='cancel' for packet in packets):self.mouse.xy=[.5,.5]
   labels={'point':'Курсор','pinch':'Щипок · клик / перетаскивание','scroll':'Прокрутка двумя пальцами','scroll_grab':'Прокрутка захватом трёх пальцев','context':'Контекстное меню','fist':'Кулак — курсор заморожен'}
   self.feedback=dict(side='Правая' if hand=='Right' else 'Левая',grip=self.mouse.pose not in (None,'idle','fist'),phase=labels.get(self.mouse.pose,'Мышь рукой · рука не видна'))
   return [(hand,'pointer',packet) for packet in packets] or None
  engine=self.engines[hand];state=self.states[hand];self.last_hand=hand
  result=engine.update(landmarks,now,hand,allow_media=allow_actions)
  self.feedback=dict(engine.feedback,side='Правая' if hand=='Right' else 'Левая')
  bindings=self.config['rules'][hand]
  if landmarks is None:
   terminal=self._finish_scroll(hand)
   self.analog[hand].reset()
   self.stepped[hand].release()
   self.zoom[hand].reset()
   since=state.get('missing',now);state['missing']=since
   if state.get('pose')=='corner' and now-state.get('corner_valid',now)>.12:state.clear()
   if now-since>=.35:state.clear();engine._needs_grab_release=False
   return terminal or None
  had_missing=state.pop('missing',None)
  if had_missing is not None and state.get('pose')=='corner' and now-state.get('corner_valid',now)>.12:state.clear()
  if not allow_actions:
   terminal=self._finish_scroll(hand);state.clear();self.zoom[hand].reset();self.analog[hand].reset();self.stepped[hand].release();engine.reset();engine.require_media_release();return terminal or None
  try:
   p=[(float(v.x),float(v.y)) if hasattr(v,'x') else (float(v[0]),float(v[1])) for v in landmarks]
   if len(p)!=21 or not all(math.isfinite(v) for xy in p for v in xy):
    terminal=self._finish_scroll(hand);state.clear();self.analog[hand].reset();self.stepped[hand].release();return terminal or None
   norm,flags=poses(p)
  except (ValueError,TypeError,IndexError,AttributeError):
   terminal=self._finish_scroll(hand);state.clear();self.analog[hand].reset();self.stepped[hand].release();return terminal or None
  if self.config['mode']=='discrete':
   # Restore distance-to-step navigation separately from touchscreen dragging.
   # Extra travel earns extra whole steps; holding an offset earns nothing.
   stepper=self.stepped[hand]
   if engine.feedback.get('grip'):
    pos=tuple(sum(p[i][axis] for i in (4,8,12))/3 for axis in (0,1))
    motion=stepper.update(pos,now,'grab',norm)
    axis_directions=('up','down') if stepper.axis==1 else ('left','right')
    repeatable=('up','down','left','right','volume_up','volume_down')
    proportional=all(bindings['grab_'+d] in repeatable for d in axis_directions)
    if proportional and result in axis_directions:result=None
    if proportional and stepper.axis is not None:
     state.clear();self.zoom[hand].reset()
     self.feedback['phase']='Обычное: длиннее мах — больше шагов; неподвижная рука не повторяет'
     if motion:
      direction,_,steps=motion
      if steps:
       event='grab_'+direction
       return hand,event,dict(action=bindings[event],swipe_steps=steps)
     return None
   else:stepper.release()
  if self.config['mode']=='analog':
   analog_pose=('corner' if hand=='Left' and flags['corner'] else
                'grab' if engine.feedback.get('grip') else None)
   if analog_pose:
    pos=tuple(sum(p[i][axis] for i in (0,5,9,13,17))/5 for axis in (0,1))
    motion=self.analog[hand].update(pos,now,analog_pose,norm,self.config['analog_speed'])
    state.clear();self.zoom[hand].reset()
    self.feedback['phase']=('Аналоговое: перемещайте страницу рукой; неподвижная кисть удерживает её'
                            if self.analog[hand].armed else 'Аналоговое: ненадолго зафиксируйте кисть')
    terminal=[]
    if self.scroll[hand].gesture_id is not None:
     if analog_pose!=self.scroll[hand].pose or self.analog[hand].axis!=1:
      terminal=self._finish_scroll(hand)
     else:
      packets=self.scroll[hand].move(pos,now)
      return [(hand,'grab_scroll',packet) for packet in packets] or None
    if motion:
     direction,distance_steps,steps=motion;event=analog_pose+'_'+direction
     if direction in ('up','down') and bindings[event] in ('up','down'):
      invert=1. if bindings[event]==direction else -1.
      packets=self.scroll[hand].move(pos,now,origin=self.analog[hand].origin,span=self.config['analog_span'],invert=invert,pose=analog_pose)
      return terminal+[(hand,'grab_scroll',packet) for packet in packets]
     payload=command(bindings[event],distance_steps,steps)
     if payload:return terminal+[(hand,event,payload)] if terminal else (hand,event,payload)
     if steps and bindings[event]!='none' and not self.analog[hand].fallback_fired:
      self.analog[hand].fallback_fired=True
      return terminal+[(hand,event,bindings[event])] if terminal else (hand,event,bindings[event])
    return terminal or None
   # A few ambiguous finger measurements are not a deliberate release. Keep
   # the last position briefly, without moving from uncertain landmarks. An
   # unambiguously opened grip, missing hand, stale frame or new owner still
   # terminates immediately; a sustained uncertain pose also ends the drag.
   active=self.scroll[hand]
   if (active.gesture_id is not None and active.pose=='grab'
       and not engine.feedback.get('grip_open',True)
       and self.analog[hand].last is not None
       and 0<=now-self.analog[hand].last<=.10):
    self.feedback['phase']='Захват кратко неуверенный — страница удерживается'
    return None
   terminal=self._finish_scroll(hand,'end')
   self.analog[hand].release()
   if terminal:return terminal
   # In this mode a grab never also emits the ordinary one-shot swipe.
   if result!='play_pause':result=None
  zoom_bound=any(bindings.get('zoom_'+suffix,'none')!='none' for suffix in ('spread','close'))
  if zoom_bound and not (state.get('pose')=='corner' and state.get('armed')):
   zoom=self.zoom[hand].update(p,now)
   if self.zoom[hand].active:
    self.feedback['phase']='Масштаб: разводите или сводите большой и указательный пальцы'
    state.clear()
    if zoom:
     engine.require_media_release();event='zoom_'+zoom;action=bindings[event]
     return (hand,event,action) if action!='none' else None
    return None
  pose=next((name for name in ('corner','pinch','point','thumb_up','thumb_down','fist')
   if flags[name] and any(bindings.get(name+'_'+suffix,'none')!='none' for suffix in ('up','down','left','right','hold'))),None)
  if result and (pose is None or result=='play_pause'):
   event='palm_hold' if result=='play_pause' else 'grab_'+result
   action=bindings[event]
   if action!='none':return hand,event,action
  if state.get('last_frame') is not None and (now<state['last_frame'] or now-state['last_frame']>.5):state.clear()
  state['last_frame']=now
  pos=tuple(sum(p[i][axis] for i in (0,5,9,13,17))/5 for axis in (0,1))
  corner_bound=any(bindings.get('corner_'+suffix,'none')!='none' for suffix in ('up','down','left','right'))
  self.feedback.update(corner_candidate=flags['corner_candidate'],corner_armed=False,corner_progress=0.)
  if pose is None:
   # A single uncertain landmark frame must not erase an otherwise stable L.
   # Missing/uncertain frames never dispatch an action themselves.
   if state.get('pose')=='corner' and 0<=now-state.get('corner_valid',now)<=.12:
    state['corner_uncertain']=True
    self.feedback['phase']='Уголок: кратко потерян — удержите руку'
    return None
   if corner_bound and flags['corner_candidate']:
    self.feedback['phase']='Уголок: '+flags['corner_reason']
   state.clear();return None
  if pose=='corner' and state.pop('corner_uncertain',False) and now-state.get('corner_valid',now)>.12:state.clear()
  if state.get('pose')!=pose:
   state.clear();state.update(last_frame=now,pose=pose,since=now,origin=pos,previous=pos,armed=pose!='corner',fired=False,last=-100.)
   if pose=='corner':
    state['corner_valid']=now;self.feedback['phase']='Уголок обнаружен: зафиксируйте руку на 0,25 с'
   return None
  if pose=='corner':state['corner_valid']=now
  if now-state['since']>3 and not state['armed']:state.clear();return None
  if math.dist(pos,state['previous'])>.45:state.clear();return None
  state['previous']=pos
  if pose=='corner' and not state['armed']:
   self.feedback['phase']='Уголок: зафиксируйте руку на 0,25 с'
   if math.dist(pos,state['origin'])>max(.018,norm*.15):state['since']=now;state['origin']=pos
   elif now-state['since']>=.25:
    state['armed']=True;state['origin']=pos;self.feedback['phase']='Уголок готов: вверх — громче, вниз — тише'
   self.feedback.update(corner_armed=state['armed'],corner_progress=min(1.,max(0.,(now-state['since'])/.25)))
   return None
  if pose=='corner':self.feedback.update(corner_armed=True,corner_progress=1.)
  self.feedback['phase']=POSES[pose]+': '+('готово — двигайте руку' if pose in ('corner','pinch','point') else 'удержите')
  if pose in ('fist','thumb_up','thumb_down'):
   if math.dist(pos,state['origin'])>max(.025,norm*.2):state['since']=now;state['origin']=pos
   if state['fired'] or now-state['since']<.75:return None
   state['fired']=True;event=pose+'_hold'
  else:
   if now-state['since']<.08 or (pose!='corner' and now-state['last']<.35):return None
   if state['fired'] and pose!='corner':return None
   dx,dy=pos[0]-state['origin'][0],pos[1]-state['origin'][1]
   major,minor=max(abs(dx),abs(dy)),min(abs(dx),abs(dy))
   if major<max(.055,norm*.28) or major<minor*1.4:return None
   event=pose+'_'+(('right' if dx>0 else 'left') if abs(dx)>abs(dy) else ('down' if dy>0 else 'up'))
   state.update(fired=True,last=now,origin=pos)
  action=bindings[event]
  if self.config['mode']=='discrete' and pose=='corner' and action in ('volume_up','volume_down'):
   step=max(.055,norm*.28);steps=min(4,int((major+1e-9)/step))
   axis=0 if abs(dx)>abs(dy) else 1
   origin=list(pos);origin[axis]-=math.copysign(max(0.,major-steps*step),dx if axis==0 else dy)
   state['origin']=tuple(origin)
   return hand,event,dict(action=action,swipe_steps=steps)
  return (hand,event,action) if action!='none' else None
