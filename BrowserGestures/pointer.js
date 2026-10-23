/* A page-local pointer. It never sends mouse input to another application. */
(()=>{
 class BrowserAirMouse{
  constructor(){this.dot=null;this.down=null;this.last=0;this.sequence=0;this.x=0;this.y=0;this.pauseUntil=0;this.clickAt=0;this.clickTarget=null;}
  marker(){
   if(this.dot?.isConnected)return;
   this.dot=document.createElement('div');this.dot.setAttribute('aria-hidden','true');
   this.dot.style.cssText='position:fixed;width:18px;height:18px;border:2px solid #7deaf4;border-radius:50%;background:#5bd3e533;box-shadow:0 0 0 4px #071c2455;pointer-events:none;z-index:2147483647;transform:translate(-50%,-50%);display:none;transition:left 25ms linear,top 25ms linear';
   document.documentElement.appendChild(this.dot);
  }
  mouse(target,type,buttons=0,button=0){target?.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:this.x,clientY:this.y,buttons,button}));}
  cancel(){if(this.down)this.mouse(this.down,'mouseup');this.down=null;if(this.dot)this.dot.style.display='none';this.last=0;}
  pause(){this.cancel();this.pauseUntil=Date.now()+1200;}
  destroy(){this.cancel();this.dot?.remove();this.dot=null;}
  tick(){if(this.last&&Date.now()-this.last>350)this.cancel();}
  range(target){
   if(target?.tagName!=='INPUT'||target.type!=='range')return false;
   const r=target.getBoundingClientRect(),min=Number(target.min||0),max=Number(target.max||100),step=Number(target.step)||1;
   const value=min+Math.round(Math.max(0,Math.min(1,(this.x-r.left)/Math.max(1,r.width)))*(max-min)/step)*step;
   const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;
   if(setter)setter.call(target,String(Math.max(min,Math.min(max,value))));else target.value=String(value);
   target.dispatchEvent(new Event('input',{bubbles:true}));return true;
  }
  handle(e,allowUnfocused){
   if(!Number.isInteger(e.id)||e.id<=this.sequence)return;this.sequence=e.id;
   if(e.phase==='cancel'){this.cancel();if(e.reason==='fist'&&this.dot){this.dot.style.display='block';this.dot.style.background='#71878a';}return;}
   if(document.hidden||(!document.hasFocus()&&!allowUnfocused)||Date.now()<this.pauseUntil){this.cancel();return;}
   if(!Number.isFinite(e.x)||!Number.isFinite(e.y)||e.x<0||e.x>1||e.y<0||e.y>1)return;
   this.x=e.x*Math.max(1,innerWidth-1);this.y=e.y*Math.max(1,innerHeight-1);this.last=Date.now();this.marker();
   this.dot.style.left=this.x+'px';this.dot.style.top=this.y+'px';this.dot.style.display='block';
   const target=document.elementFromPoint(this.x,this.y);if(!target){this.cancel();return;}
   if(e.phase==='move'){
    if(!this.range(this.down))this.mouse(this.down||target,'mousemove',this.down?1:0);
    this.dot.style.background=this.down?'#7deaf4':'#5bd3e533';
   }else if(e.phase==='click'){
    target.closest?.('input,textarea,select,button,a[href],[tabindex],[contenteditable="true"]')?.focus?.({preventScroll:true});
    this.mouse(target,'mousedown',1);this.mouse(target,'mouseup');
    if(!this.range(target))target.click?.();
    else target.dispatchEvent(new Event('change',{bubbles:true}));
    if(this.clickTarget===target&&Date.now()-this.clickAt<450){this.mouse(target,'dblclick');this.clickAt=0;}
    else{this.clickAt=Date.now();this.clickTarget=target;}
   }else if(e.phase==='down'){this.down=target;this.mouse(target,'mousedown',1);this.range(target);}
   else if(e.phase==='up'){
    const down=this.down;this.mouse(down||target,'mouseup');
    if(this.range(down))down.dispatchEvent(new Event('change',{bubbles:true}));this.down=null;
   }else if(e.phase==='context')this.mouse(target,'contextmenu',0,2);
   else if(e.phase==='scroll'&&Number.isFinite(e.dy)&&Math.abs(e.dy)<=1){
    let el=target;
    while(el&&el!==document.body&&!(el.scrollHeight>el.clientHeight+30&&/(auto|scroll)/.test(getComputedStyle(el).overflowY)))el=el.parentElement;
    (el&&el!==document.body?el:window).scrollBy({top:e.dy*innerHeight,behavior:'instant'});
   }
  }
 }
 window.__AirControlBrowserAirMouse=BrowserAirMouse;
})();
