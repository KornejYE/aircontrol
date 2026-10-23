let cursor=0,session='',lastPoll=0,inFlight=false;
let preferenceCache=null,preferenceRead=null,preferenceEpoch=0,lastProfile=null;
function normalizePreferences(value){
 return {scope:['tab','window','browser'].includes(value?.scope)?value.scope:'browser',mode:['auto','analog','discrete','mouse','system_mouse'].includes(value?.mode)?value.mode:'auto',
  span:typeof value?.span==='number'&&Number.isFinite(value.span)?Math.max(.12,Math.min(.60,value.span)):.20,
  distance:typeof value?.distance==='number'&&Number.isFinite(value.distance)?Math.max(.04,Math.min(.20,value.distance)):.085};
}
async function preferences(){
 if(preferenceCache)return preferenceCache;
 if(!preferenceRead){
  const epoch=preferenceEpoch;
  preferenceRead=chrome.storage.local.get('gesturePreferences').then(data=>{
   if(epoch===preferenceEpoch)preferenceCache=normalizePreferences(data.gesturePreferences);
   return preferenceCache||normalizePreferences();
  }).finally(()=>{preferenceRead=null;});
 }
 return preferenceRead;
}
chrome.storage.onChanged.addListener((changes,area)=>{
 if(area==='local'&&changes.gesturePreferences){
  preferenceEpoch++;preferenceCache=normalizePreferences(changes.gesturePreferences.newValue);lastProfile=null;
 }
});
const actions=new Set(['up','down','left','right','play_pause','volume_up','volume_down','mute','next_track','previous_track','zoom_in','zoom_out','drag_scroll','pointer']);
const zoomActions=new Set(['zoom_in','zoom_out']);
const armedKeys=['armedTab','armedWindow','armedAt','armedDocumentId','armedOrigin','allowUnfocused','armedScope'];
const disabled=()=>({enabled:false,allowUnfocused:false,events:[]});
let selectedDocument='',selectedSince=0;
async function targetFor(sender){
 const [arm,prefs]=await Promise.all([chrome.storage.session.get(armedKeys),preferences()]);
 if(prefs.mode==='system_mouse'||arm.armedScope==='system')return null;
 if(sender.frameId!==0 || !arm.armedAt || !/^https?:/.test(sender.url||sender.tab?.url||''))return null;
 const scope=arm.armedScope||(Number.isInteger(arm.armedWindow)?'window':'tab');
 if(scope==='tab'&&sender.tab?.id!==arm.armedTab)return null;
 if(scope==='window'&&sender.tab?.windowId!==arm.armedWindow)return null;
 if(scope==='browser'){
  const selected=await chrome.windows.getLastFocused({windowTypes:['normal']});
  if(selected?.id!==sender.tab?.windowId)return null;
 }
 const windowId=sender.tab.windowId;
 const [win,tabs]=await Promise.all([
  chrome.windows.get(windowId),chrome.tabs.query({active:true,windowId})
 ]);
 if(win.state==='minimized' || tabs[0]?.id!==sender.tab.id)return null;
 if(!win.focused && arm.allowUnfocused!==true)return null;
 const key=`${arm.armedAt}:${scope}:${sender.tab.windowId}:${sender.tab.id}:${sender.documentId}:${prefs.mode}:${prefs.span}:${prefs.distance}`;
 if(key!==selectedDocument){selectedDocument=key;selectedSince=Date.now()/1000;}
 return {...arm,armedTab:sender.tab.id,targetKey:key,targetSince:selectedSince,prefs};
}
function sameTarget(current,arm){return current && current.targetKey===arm.targetKey && current.armedAt===arm.armedAt;}
// Optional web access is requested once from the extension popup. The content
// script only executes commands after the selected-window / visible-tab checks.
async function ensureScripts(){
 if(!await chrome.permissions.contains({origins:['http://*/*','https://*/*']}))return;
 const scripts=await chrome.scripting.getRegisteredContentScripts({ids:['aircontrol-gestures']});
 const spec={id:'aircontrol-gestures',matches:['http://*/*','https://*/*'],js:['pointer.js','content.js'],runAt:'document_idle',persistAcrossSessions:true};
 if(scripts.length)await chrome.scripting.updateContentScripts([spec]);
 else await chrome.scripting.registerContentScripts([spec]);
}
chrome.runtime.onInstalled.addListener(()=>{ensureScripts().catch(()=>{});});
chrome.runtime.onStartup.addListener(()=>{ensureScripts().catch(()=>{});});
chrome.tabs.onActivated.addListener(async info=>{
 try{
  const arm=await chrome.storage.session.get(armedKeys);
  if(arm.armedAt&&(arm.armedScope==='browser'||info.windowId===arm.armedWindow||info.tabId===arm.armedTab))await chrome.scripting.executeScript({target:{tabId:info.tabId},files:['pointer.js','content.js']});
 }catch{} // Internal Chrome pages cannot run content scripts.
});
chrome.windows.onFocusChanged.addListener(async windowId=>{
 try{
  const arm=await chrome.storage.session.get(armedKeys);
  if(!arm.armedAt||arm.armedScope!=='browser'||windowId<0)return;
  const [tab]=await chrome.tabs.query({active:true,windowId});
  if(tab)await chrome.scripting.executeScript({target:{tabId:tab.id},files:['pointer.js','content.js']});
 }catch{}
});
async function zoomTarget(sender,arm,action){
 if(!sameTarget(await targetFor(sender),arm))return;
 // Chrome defaults to zoom shared by origin. Limit this gesture to the chosen tab.
 await chrome.tabs.setZoomSettings(arm.armedTab,{mode:'automatic',scope:'per-tab'});
 const scale=await chrome.tabs.getZoom(arm.armedTab);
 if(!Number.isFinite(scale) || !sameTarget(await targetFor(sender),arm))return;
 const next=Math.min(3,Math.max(.5,Math.round(scale*(action==='zoom_in'?1.1:1/1.1)*100)/100));
 if(next!==scale)await chrome.tabs.setZoom(arm.armedTab,next);
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(message.type==='register'){ensureScripts().then(()=>reply({ok:true})).catch(()=>reply({ok:false}));return true;}
 if(message.type==='pointer_stop'){
  (async()=>{
   const arm=await targetFor(sender);
   if(!arm||!['mouse','system_mouse'].includes(arm.prefs.mode))return {ok:false};
   await chrome.storage.session.remove(armedKeys);
   await fetch('http://127.0.0.1:8767/camera/off',{method:'POST',headers:{'X-Jarvis-Extension':chrome.runtime.id},signal:AbortSignal.timeout(4000)});
   return {ok:true};
  })().then(reply).catch(()=>reply({ok:false}));return true;
 }
 if(message.type==='gesture_status'){
  (async()=>{
   const [[tab],arm]=await Promise.all([chrome.tabs.query({active:true,currentWindow:true}),chrome.storage.session.get(armedKeys)]);
   const fresh=lastProfile&&Date.now()-lastProfile.time<1200&&lastProfile.tabId===tab?.id&&lastProfile.armedAt===arm.armedAt;
   let camera=null;
   try{
    const response=await fetch('http://127.0.0.1:8767/camera/status',{cache:'no-store',headers:{'X-Jarvis-Extension':chrome.runtime.id},signal:AbortSignal.timeout(500)});
    if(response.ok)camera=await response.json();
   }catch{}
   return {...(fresh?{mode:lastProfile.mode,reason:lastProfile.reason,available:lastProfile.available}:{mode:null,available:false}),camera};
  })().then(reply).catch(()=>reply({mode:null,available:false}));return true;
 }
 if(message.type!=='poll')return;
 (async()=>{
  const arm=await targetFor(sender);
  if(!arm)return disabled();
  const page=new URL(sender.url||sender.tab.url);
  const shorts=/(^|\.)youtube\.com$/.test(page.hostname)&&page.pathname.startsWith('/shorts/');
  const mode=arm.prefs.mode==='auto'?(shorts?'discrete':'analog'):arm.prefs.mode;
  const recent=lastProfile&&lastProfile.targetKey===arm.targetKey&&lastProfile.mode===mode&&Date.now()-lastProfile.time<300;
  const enabled={enabled:true,allowUnfocused:arm.allowUnfocused===true,events:[],session,targetKey:arm.targetKey,available:!!session,preference:arm.prefs.mode,profile:recent?lastProfile.profile:null};
  if(inFlight || Date.now()-lastPoll<20)return enabled;
  inFlight=true;lastPoll=Date.now();
  try{
   const profileQuery=`&mode=${mode}&span=${arm.prefs.span}&distance=${arm.prefs.distance}&target=${encodeURIComponent(arm.targetKey)}`;
   const res=await fetch(`http://127.0.0.1:8767/events?after=${cursor}&session=${session}&protocol=3${profileQuery}`,{cache:'no-store',headers:{'X-Jarvis-Extension':chrome.runtime.id},signal:AbortSignal.timeout(300)});
   if(!res.ok)return {...enabled,available:false};
   const data=await res.json();const previous=session;session=data.session;cursor=data.cursor;
   if(typeof session!=='string'||!session)return {...enabled,available:false};
   // Never deliver a response that was in flight when the selected target changed.
   const current=await targetFor(sender);
   if(!sameTarget(current,arm))return disabled();
   const profile=data.profile;
   const applied=profile?.applied===true&&profile.mode===mode&&profile.span===arm.prefs.span&&profile.distance===arm.prefs.distance;
   lastProfile={mode,reason:arm.prefs.mode==='auto'?(shorts?'shorts':'page'):'manual',available:applied,tabId:sender.tab.id,time:Date.now(),armedAt:arm.armedAt,targetKey:arm.targetKey,profile:applied?profile:null};
   const now=Date.now()/1000;
   const events=applied&&previous===session && Array.isArray(data.events)?data.events.filter(e=>{
    const action=e.action||e.direction;
    if(!actions.has(action)||!Number.isFinite(e.time)||now-e.time>=((e.continuous===true||['drag_scroll','pointer'].includes(action))?.30:1.2)||e.time>now+.1||e.time<Math.max(arm.armedAt,arm.targetSince))return false;
    if(action==='pointer')return mode==='mouse'&&['move','click','context','down','up','scroll','cancel'].includes(e.phase)&&['x','y'].every(k=>Number.isFinite(e[k])&&e[k]>=0&&e[k]<=1)&&(e.phase!=='scroll'||(Number.isFinite(e.dy)&&Math.abs(e.dy)<=1));
    if('swipe_steps' in e)return mode==='discrete'&&['up','down','left','right','volume_up','volume_down'].includes(action)&&e.continuous!==true&&Number.isInteger(e.swipe_steps)&&e.swipe_steps>=1&&e.swipe_steps<=4;
    if(action==='drag_scroll')return ['Right','Left'].includes(e.hand)&&typeof e.gesture_id==='string'&&/^[A-Za-z0-9:_-]{1,96}$/.test(e.gesture_id)&&['start','move','end','cancel'].includes(e.phase)&&Number.isFinite(e.position)&&Math.abs(e.position)<=8&&(e.phase!=='start'||e.position===0);
    if(e.continuous===true){
     const limit={up:3,down:3,left:20,right:20,volume_up:.3,volume_down:.3}[action];
     return Number.isFinite(e.amount)&&e.amount>0&&e.amount<=limit&&Number.isInteger(e.steps)&&e.steps>=0&&e.steps<=4;
    }
    return true;
   }):[];
   let zoomRequested=false;
   for(const event of events){
    const action=event.action||event.direction;
    if(zoomActions.has(action) && message.zoomAllowed===true){zoomRequested=true;await zoomTarget(sender,arm,action);}
   }
   // The response was validated after fetch above. Only zoom adds asynchronous
   // work afterward and therefore needs another target check before delivery.
   if(zoomRequested && !sameTarget(await targetFor(sender),arm))return disabled();
   return {...enabled,session,targetKey:arm.targetKey,available:true,profile:applied?profile:null,events:events.filter(e=>!zoomActions.has(e.action||e.direction))};
  }catch{return {...enabled,available:false};}finally{inFlight=false;}
 })().then(reply).catch(()=>reply(disabled()));return true;
});
