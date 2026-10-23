"""Leased browser modes: guarded HTTP, worker overlay and offscreen Qt IPC."""
import io,json,os,sys,tempfile,time,unittest,urllib.error,urllib.request
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Source'))
from core.room_gesture_relay import Relay
from core.room_gesture_worker import browser_runtime_config,runtime_settings,runtime_distance
from core.room_gesture_rules import settings,read_settings,save_settings
from core import room_gesture_panel as panel
from PyQt6.QtWidgets import QApplication,QWidget


class Lease(unittest.TestCase):
 def test_mouse_mode_endpoint_accepts_only_fixed_modes(self):
  r=Relay(port=0);calls=[];r.camera_control=lambda enabled:dict(ok=True);r.camera_mode=lambda mode:(calls.append(mode) or dict(ok=True));r.start()
  try:
   for mode in ('mouse','system_mouse','restore'):
    request=urllib.request.Request(f'http://127.0.0.1:{r.port}/camera/mode/{mode}',method='POST',headers={'X-Jarvis-Extension':'a'*32})
    with urllib.request.urlopen(request,timeout=2) as response:self.assertTrue(json.load(response)['ok'])
   request=urllib.request.Request(f'http://127.0.0.1:{r.port}/camera/mode/shell',method='POST',headers={'X-Jarvis-Extension':'a'*32})
   with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request,timeout=2)
   self.assertEqual(calls,['mouse','system_mouse','restore'])
  finally:r.stop()

 def test_camera_control_requires_guarded_explicit_post(self):
  r=Relay(port=0);calls=[];r.camera_control=lambda enabled:(calls.append(enabled) or dict(ok=True,camera=enabled));r.start()
  base=f'http://127.0.0.1:{r.port}'
  def post(path,headers=None):
   request=urllib.request.Request(base+path,method='POST',headers=headers or {'X-Jarvis-Extension':'a'*32})
   with urllib.request.urlopen(request,timeout=2) as response:return json.load(response)
  try:
   self.assertTrue(post('/camera/on')['camera']);self.assertFalse(post('/camera/off')['camera']);self.assertTrue(post('/camera/on')['camera'])
   for headers in [{'X-Jarvis-Extension':'bad'},{'X-Jarvis-Extension':'a'*32,'Origin':'https://evil.test'},{'X-Jarvis-Extension':'a'*32,'Host':'evil.test'}]:
    with self.assertRaises(urllib.error.HTTPError) as error:post('/camera/on',headers)
    self.assertEqual(error.exception.code,403)
   with self.assertRaises(urllib.error.HTTPError):post('/camera/other')
   self.assertEqual(calls,[True,False,True])
  finally:r.stop()

 def test_profile_change_flushes_old_events_and_requires_matching_ack(self):
  r=Relay();old=r.session;r.publish('up')
  r.offer_browser_profile('analog',.25,'1:7:document-A')
  p=r.browser_profile();self.assertNotEqual(r.session,old);self.assertEqual(p['revision'],1)
  self.assertFalse(p['applied']);self.assertEqual(list(r.events),[])
  r.publish('down');self.assertEqual(r.snapshot(0,r.session)['events'],[])
  r.acknowledge_browser_profile(0);self.assertFalse(r.browser_profile()['applied'])
  r.acknowledge_browser_profile(1);self.assertEqual(r.snapshot(0,r.session)['events'],[])
  r.publish('up');self.assertEqual(r.snapshot(0,r.session)['events'][0]['direction'],'up')
  session=r.session;r.offer_browser_profile('analog',.25,'1:7:document-A')
  self.assertEqual(r.session,session);self.assertEqual(r.browser_profile()['revision'],1)
  r.offer_browser_profile('discrete',.25,'1:7:document-A')
  self.assertNotEqual(r.session,session);self.assertEqual(r.browser_profile()['revision'],2)

 def test_lease_renews_without_reset_and_expires_to_desktop_profile(self):
  r=Relay()
  with patch('core.room_gesture_relay.time.monotonic',return_value=10):r.offer_browser_profile('analog',None)
  session=r.session
  with patch('core.room_gesture_relay.time.monotonic',return_value=10.8):r.offer_browser_profile('analog',None)
  with patch('core.room_gesture_relay.time.monotonic',return_value=11.2):self.assertEqual(r.browser_profile()['mode'],'analog')
  self.assertEqual(r.session,session)
  with patch('core.room_gesture_relay.time.monotonic',return_value=11.81):
   p=r.browser_profile();self.assertIsNone(p['mode']);self.assertEqual(p['revision'],2);self.assertFalse(p['applied'])
  self.assertNotEqual(r.session,session)

 def test_invalid_profile_cannot_change_state_or_open_a_command_surface(self):
  r=Relay();session=r.session
  for args in [('shell',.2,''),('analog',True,''),('analog',float('nan'),''),('analog',.61,''),('analog',.1,''),('analog',.2,'http://site'),('analog',.2,'x'*201)]:
   with self.assertRaises(ValueError):r.offer_browser_profile(*args)
  self.assertEqual(r.session,session);self.assertEqual(r.browser_profile()['revision'],0)

 def test_http_only_accepts_exact_protocol_and_existing_origin_host_guards(self):
  r=Relay(port=0);r.start();base=f'http://127.0.0.1:{r.port}/events'
  extension='a'*32
  def get(query,headers=None):
   request=urllib.request.Request(base+query,headers=headers if headers is not None else {'X-Jarvis-Extension':extension})
   with urllib.request.urlopen(request,timeout=2) as response:return json.load(response)
  try:
   p=get('?protocol=3&mode=analog&span=0.25&target=1:7:doc')['profile']
   self.assertEqual((p['mode'],p['span'],p['revision']),('analog',.25,1))
   for query,headers,code in [
    ('?protocol=3&mode=discrete',{},403),
    ('?protocol=3&mode=discrete',{'X-Jarvis-Extension':extension,'Origin':'https://evil.test'},403),
    ('?protocol=3&mode=discrete',{'X-Jarvis-Extension':extension,'Host':'evil.test'},403),
    ('?protocol=2&mode=analog',None,400),('?protocol=3&mode=analog&span=nan',None,400),
    ('?protocol=3&mode=analog&mode=discrete',None,400),('?protocol=3&mode=',None,400),
    ('?protocol=3&mode=analog&span=',None,400)]:
    with self.assertRaises(urllib.error.HTTPError) as e:get(query,headers)
    self.assertEqual(e.exception.code,code)
   self.assertEqual(r.browser_profile()['revision'],1)
  finally:r.stop()


