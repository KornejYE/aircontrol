"""Loopback gesture relay with a leased browser mode. Never executes commands."""
import json,math,re,threading,time,uuid
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
BROWSER_ACTIONS=frozenset(('up','down','left','right','play_pause','volume_up','volume_down','mute','next_track','previous_track','zoom_in','zoom_out'))
class Relay:
 def __init__(self,port=8767):
  self.port=port;self.session=uuid.uuid4().hex;self.events=deque(maxlen=48);self.sequence=0;self.lock=threading.Lock();self.server=None;self._drags={}
  self.camera_control=None;self.camera_status=None;self.camera_mode=None
  self._browser_profile=None;self._browser_revision=0;self._browser_expires=0.;self._browser_applied=True
 def _invalidate_locked(self):
  self.session=uuid.uuid4().hex;self.events.clear();self.sequence=0;self._drags.clear()
 def invalidate(self):
  with self.lock:self._invalidate_locked()
 def offer_browser_profile(self,mode,span=None,target='',distance=None):
  if (mode not in ('analog','discrete','mouse','system_mouse') or (span is not None and
      (type(span) not in (int,float) or not math.isfinite(span) or not .12<=span<=.60))
      or (distance is not None and (type(distance) not in (int,float) or not math.isfinite(distance) or not .04<=distance<=.20))
      or not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9:._-]{0,200}',target)):
   raise ValueError('browser profile')
  profile=dict(mode=mode,span=span,target=target,distance=distance)
  with self.lock:
   self._expire_browser_locked()
   if profile!=self._browser_profile:
    self._browser_profile=profile;self._browser_revision+=1;self._browser_applied=False;self._invalidate_locked()
   self._browser_expires=time.monotonic()+1.
 def _expire_browser_locked(self):
  if self._browser_profile is not None and time.monotonic()>=self._browser_expires:
   self._browser_profile=None;self._browser_revision+=1;self._browser_applied=False;self._invalidate_locked()
 def _browser_snapshot_locked(self):
  return dict(self._browser_profile or dict(mode=None,span=None,target='',distance=None),revision=self._browser_revision,applied=self._browser_applied)
 def browser_profile(self):
  with self.lock:
   self._expire_browser_locked();return self._browser_snapshot_locked()
 def acknowledge_browser_profile(self,revision):
  with self.lock:
   if type(revision) is int and revision==self._browser_revision:self._browser_applied=True
 def publish_pointer(self,data):
  from core.room_air_mouse import valid_pointer
  if not valid_pointer(data):raise ValueError('pointer')
  with self.lock:
   if not self._browser_applied:return
   self.sequence+=1;self.events.append(dict(data,id=self.sequence,time=time.time()))
 def publish_drag(self,*,hand,gesture_id,phase,position):
  if (hand not in ('Right','Left') or not isinstance(gesture_id,str)
      or not re.fullmatch(r'[A-Za-z0-9:_-]{1,96}',gesture_id)
      or phase not in ('start','move','end','cancel')
      or type(position) not in (int,float) or not math.isfinite(position)
      or not -8<=position<=8 or (phase=='start' and position!=0)):
   raise ValueError('drag')
  with self.lock:
   if not self._browser_applied:return
   current=self._drags.get(hand)
   if phase!='start' and (not current or current['gesture_id']!=gesture_id):raise ValueError('orphan drag')
   if phase=='start' and current:
    self.sequence+=1
    self.events.append(dict(id=self.sequence,action='drag_scroll',time=time.time(),hand=hand,
                            gesture_id=current['gesture_id'],phase='cancel',position=current['position']))
   self.sequence+=1
   self.events.append(dict(id=self.sequence,action='drag_scroll',time=time.time(),hand=hand,
                           gesture_id=gesture_id,phase=phase,position=position))
   if phase in ('end','cancel'):self._drags.pop(hand,None)
   else:self._drags[hand]=dict(gesture_id=gesture_id,position=position)
 def publish(self,direction,*,amount=None,steps=0,swipe_steps=None):
  if direction not in BROWSER_ACTIONS:raise ValueError('action')
  extra={}
  if swipe_steps is not None:
   if (direction not in ('up','down','left','right','volume_up','volume_down') or type(swipe_steps) is not int
       or not 1<=swipe_steps<=4 or amount is not None):raise ValueError('swipe steps')
   extra=dict(swipe_steps=swipe_steps)
  if amount is not None:
   from core.room_gesture_analog import valid_amount
   if not valid_amount(direction,amount) or type(steps) is not int or not 0<=steps<=4:raise ValueError('analog amount')
   extra=dict(continuous=True,amount=amount,steps=steps)
  with self.lock:
   if not self._browser_applied:return
   self.sequence+=1;self.events.append(dict(id=self.sequence,direction=direction,time=time.time(),**extra))
 def snapshot(self,after=0,session='',analog=True,drag=False):
  with self.lock:
   self._expire_browser_locked()
   events=[dict(e) for e in self.events if e['id']>after and (analog or not e.get('continuous')) and (drag or e.get('action')!='drag_scroll') and time.time()-e['time']<(.30 if e.get('continuous') or e.get('action')=='drag_scroll' else 1.2)] if session==self.session and self._browser_applied else []
   return dict(session=self.session,cursor=self.sequence,events=events,profile=self._browser_snapshot_locked())
 def start(self):
  relay=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def authorized(self):
    client=self.headers.get('X-Jarvis-Extension','');origin=self.headers.get('Origin','')
    return self.headers.get('Host')==f'127.0.0.1:{relay.port}' and bool(re.fullmatch(r'[a-p]{32}',client)) and (not origin or origin=='chrome-extension://'+client)
   def do_POST(self):
    if not self.authorized():self.send_error(403);return
    mode=self.path.removeprefix('/camera/mode/') if self.path.startswith('/camera/mode/') else None
    if self.path not in ('/camera/on','/camera/off') and mode not in ('mouse','system_mouse','analog','discrete','restore'):self.send_error(404);return
    if self.headers.get('Content-Length','0')!='0' or self.headers.get('Transfer-Encoding'):self.send_error(400);return
    if relay.camera_control is None:self.send_error(503);return
    try:data=json.dumps(relay.camera_mode(mode) if mode is not None else relay.camera_control(self.path.endswith('/on'))).encode()
    except Exception:self.send_error(503);return
    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','chrome-extension://'+self.headers['X-Jarvis-Extension']);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
   def do_GET(self):
    # Privileged extension GETs may omit Origin. A custom header blocks ordinary
    # web requests (their preflight is deliberately unsupported), and Host blocks rebinding.
    client=self.headers.get('X-Jarvis-Extension','');origin=self.headers.get('Origin','')
    if self.headers.get('Host')!=f'127.0.0.1:{relay.port}' or not re.fullmatch(r'[a-p]{32}',client) or (origin and origin!='chrome-extension://'+client):
     self.send_error(403);return
    parsed=urlparse(self.path)
    if parsed.path=='/camera/status':
     if relay.camera_status is None:self.send_error(503);return
     data=json.dumps(relay.camera_status()).encode()
     self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','chrome-extension://'+client);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
    if parsed.path!='/events':self.send_error(404);return
    query=parse_qs(parsed.query,keep_blank_values=True)
    try:after=int(query.get('after',['0'])[0])
    except ValueError:self.send_error(400);return
    # Older extensions ignore amounts and would turn each tiny analog delta
    # into a full swipe. Deliver them only to the new explicit protocol reader.
    protocol=query.get('protocol',[''])[0]
    if any(key in query for key in ('mode','span','target','distance')):
     try:
      if protocol!='3' or any(len(query.get(key,[]))>1 for key in ('mode','span','target','distance')):raise ValueError()
      span=float(query['span'][0]) if 'span' in query else None
      distance=float(query['distance'][0]) if 'distance' in query else None
      relay.offer_browser_profile(query.get('mode',[''])[0],span,query.get('target',[''])[0],distance=distance)
     except (ValueError,OverflowError):self.send_error(400);return
    data=json.dumps(relay.snapshot(after,query.get('session',[''])[0],analog=protocol in ('2','3'),drag=protocol=='3')).encode()
    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','chrome-extension://'+client);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  self.server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler);self.port=self.server.server_port;self.server.daemon_threads=True
  threading.Thread(target=self.server.serve_forever,daemon=True,name='GestureRelay').start()
 def stop(self):
  if self.server:self.server.shutdown();self.server.server_close();self.server=None
