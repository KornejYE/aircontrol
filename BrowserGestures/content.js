(()=>{
 const version='1.8.2';
 if(window.__airControlGestures?.version===version)return;
 window.__airControlGestures?.stop?.();
 function visible(element){
  if(!element || !element.getClientRects().length)return false;
  const rect=element.getBoundingClientRect();
  const style=getComputedStyle(element);
  return rect.width>0 && rect.height>0 && rect.bottom>0 && rect.right>0 && rect.top<innerHeight && rect.left<innerWidth && style.visibility!=='hidden' && style.display!=='none';
 }
 function videoForTarget(){
  // Shorts keeps adjacent, preloaded players in the DOM. Prefer its active reel.
  const current=[...document.querySelectorAll('ytd-reel-video-renderer[is-active] video, ytd-reel-video-renderer[active] video, [data-is-active="true"] video')].find(visible);
  if(current)return current;
  const videos=[...document.querySelectorAll('video')].filter(visible);
  return videos.find(v=>!v.paused && !v.ended)||videos[0];
 }
 function mediaPage(){
  if(/(^|\.)youtube\.com$/.test(location.hostname)&&/^\/(shorts\/|watch(?:\/|$))/.test(location.pathname))return true;
  const substantial=element=>{
   if(!visible(element))return false;
   const r=element.getBoundingClientRect();
   return Math.min(r.right,innerWidth)-Math.max(0,r.left)>=160
    &&Math.min(r.bottom,innerHeight)-Math.max(0,r.top)>=90;
  };
  if([...document.querySelectorAll('video')].some(substantial))return true;
  // Cross-origin movie players expose their fullscreen container, not their
  // private DOM. Never inspect an iframe's document or collect its contents.
  return [...document.querySelectorAll('iframe[allowfullscreen], iframe[allow*="fullscreen"]')].some(substantial);
 }
 function shortsStep(next){
  const selectors=next?['#navigation-button-down button','#navigation-button-down','button[aria-label="Next video"]','button[aria-label="Следующее видео"]']:['#navigation-button-up button','#navigation-button-up','button[aria-label="Previous video"]','button[aria-label="Предыдущее видео"]'];
  const button=selectors.map(s=>document.querySelector(s)).find(e=>visible(e) && !e.disabled);
  if(button){button.click();return;}
  // This event belongs only to the chosen page; it never sends a key to the game.
  document.dispatchEvent(new KeyboardEvent('keydown',{key:next?'ArrowDown':'ArrowUp',code:next?'ArrowDown':'ArrowUp',bubbles:true}));
 }
 let relaySession='',targetKey='',drag=null,lastDragSequence=0;
 let pendingSteps=0,stepsUntil=0,nextStepAt=0,stepsUnfocused=false,lastStepSequence=0;
 function clearSteps(){pendingSteps=0;stepsUntil=0;nextStepAt=0;}
 function addSteps(e,allowUnfocused){
  if(!Number.isInteger(e.id)||e.id<=lastStepSequence)return;
  lastStepSequence=e.id;
  const action=e.action||e.direction;
  if(!['up','down'].includes(action)){
   const unit=['left','right'].includes(action)?5:.05;
   apply(action,allowUnfocused,unit*e.swipe_steps);return;
  }
  if(!isShorts()){apply(action,allowUnfocused,.7*e.swipe_steps);return;}
  pendingSteps=Math.max(-8,Math.min(8,pendingSteps+((e.action||e.direction)==='up'?1:-1)*e.swipe_steps));
  stepsUntil=Date.now()/1000+1.3;stepsUnfocused=allowUnfocused;
 }
 function pumpSteps(){
  if(!pendingSteps)return;
  const now=Date.now()/1000;
  if(now>stepsUntil||activeMode!=='discrete'||!isShorts()||inputBlocked(stepsUnfocused)){clearSteps();return;}
  if(now<nextStepAt)return;
  const next=pendingSteps>0;pendingSteps+=next?-1:1;nextStepAt=now+.16;shortsStep(next);
 }
 const isShorts=()=>/(^|\.)youtube\.com$/.test(location.hostname)&&location.pathname.startsWith('/shorts/');
 function inputBlocked(allowUnfocused){
  const active=document.activeElement;
  return document.hidden||(!allowUnfocused&&!document.hasFocus())||active?.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(active?.tagName||'');
 }
 function scrollTarget(shorts){
  if(shorts){
   // Verified native Shorts feed: its own height excludes YouTube's header.
   // No button/Arrow fallback: a partial drag must never mean "next video".
   const feed=document.querySelector('ytd-shorts #shorts-container')||document.querySelector('#shorts-container');
   return feed&&feed.clientHeight>50&&feed.scrollHeight>feed.clientHeight+1&&getComputedStyle(feed).overflowY!=='clip'?feed:null;
  }
  let node=document.elementFromPoint(innerWidth*.5,innerHeight*.5);
  while(node&&node!==document.body&&node!==document.documentElement){
   if(node.clientHeight>50&&node.scrollHeight>node.clientHeight+1&&/^(auto|scroll|hidden)$/.test(getComputedStyle(node).overflowY))return node;
   node=node.parentElement;
  }
  const root=document.scrollingElement||document.documentElement;
  return root&&root.clientHeight>0&&root.scrollHeight>root.clientHeight+1?root:null;
 }
 function pageUnit(feed,shorts){
  const height=feed.clientHeight;
  if(!shorts)return height;
  const anchors=Array.from(feed.querySelectorAll?.('ytd-reel-video-renderer')||[])
   .map(e=>e.getBoundingClientRect().top).filter(Number.isFinite).sort((a,b)=>a-b);
  const gaps=anchors.slice(1).map((top,i)=>top-anchors[i]).filter(gap=>gap>height*.5&&gap<height*1.5).sort((a,b)=>a-b);
  return gaps.length?gaps[Math.floor(gaps.length/2)]:height;
 }
 function finishDrag(commit=false){
  if(!drag)return;
  const ending=drag;drag=null;
  if(ending.frame)cancelAnimationFrame(ending.frame);
  // Round toward zero, while snap is STILL disabled: 0.9 of a reel returns
  // to its starting reel; 1.2 finishes exactly one, never the nearest two.
  if(ending.element.isConnected!==false&&ending.shorts){
   const position=commit===true?ending.position:ending.rendered;
   const whole=Math.trunc(position+Math.sign(position)*1e-7);
   // The feed may recycle earlier reels and rebase scrollTop while held.
   // Settle relative to the distance actually drawn, never a stale DOM origin.
   ending.element.scrollTop=Math.max(0,Math.min(ending.element.scrollHeight-ending.element.clientHeight,
    ending.element.scrollTop+(whole-ending.rendered)*ending.unit));
  }else if(ending.element.isConnected!==false&&commit===true){
   ending.element.scrollTop=Math.max(0,Math.min(ending.element.scrollHeight-ending.element.clientHeight,
    ending.element.scrollTop+(ending.position-ending.rendered)*ending.unit));
  }
  for(const [name,value,priority] of ending.styles){
   if(value)ending.element.style.setProperty(name,value,priority);
   else ending.element.style.removeProperty(name);
  }
 }
 function validDragTarget(){
  return drag&&drag.element.isConnected!==false&&drag.shorts===isShorts()
   &&(drag.shorts||drag.path===location.pathname)&&!inputBlocked(drag.allowUnfocused);
 }
 function animateDrag(){
  if(!drag||drag.frame)return;
  drag.frame=requestAnimationFrame(drawDrag);
 }
 function drawDrag(stamp){
  if(!drag)return;
  drag.frame=0;
  if(!validDragTarget()||Date.now()/1000-drag.last>.4){finishDrag();return;}
  const elapsed=drag.frameAt?Math.max(1,Math.min(32,stamp-drag.frameAt)):16;
  drag.frameAt=stamp;
  const remaining=drag.position-drag.rendered;
  if(Math.abs(remaining*drag.unit)<.25){
   if(remaining)moveDrag(remaining);
   return;
  }
  // Display-rate following, with a short bounded easing tail; no prediction,
  // velocity, queued Next clicks or continued motion beyond the hand target.
  // Limit each frame so a lazy native feed can load its next reel in between.
  const step=Math.max(-.5,Math.min(.5,remaining*(1-Math.exp(-elapsed/18))));
  moveDrag(step);
  const rest=drag.position-drag.rendered;
  if(Math.abs(rest*drag.unit)>=.25)animateDrag();
  else if(rest)moveDrag(rest);
 }
 function moveDrag(distance){
  const element=drag.element,before=element.scrollTop;
  element.scrollTop=Math.max(0,Math.min(element.scrollHeight-element.clientHeight,before+distance*drag.unit));
  // A loaded edge is not completed travel. Keep the unconsumed hand target
  // only for this fresh grab, so newly appended reels can consume it later.
  drag.rendered+=(element.scrollTop-before)/drag.unit;
 }
 function dragEvent(e,allowUnfocused){
  if(!['Right','Left'].includes(e.hand)||typeof e.gesture_id!=='string'||!/^[A-Za-z0-9:_-]{1,96}$/.test(e.gesture_id)
   ||!['start','move','end','cancel'].includes(e.phase)||!Number.isFinite(e.position)||Math.abs(e.position)>8
   ||!Number.isInteger(e.id)||e.id<=lastDragSequence||(e.phase==='start'&&e.position!==0))return;
  lastDragSequence=e.id;
  const matches=drag&&drag.id===e.gesture_id&&drag.hand===e.hand;
  if(e.phase==='start'){
   if(matches)return;
   if(drag&&drag.hand!==e.hand)return; // one physical scroll surface at a time
   finishDrag();
   if(inputBlocked(allowUnfocused))return;
   const shorts=isShorts(),element=scrollTarget(shorts);
   if(!element||!element.style)return;
   const styles=['scroll-snap-type','scroll-behavior','overflow-anchor'].map(name=>[name,element.style.getPropertyValue(name),element.style.getPropertyPriority(name)]);
   element.style.setProperty('scroll-snap-type','none','important');
   element.style.setProperty('scroll-behavior','auto','important');
   element.style.setProperty('overflow-anchor','none','important');
   drag={element,styles,shorts,unit:pageUnit(element,shorts),position:0,rendered:0,frame:0,frameAt:0,
         id:e.gesture_id,hand:e.hand,path:location.pathname,allowUnfocused,last:Date.now()/1000};
   return;
  }
  if(!matches)return;
  if(!validDragTarget()){finishDrag();return;}
  drag.last=Date.now()/1000;
  if(e.phase!=='cancel'){
   drag.position=e.position;
   animateDrag();
  }
  if(e.phase==='end'||e.phase==='cancel')finishDrag(e.phase==='end');
 }
 function apply(action,allowUnfocused,amount=null,steps=0){
  if(document.hidden || (!allowUnfocused && !document.hasFocus()))return;
  const active=document.activeElement;
  if(active?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(active?.tagName||''))return;
  const shorts=/(^|\.)youtube\.com$/.test(location.hostname)&&location.pathname.startsWith('/shorts/');
  if(shorts && ['up','down','next_track','previous_track'].includes(action)){
   if(amount!==null){
    // Old distance-to-click packets are intentionally not interpreted as
    // touch motion. Only the lifecycle protocol can own a partial scroll.
    return;
   }
   shortsStep(action==='up'||action==='next_track');return;
  }
  if(action==='up'||action==='down'){
   const point=document.elementFromPoint(innerWidth*.5,innerHeight*.5);let el=point;
   while(el && el!==document.body && !(el.scrollHeight>el.clientHeight+30&&/(auto|scroll)/.test(getComputedStyle(el).overflowY)))el=el.parentElement;
   (el&&el!==document.body?el:window).scrollBy({top:innerHeight*(amount===null?.7:amount)*(action==='up'?1:-1),behavior:'smooth'});return;
  }
  const video=videoForTarget();
  if(action==='left'||action==='right'){
   if(video && Number.isFinite(video.duration))video.currentTime=Math.min(video.duration,Math.max(0,video.currentTime+(amount===null?5:amount)*(action==='right'?1:-1)));
   else window.scrollBy({left:innerWidth*(amount===null?.6:amount/5*.6)*(action==='right'?1:-1),behavior:'smooth'});
  }else if(video && action==='play_pause'){
   if(video.paused)Promise.resolve(video.play()).catch(()=>{});else video.pause();
  }else if(video && (action==='volume_up'||action==='volume_down')){
   video.volume=Math.max(0,Math.min(1,video.volume+(amount===null?.05:amount)*(action==='volume_up'?1:-1)));
   if(action==='volume_up')video.muted=false;
  }else if(video && action==='mute')video.muted=!video.muted;
  else if(action==='next_track'||action==='previous_track'){
   const button=document.querySelector(action==='next_track'?'.ytp-next-button':'.ytp-prev-button');
   if(visible(button) && button.getAttribute('aria-disabled')!=='true')button.click();
  }
 }
 let airMouse=null;
 function stopMouse(){airMouse?.destroy();airMouse=null;}
 function pointerEvent(e,allowUnfocused){
  if(!airMouse&&window.__AirControlBrowserAirMouse)airMouse=new window.__AirControlBrowserAirMouse();
  airMouse?.handle(e,allowUnfocused);
 }
 window.addEventListener('keydown',e=>{
  if(!e.isTrusted)return;
  airMouse?.pause();
  if(e.key==='Escape'&&['mouse','system_mouse'].includes(activeMode)){
   stopMouse();chrome.runtime.sendMessage({type:'pointer_stop'}).catch(()=>{});
  }
 });
 window.addEventListener('pointermove',e=>{if(e.isTrusted&&e.pointerType==='mouse')airMouse?.pause();},{passive:true});
 let busy=false,activeMode=null,activePreference='auto';
 // Keep polling a visible selected window while a game has keyboard focus.
 // The background worker checks the explicit opt-in and the exact tab/document.
 const startedAt=Date.now()/1000;
 let visibleSince=startedAt,focusSince=startedAt,wasVisible=!document.hidden,wasFocused=document.hasFocus();
 window.addEventListener('pageshow',()=>{clearSteps();finishDrag();visibleSince=Date.now()/1000;focusSince=visibleSince;wasVisible=!document.hidden;});
 window.addEventListener('pagehide',()=>{clearSteps();finishDrag();});
 window.addEventListener('wheel',()=>{clearSteps();finishDrag();},{passive:true});
 window.addEventListener('pointerdown',()=>{clearSteps();finishDrag();},{passive:true});
 const timer=setInterval(async()=>{
  const now=Date.now()/1000,focused=document.hasFocus();
  if(drag&&(!validDragTarget()||now-drag.last>.4||now<drag.last-.1))finishDrag();
  airMouse?.tick();
  if(document.hidden){stopMouse();clearSteps();finishDrag();wasVisible=false;wasFocused=focused;return;}
  if(!wasVisible){wasVisible=true;visibleSince=now;}
  if(focused && !wasFocused)focusSince=now;
  wasFocused=focused;
  if(busy)return;busy=true;
  try{
   const active=document.activeElement;
   const zoomAllowed=!(active?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(active?.tagName||''));
   const media=mediaPage();
   if(activePreference==='auto'&&activeMode&&(isShorts()?'discrete':'analog')!==activeMode)finishDrag();
   const data=await chrome.runtime.sendMessage({type:'poll',zoomAllowed,media});
   if(!data?.enabled||data.available===false||!data.session){stopMouse();clearSteps();finishDrag();return;}
   const desired=data.preference==='auto'?(isShorts()?'discrete':'analog'):data.preference;
   if(!data.profile?.applied||data.profile.mode!==desired){stopMouse();clearSteps();finishDrag();return;}
   if(activeMode!==desired){stopMouse();clearSteps();finishDrag();lastDragSequence=0;lastStepSequence=0;}
   activeMode=desired;activePreference=data.preference;
   if(data.session!==relaySession||data.targetKey!==targetKey){stopMouse();clearSteps();finishDrag();lastDragSequence=0;lastStepSequence=0;}
   relaySession=data.session;targetKey=data.targetKey;
   let scroll=0;const shorts=/(^|\.)youtube\.com$/.test(location.hostname)&&location.pathname.startsWith('/shorts/');
   for(const event of data.events||[]){
    const allowedFrom=data.allowUnfocused===true?visibleSince:Math.max(visibleSince,focusSince);
    const action=event.action||event.direction;
    if(!Number.isFinite(event.time)||event.time<allowedFrom||event.time>Date.now()/1000+.1||Date.now()/1000-event.time>=((event.continuous===true||['drag_scroll','pointer'].includes(action))?.30:1.2))continue;
    if(action==='pointer'){if(activeMode==='mouse')pointerEvent(event,data.allowUnfocused===true);continue;}
    if(activeMode==='mouse'||activeMode==='system_mouse')continue;
    if('swipe_steps' in event){
     if(activeMode==='discrete'&&['up','down','left','right','volume_up','volume_down'].includes(action)&&event.continuous!==true&&Number.isInteger(event.swipe_steps)&&event.swipe_steps>=1&&event.swipe_steps<=4)addSteps(event,data.allowUnfocused===true);
     continue;
    }
    if(action==='drag_scroll'){if(activeMode==='analog')dragEvent(event,data.allowUnfocused===true);continue;}
    if(event.continuous===true){
     if(activeMode!=='analog')continue;
     const limit={up:3,down:3,left:20,right:20,volume_up:.3,volume_down:.3}[action];
     if(!Number.isFinite(event.amount)||!(event.amount>0&&event.amount<=limit)||!Number.isInteger(event.steps)||event.steps<0||event.steps>4)continue;
     if(!shorts&&(action==='up'||action==='down'))scroll+=event.amount*(action==='up'?1:-1);
     else apply(action,data.allowUnfocused===true,event.amount,event.steps);
    }else apply(action,data.allowUnfocused===true);
   }
   if(scroll)apply(scroll>0?'up':'down',data.allowUnfocused===true,Math.min(6,Math.abs(scroll)));
   pumpSteps();
  }catch{stopMouse();clearSteps();finishDrag();}finally{busy=false;}
 },25);
 window.__airControlGestures={version,stop:()=>{stopMouse();clearSteps();finishDrag();clearInterval(timer);}};
})();
