const status=document.getElementById('status');
const armButton=document.getElementById('arm'),stopButton=document.getElementById('stop');
const settingsButton=document.getElementById('settings-toggle'),settingsPanel=document.getElementById('settings');
let pendingControl=false,lastCameraError=false,lastCamera=null;
settingsButton.onclick=()=>{
 const open=settingsPanel.hidden;settingsPanel.hidden=!open;
 settingsButton.setAttribute('aria-expanded',String(open));
};
async function refreshControls(camera){
 if(camera)lastCamera=camera;
 camera=camera||lastCamera;
 const arm=await chrome.storage.session.get(['armedAt']);
 const enabled=(!!arm.armedAt||camera?.mode==='system_mouse')&&camera?.state!=='off';
 armButton.hidden=enabled;stopButton.hidden=!enabled;
}
function controlBusy(value){pendingControl=value;armButton.disabled=value;stopButton.disabled=value;}

const unfocused=document.getElementById('unfocused');
const scope=document.getElementById('scope');
const mode=document.getElementById('mode'),span=document.getElementById('span');
const spanValue=document.getElementById('span-value'),spanHelp=document.getElementById('span-help');
const current=document.getElementById('current'),saved=document.getElementById('saved');
let preferences={mode:'auto',span:.20,distance:.085},effectiveMode='analog';
function normalize(value){
 const raw=value&&typeof value==='object'?value:{};
 return {scope:['tab','window','browser'].includes(raw.scope)?raw.scope:'browser',mode:['auto','analog','discrete','mouse','system_mouse'].includes(raw.mode)?raw.mode:'auto',
  span:typeof raw.span==='number'&&Number.isFinite(raw.span)?Math.max(.12,Math.min(.60,raw.span)):.20,
  distance:typeof raw.distance==='number'&&Number.isFinite(raw.distance)?Math.max(.04,Math.min(.20,raw.distance)):.085};
}
function rangeMode(){return mode.value==='auto'?effectiveMode:mode.value;}
function configureRange(){
 document.getElementById('span-title').closest?.('section')?.toggleAttribute('hidden',['mouse','system_mouse'].includes(mode.value));
 const ordinary=rangeMode()==='discrete';
 span.min=ordinary?'4':'12';span.max=ordinary?'20':'60';span.step=ordinary?'0.5':'1';
 span.value=String(Math.round((ordinary?preferences.distance:preferences.span)*1000)/10);
 document.getElementById('span-title').textContent=ordinary?'Размах на один шаг':'Размах на одно видео';
 showRange();
}
function showRange(){
 const value=Number(span.value);
 spanValue.textContent=value+'%';span.setAttribute('aria-valuetext',value+' процентов высоты кадра');
 spanHelp.textContent=rangeMode()==='discrete'
  ?'Считается движение захвата пальцев, можно двигать только кистью. Длиннее мах — больше шагов прокрутки, перемотки или громкости. Меньше значение — короче движение.'
  :'Два ролика — движение на '+(value*2)+'% высоты кадра. Меньше значение — меньше размах руки.';
}
function showMode(){
 document.getElementById('mode-help').textContent=mode.value==='auto'
  ?'YouTube Shorts — обычное управление. Обычные ролики YouTube и все остальные страницы — аналоговое.'
  :mode.value==='mouse'?'Правая рука: указательный — курсор; щипок — клик; щипок с движением — перетаскивание; два пальца — прокрутка; большой и средний — меню страницы. Кулак останавливает. Скорость и рука выбираются в настройках жестов AirControl. Esc выключает управление. Физическая мышь временно получает приоритет.'
  :mode.value==='system_mouse'?'Управление настоящей мышью Mac. Требуется разрешение macOS. Кулак останавливает и отпускает кнопку; Esc останавливает до повторного включения, физическая мышь временно получает приоритет. При нажатии фокус может перейти из игры.'
  :mode.value==='analog'?'На всех страницах лента следует за движением руки. Удерживайте захват, чтобы протянуть дальше.'
  :'Короткое движение кистью — один шаг, длинный мах — несколько. Неподвижный захват не продолжает листать.';
}
async function refreshCurrent(){
 try{
  const state=await chrome.runtime.sendMessage({type:'gesture_status'});
  await refreshControls(state?.camera);
  const cameraState=document.getElementById('camera-state');
  if(state?.camera?.state==='on'&&lastCameraError&&!pendingControl){status.textContent='';lastCameraError=false;}
  cameraState.dataset.state=state?.camera?.state||'unknown';
  cameraState.textContent=state?.camera?.state==='on'?'Камера включена':state?.camera?.state==='starting'?'Камера запускается…':state?.camera?.state==='off'?'Камера выключена':'Нет связи с камерой AirControl';
  if(state?.camera?.pointer_error)status.textContent=state.camera.pointer_error;
  const native=state?.camera?.mode==='system_mouse'&&state.camera.state==='on';
  if(native)state.mode='system_mouse';
  const active=(native||state?.available===true)&&(['analog','discrete','mouse','system_mouse'].includes(state.mode));
  if(active&&effectiveMode!==state.mode){effectiveMode=state.mode;if(mode.value==='auto')configureRange();}
  current.parentElement.dataset.mode=active?state.mode:'';
  current.textContent=active?({analog:'Сейчас: аналоговое',discrete:'Сейчас: обычное',mouse:'Сейчас: мышь в браузере',system_mouse:'Сейчас: мышь Mac'}[state.mode])
   +(state.reason==='shorts'?' · YouTube Shorts':state.reason==='page'?' · страница':' · ваш выбор')
   :'Выберите окно с веб-страницей для управления.';
 }catch{current.textContent='Режим появится после выбора окна.';current.parentElement.dataset.mode='';}
}
const ready=Promise.all([
 chrome.storage.session.get(['armedTab','allowUnfocused']).then(arm=>{
  if(arm.armedTab!==undefined)unfocused.checked=arm.allowUnfocused===true;
 }),
 chrome.storage.local.get('gesturePreferences').then(data=>{
  preferences=normalize(data.gesturePreferences);scope.value=preferences.scope;mode.value=preferences.mode;showMode();configureRange();
 })
]).then(refreshCurrent).catch(()=>{showMode();showRange();saved.textContent='Не удалось загрузить настройки. Выберите их заново.';});
async function save(rangeChanged=false){
 await ready;
 try{
  preferences=normalize({...preferences,scope:scope.value,mode:mode.value,...(rangeChanged?{[rangeMode()==='discrete'?'distance':'span']:Number(span.value)/100}:{})});
  await chrome.storage.local.set({gesturePreferences:preferences});saved.textContent='Сохранено. Применяется к следующему жесту.';
  showMode();configureRange();await refreshCurrent();
 }catch{saved.textContent='Не удалось сохранить. Попробуйте ещё раз.';}
}
scope.onchange=async()=>{await save(false);const arm=await chrome.storage.session.get(['armedAt']);if(arm.armedAt)await document.getElementById('arm').onclick();};
async function desktopMode(value){
 const response=await fetch('http://127.0.0.1:8767/camera/mode/'+(value==='auto'?'restore':value),{method:'POST',headers:{'X-Jarvis-Extension':chrome.runtime.id},signal:AbortSignal.timeout(4000)});
 if(!response.ok)throw Error('Не удалось переключить режим AirControl.');
 const result=await response.json();if(!result.ok)throw Error(result.error||'Режим не применён.');
}
mode.onchange=async()=>{
 const previous=preferences.mode;await save(false);
 if(['mouse','system_mouse'].includes(previous)||['mouse','system_mouse'].includes(mode.value)){
  try{await desktopMode(mode.value);}catch(error){status.textContent=error.message;}
  const arm=await chrome.storage.session.get(['armedAt']);
  if(arm.armedAt&&(previous==='system_mouse'||mode.value==='system_mouse'))await armButton.onclick();
 }
};span.oninput=showRange;span.onchange=()=>save(true);
unfocused.onchange=async()=>{
 await ready;
 const arm=await chrome.storage.session.get(['armedTab']);
 if(arm.armedTab!==undefined)await chrome.storage.session.set({allowUnfocused:unfocused.checked});
};
async function cameraControl(enabled){
 try{
  const response=await fetch('http://127.0.0.1:8767/camera/'+(enabled?'on':'off'),{method:'POST',headers:{'X-Jarvis-Extension':chrome.runtime.id},signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('Не удалось связаться с камерой.');
  const result=await response.json();if(!result.ok)throw Error(result.error||'Камера не запустилась.');
  lastCameraError=false;
 }catch(error){lastCameraError=true;throw Error(error.message+' Проверьте, что AirControl запущен.');}
}
document.getElementById('arm').onclick=async()=>{
 if(pendingControl)return;controlBusy(true);
 try{
  await ready;status.textContent='Включаю камеру…';
  if(mode.value==='system_mouse'){
   await chrome.storage.session.remove(['armedWindow','armedTab','armedDocumentId','armedOrigin']);
   await cameraControl(true);await desktopMode('system_mouse');
   await chrome.storage.session.set({armedScope:'system',armedAt:Date.now()/1000});
   status.textContent='Готово. Мышь рукой включена для всего Mac.';await refreshCurrent();return;
  }
  const pendingTab=chrome.tabs.query({active:true,currentWindow:true});
  const granted=await chrome.permissions.request({origins:['http://*/*','https://*/*']});
  const [tab]=await pendingTab;
  if(!/^https?:/.test(tab.url||''))throw Error('Откройте обычную веб-страницу.');
  if(!granted)throw Error('Для переходов между сайтами нужен доступ к веб-страницам. Управление пока не включено.');
  const registration=await chrome.runtime.sendMessage({type:'register'});
  if(!registration?.ok)throw Error('Не удалось включить управление после переходов.');
  const results=await chrome.scripting.executeScript({target:{tabId:tab.id},files:['pointer.js','content.js']});
  const main=results.find(result=>result.frameId===0);
  if(!main?.documentId)throw Error('Не удалось выбрать страницу. Обновите Chrome и попробуйте снова.');
  await cameraControl(true);
  if(['mouse','system_mouse'].includes(mode.value))await desktopMode(mode.value);
  await chrome.storage.session.set({armedScope:scope.value,armedWindow:tab.windowId,armedTab:tab.id,armedAt:Date.now()/1000,armedDocumentId:main.documentId,armedOrigin:new URL(tab.url).origin,allowUnfocused:unfocused.checked});
  status.textContent='Готово. Камера включена. Управление: '+({tab:'эта вкладка',window:'это окно',browser:'весь браузер'}[scope.value])+'.';
  await refreshCurrent();
 }catch(e){status.textContent=e.message;}
 finally{controlBusy(false);await refreshControls();}
};
document.getElementById('stop').onclick=async()=>{
 if(pendingControl)return;controlBusy(true);
 try{
 await chrome.storage.session.remove(['armedWindow','armedTab','armedAt','armedDocumentId','armedOrigin','allowUnfocused','armedScope']);
 try{await cameraControl(false);status.textContent='Управление и камера выключены.';}
 catch(error){status.textContent='Управление отключено. '+error.message;}
 await refreshCurrent();
 }finally{controlBusy(false);await refreshControls();}
};
// The popup is short lived; keep its current-page indicator in sync while open.
setInterval(refreshCurrent,600);
