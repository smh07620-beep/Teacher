/* 學員端：教材附有 AI 配音時，開啟教材即自動播放；可用喇叭鈕關閉（記住偏好）。 */
(function(){
  'use strict';
  var KEY='teacher.narration.muted', bar=null, audio=null, timer=0;
  function getMuted(){ try{ return localStorage.getItem(KEY)==='1'; }catch(e){ return false; } }
  function setMuted(v){ try{ localStorage.setItem(KEY, v?'1':'0'); }catch(e){} }
  function viewerOpen(){
    return ['slide-viewer-modal','media-viewer-modal'].some(function(id){
      var el=document.getElementById(id); return el && !el.classList.contains('hidden');
    });
  }
  function stop(){
    if(timer){ clearInterval(timer); timer=0; }
    if(audio){ try{ audio.pause(); }catch(e){} audio.removeAttribute('src'); }
    if(bar){ bar.remove(); bar=null; }
    audio=null;
  }
  function paint(btn){
    var on=!!audio && !audio.paused && !audio.muted;
    btn.textContent=getMuted()?'🔇 配音已關':(on?'🔊 配音播放中':'🔈 點此播放配音');
    btn.setAttribute('aria-pressed', getMuted()?'true':'false');
  }
  function start(narration){
    stop();
    if(!narration || !narration.viewUrl) return;
    audio=new Audio(narration.viewUrl); audio.preload='auto'; audio.muted=getMuted();
    bar=document.createElement('div');
    bar.setAttribute('data-narration-bar','1');
    bar.style.cssText='position:fixed;right:16px;bottom:16px;z-index:2147483000;display:flex;gap:6px;align-items:center;background:#1e1b4b;color:#fff;border-radius:999px;padding:6px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.3)';
    var btn=document.createElement('button'); btn.type='button';
    btn.style.cssText='background:transparent;color:inherit;border:0;cursor:pointer;font-weight:700';
    btn.addEventListener('click', function(){
      if(getMuted()){ setMuted(false); audio.muted=false; audio.play().catch(function(){}); }
      else if(audio.paused){ audio.play().catch(function(){}); }
      else { setMuted(true); audio.muted=true; }
      paint(btn);
    });
    audio.addEventListener('play', function(){ paint(btn); });
    audio.addEventListener('pause', function(){ paint(btn); });
    audio.addEventListener('ended', function(){ paint(btn); });
    bar.appendChild(btn); document.body.appendChild(bar); paint(btn);
    audio.play().catch(function(){ paint(btn); });
    // 檢視視窗關閉後自動停止並移除控制列
    timer=setInterval(function(){ if(!viewerOpen()) stop(); }, 800);
    setTimeout(function(){ if(bar && !viewerOpen()) stop(); }, 4000);
  }
  function wrap(){
    var original=window.openMaterial;
    if(typeof original!=='function' || original.__narrationWrapped) return;
    var wrapped=function(id){
      var result=original.apply(this, arguments);
      try{
        var list=window.cachedSlidesList||[];
        var m=list.find(function(x){ return x && x.id===id; });
        if(m && m.narration) start(m.narration); else stop();
      }catch(e){}
      return result;
    };
    wrapped.__narrationWrapped=true;
    window.openMaterial=wrapped;
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', wrap); else wrap();
  window.addEventListener('load', wrap);
})();