class Overlay(unittest.TestCase):
 def test_only_browser_mode_and_optional_span_are_overlaid_without_writing(self):
  saved=settings({'mode':'discrete','analog_span':.4,'swap_hands':True})
  copied=json.loads(json.dumps(saved))
  overlay=browser_runtime_config({'mode':'analog','span':.2,'revision':1})
  effective=runtime_settings(saved,overlay)
  self.assertEqual((effective['mode'],effective['analog_span']),('analog',.2))
  self.assertEqual(effective['rules'],saved['rules']);self.assertTrue(effective['swap_hands']);self.assertEqual(saved,copied)
  self.assertEqual(runtime_settings(saved,None),saved)
  self.assertEqual(runtime_settings(saved,browser_runtime_config({'mode':'analog','revision':2}))['analog_span'],.4)

 def test_worker_rejects_invalid_revisions_modes_and_nonfinite_ranges(self):
  for change in [{'mode':'shell'},{'revision':True},{'revision':0},{'revision':2**53},{'span':float('inf')},{'span':True},{'span':.9},{'distance':True},{'distance':float('nan')},{'distance':.03},{'distance':.21}]:
   with self.assertRaises(ValueError):browser_runtime_config(dict(mode='analog',span=.2,revision=1,**{})|change)

 def test_ordinary_range_overrides_saved_distance_without_touching_analog_span(self):
  overlay=browser_runtime_config(dict(mode='discrete',span=.37,distance=.04,revision=1))
  self.assertEqual(runtime_distance(.20,overlay),.04)
  self.assertEqual(runtime_distance(.20,None),.20)
  self.assertEqual(runtime_settings(settings(),overlay)['analog_span'],.37)


class Controller(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
  self.patches=[patch.object(panel,'DATA_DIR',self.root),patch.object(panel,'load_preferences',return_value={})]
  for p in self.patches:p.start()
  self.window=QWidget();self.c=panel.GestureController(self.window);self.c._browser_timer.stop()
  self.c.process=S(poll=lambda:None,stdin=io.StringIO());self.c.ready=True;self.c.relay=Relay()
 def tearDown(self):
  self.c.process=None;self.window.close()
  for p in reversed(self.patches):p.stop()
  self.directory.cleanup()
 def test_status_reports_running_and_ready_separately(self):
  c=self.c;c.process=None;c.ready=False
  self.assertEqual(c.camera_snapshot()['state'],'off')
  c.process=S(poll=lambda:None);self.assertEqual(c.camera_snapshot()['state'],'starting')
  c.ready=True;self.assertEqual(c.camera_snapshot()['state'],'on')
  c.process=S(poll=lambda:1);self.assertEqual(c.camera_snapshot()['state'],'off')
  c.process=None;c._browser_timer.stop()

 def apply(self,mode,span=.25):
  self.c.relay.offer_browser_profile(mode,span,'1:7:document')
  self.c.poll_browser_profile();return self.c._browser_revision
 def ack(self,revision,mode):self.c.receive(dict(type='profile_applied',revision=revision,mode=mode))
 def test_pointer_packets_are_fresh_deduplicated_and_relayed_only_in_mouse_mode(self):
  c=self.c;c.control_mode='mouse';now=time.monotonic()
  packet=dict(type='pointer',id=1,action='pointer',phase='move',x=.4,y=.3,mode='mouse',captured_monotonic=now)
  c.receive(packet);self.assertEqual(len(c.relay.events),1)
  c.receive(packet);self.assertEqual(len(c.relay.events),1)
  c.receive(packet|dict(id=2,captured_monotonic=now-1));self.assertEqual(len(c.relay.events),1)
  c.receive(packet|dict(id=3,mode='system_mouse'));self.assertEqual(len(c.relay.events),1)
  c.receive(packet|dict(id=4,phase='cancel'));self.assertEqual(c.relay.events[-1]['phase'],'cancel')

 def test_ordinary_popup_range_reaches_worker_and_multistep_packet_reaches_relay(self):
  c=self.c;c.relay.offer_browser_profile('discrete',.37,'range-test',distance=.04)
  c.poll_browser_profile();command=json.loads(c.process.stdin.getvalue().splitlines()[-1])
  self.assertEqual(command['distance'],.04);self.assertEqual(command['span'],.37)
  self.ack(c._browser_revision,'discrete')
  event=dict(type='action',id=1,mode='discrete',profile_revision=c._browser_revision,
             action='up',swipe_steps=3,captured_monotonic=time.monotonic())
  c.receive(event);self.assertEqual(c.relay.snapshot(0,c.relay.session)['events'][0]['swipe_steps'],3)
  for i,count in enumerate((True,0,5,1.5),2):c.receive(dict(event,id=i,swipe_steps=count))
  self.assertEqual(c.relay.sequence,1)
 def test_profile_is_volatile_and_clear_restores_latest_saved_desktop_mode(self):
  save_settings(self.root/'config/gesture-actions.json',settings({'mode':'discrete','analog_span':.4}))
  original=(self.root/'config/gesture-actions.json').read_bytes();c=self.c
  revision=self.apply('analog');self.assertEqual(c.control_mode,'discrete');self.assertEqual(c.effective_mode,'analog')
  sent=json.loads(c.process.stdin.getvalue().splitlines()[-1]);self.assertEqual(sent,dict(command='runtime_config',mode='analog',span=.25,revision=revision))
  self.assertEqual((self.root/'config/gesture-actions.json').read_bytes(),original)
  self.ack(revision,'analog');self.assertTrue(c.relay.browser_profile()['applied'])
  c.relay._browser_expires=time.monotonic()-1;c.poll_browser_profile()
  self.assertIsNone(c._browser_mode);self.assertEqual(c.effective_mode,'discrete')
  self.assertEqual(json.loads(c.process.stdin.getvalue().splitlines()[-1])['mode'],None)

 def test_all_old_actions_are_dropped_until_matching_worker_ack_and_revision(self):
  c=self.c;revision=self.apply('analog')
  def action(i,rev):c.receive(dict(type='action',id=i,mode='analog',profile_revision=rev,action='right',continuous=True,amount=2.,steps=1,captured_monotonic=time.monotonic()))
  action(1,revision);self.assertEqual(c.relay.sequence,0)
  self.ack(revision-1,'analog');self.assertFalse(c._worker_profile_ready)
  self.ack(revision,'discrete');self.assertFalse(c._worker_profile_ready)
  self.ack(revision,'analog');action(2,revision-1);self.assertEqual(c.relay.sequence,0)
  action(3,revision);self.assertEqual(c.relay.sequence,1)
  revision2=self.apply('discrete');self.assertGreater(revision2,revision);self.ack(revision2,'discrete')
  c.receive(dict(type='action',id=4,mode='discrete',profile_revision=revision,action='up'))
  self.assertEqual(c.relay.sequence,0)
  c.receive(dict(type='action',id=5,mode='discrete',profile_revision=revision2,action='up'))
  self.assertEqual(c.relay.sequence,1)

 def test_browser_profile_never_sends_media_keys_to_the_foreground_game(self):
  c=self.c;c.browser_media=False;revision=self.apply('discrete');self.ack(revision,'discrete')
  with patch('core.room_media_keys.dispatch_action',side_effect=AssertionError('No system media keys')):
   c.receive(dict(type='action',id=1,mode='discrete',profile_revision=revision,action='play_pause'))
  self.assertEqual(c.relay.snapshot(0,c.relay.session)['events'][0]['direction'],'play_pause')

 def test_old_action_between_http_offer_and_qt_tick_is_never_released_after_ack(self):
  c=self.c;c.control_mode='discrete';c.browser_media=False
  c.relay.offer_browser_profile('analog',.25,'1:7:document')
  self.assertEqual(c._browser_revision,0)
  with patch('core.room_media_keys.dispatch_action',side_effect=AssertionError('No stale system media key')):
   c.receive(dict(type='action',id=1,mode='discrete',profile_revision=0,action='play_pause'))
  c.poll_browser_profile();self.ack(c._browser_revision,'analog')
  self.assertEqual(c.relay.snapshot(0,c.relay.session)['events'],[])


if __name__=='__main__':unittest.main()
