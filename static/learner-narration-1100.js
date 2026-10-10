/* 學員端：教材附有配音時，開啟教材即自動播放；可用喇叭鈕關閉（記住偏好）。
 *
 * 老師自己錄的旁白（narration.kind === 'teacher'）另外會：
 *  - 依翻頁時間表自動帶學員翻頁（學員自己翻頁就暫停跟隨，可按鈕回到跟隨模式）
 *  - 載入「教師核准後」的字幕並顯示在投影片上（可開關）
 * AI 語音若是「逐張投影片分段合成」（narration.kind === 'ai' 且有 segments）：
 *  - 學員打開／翻到第 k 張才播第 k 段，講完就停住，不會自動翻頁，也不會接著講下一張
 *  - 翻到別張就從那張的段落開頭播；翻回來可重聽；按鈕可「重聽本頁」
 *  - 教材改版後（stale）或沒有分段資料時，維持原本整段播放
 * 老師正在錄製新旁白時（window.__teacherNarrationRecording）不播放，避免舊旁白被錄進去。
 */
(function(){
  'use strict';
  var KEY='teacher.narration.muted', CC_KEY='teacher.narration.captions';
  var bar=null, audio=null, timer=0, syncTimer=0, capEl=null, cues=[], following=true, autoPage=-1, current=null, sourceId='';
  var segMode=false, segTimer=0, segPage=-1, stopAt=-1, segDone=false;
  var heard=null, heardDirty=false, flushTimer=0, heardBtnEl=null;
  function readFlag(key, fallback){ try{ var v=localStorage.getItem(key); return v===null?fallback:v==='1'; }catch(e){ return fallback; } }
  function writeFlag(key, v){ try{ localStorage.setItem(key, v?'1':'0'); }catch(e){} }
  function getMuted(){ return readFlag(KEY,false); }
  function setMuted(v){ writeFlag(KEY,v); }
  function captionsOn(){ return readFlag(CC_KEY,true); }
  function viewerOpen(){
    return ['slide-viewer-modal','media-viewer-modal'].some(function(id){
      var el=document.getElementById(id); return el && !el.classList.contains('hidden');
    });
  }
  // ---- AI 語音逐張分段（純函式，方便測試） ----
  function isSegmented(n){ return !!n && n.kind==='ai' && !n.stale && Array.isArray(n.segments) && n.segments.length>0; }
  function segmentForPage(segments, page){
    var list=Array.isArray(segments)?segments:[];
    for(var i=0;i<list.length;i++){ if(Number(list[i].page)===page) return list[i]; }
    return null;
  }
  function reachedEnd(currentSeconds, endMs){ return currentSeconds*1000 >= Number(endMs)-30; }
  function stop(){
    flushHeard(true);
    if(flushTimer){ clearInterval(flushTimer); flushTimer=0; }
    heard=null; heardDirty=false; heardBtnEl=null;
    if(segTimer){ clearInterval(segTimer); segTimer=0; }
    segMode=false; segPage=-1; stopAt=-1; segDone=false;
    if(timer){ clearInterval(timer); timer=0; }
    if(syncTimer){ clearInterval(syncTimer); syncTimer=0; }
    if(audio){ try{ audio.pause(); }catch(e){} audio.removeAttribute('src'); }
    if(bar){ bar.remove(); bar=null; }
    if(capEl){ capEl.remove(); capEl=null; }
    audio=null; cues=[]; current=null; sourceId=''; following=true; autoPage=-1;
  }
  function paint(btn){
    var on=!!audio && !audio.paused && !audio.muted;
    var idle=(segMode && segDone)?'🔁 重聽本頁':'🔈 點此播放配音';
    btn.textContent=getMuted()?'🔇 配音已關':(on?'🔊 配音播放中':idle);
    btn.setAttribute('aria-pressed', getMuted()?'true':'false');
  }

  // ---- 翻頁時間表（老師旁白） ----
  function timeline(){ return (current && current.kind==='teacher' && !current.stale && Array.isArray(current.timeline)) ? current.timeline : []; }
  function pageAt(ms){
    var list=timeline(), page=-1;
    for(var i=0;i<list.length;i++){ if(Number(list[i].startMs)<=ms) page=Number(list[i].page); else break; }
    return page;
  }
  function viewerIndex(){
    var s=window.slideViewerState;
    return (s && String(s.materialId||'')===String(sourceId) && Number.isInteger(Number(s.index))) ? Number(s.index) : -1;
  }
  function syncPages(){
    if(!audio || !timeline().length || window.__teacherNarrationRecording) return;
    var shown=viewerIndex();
    if(shown<0 || typeof window.goToSlidePage!=='function') return;
    if(following){
      // 學員在上一個 tick 之後自己換了頁 → 不再硬拉回來
      if(autoPage>=0 && shown!==autoPage){ seekToPage(shown); return; }
      var target=pageAt(Math.round(audio.currentTime*1000));
      if(target>=0 && target!==shown){ autoPage=target; window.goToSlidePage(target); }
      else autoPage=shown;
    }
  }
  var followBtn=null;
  function refreshFollowButton(){
    if(!followBtn) return;
    followBtn.style.display=timeline().length?'':'none';
    followBtn.textContent=following?'📖 跟著旁白（點此改自行閱讀）':'⏯ 回到跟著旁白聽';
  }
  function pageStartMs(page){
    var list=timeline();
    for(var i=0;i<list.length;i++){ if(Number(list[i].page)===page) return Number(list[i].startMs); }
    return null;
  }
  // 學員自己翻頁 → 旁白跳到那一頁的起點繼續講，聲音永遠對得上畫面。
  function seekToPage(page){
    var startMs=pageStartMs(page);
    autoPage=page;
    if(startMs===null) return;               // 這一頁沒有旁白段落：不動
    audio.currentTime=startMs/1000;
    if(!getMuted()) audio.play().catch(function(){});
  }
  function listenFromHere(){
    following=true;
    seekToPage(viewerIndex());
    refreshFollowButton();
  }
  // 自行閱讀：旁白暫停，翻頁不再帶動；但有旁白的教材仍需聽完約 90% 才算完成。
  function readFreely(){
    following=false; autoPage=-1;
    try{ audio.pause(); }catch(e){}
    refreshFollowButton();
  }

  // ---- 已聽進度：以 10 秒為單位記錄，由伺服器判定是否達 90% ----
  function markHeard(){
    if(!audio || !heard || audio.paused || audio.muted || audio.seeking || window.__teacherNarrationRecording) return;
    var b=Math.floor(audio.currentTime/10);
    if(b>=0 && !heard[b]){ heard[b]=1; heardDirty=true; paintHeard(); }
  }
  function heardPercent(){
    if(!audio || !heard || !isFinite(audio.duration) || audio.duration<=0) return null;
    var covered=0;
    Object.keys(heard).forEach(function(k){ covered+=Math.min(10, Math.max(0, audio.duration-Number(k)*10)); });
    return Math.min(100, Math.round(covered/audio.duration*100));
  }
  function paintHeard(){
    if(!heardBtnEl) return;
    var pct=heardPercent();
    if(pct===null){ heardBtnEl.textContent=''; return; }
    heardBtnEl.textContent=pct>=90?'✅ 旁白已聽完':'🎧 旁白已聽 '+pct+'%（需 90%）';
  }
  function flushHeard(sync){
    if(!audio || !heard || !heardDirty || !current || !current.id) return;
    var duration=isFinite(audio.duration)?audio.duration:0;
    if(duration<=0) return;
    heardDirty=false;
    var body={duration:duration, lastPositionSeconds:Math.min(duration, audio.currentTime||0),
      watchedBuckets:Object.keys(heard).map(Number)};
    try{
      fetch('/api/learning-progress/'+encodeURIComponent(current.id),{
        method:'PUT', credentials:'same-origin', keepalive:!!sync,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
      }).then(function(r){ return r.ok?r.json():null; }).then(function(data){
        if(data && data.sourceCompleted) window.dispatchEvent(new CustomEvent('smartLearning67:progress',{detail:data}));
      }).catch(function(){ heardDirty=true; });
    }catch(e){ heardDirty=true; }
  }
  function loadHeard(){
    var token=current && current.id;
    heard={};
    fetch('/api/learning-progress/'+encodeURIComponent(token),{credentials:'same-origin',cache:'no-store'})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(data){
        if(!data || !current || current.id!==token || !heard) return;
        (data.watchedBuckets||[]).forEach(function(b){ heard[Number(b)]=1; });
        paintHeard();
      }).catch(function(){});
  }

  // ---- 字幕（只取教師核准版） ----
  function toSeconds(text){
    var m=/^(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})$/.exec(String(text||'').trim());
    if(!m) return NaN;
    return (Number(m[1]||0)*3600)+(Number(m[2])*60)+Number(m[3])+Number(('0.'+m[4]));
  }
  function parseVtt(text){
    var out=[], blocks=String(text||'').replace(/\r/g,'').split(/\n\s*\n/);
    blocks.forEach(function(block){
      var lines=block.split('\n').filter(function(l){ return l.trim()!==''; });
      for(var i=0;i<lines.length;i++){
        if(lines[i].indexOf('-->')<0) continue;
        var parts=lines[i].split('-->'), start=toSeconds(parts[0]), end=toSeconds(String(parts[1]||'').trim().split(/\s+/)[0]);
        var body=lines.slice(i+1).join('\n').replace(/<[^>]+>/g,'').trim();
        if(isFinite(start)&&isFinite(end)&&body) out.push({start:start,end:end,text:body});
        break;
      }
    });
    return out;
  }
  function ensureCaptionEl(){
    if(capEl) return capEl;
    capEl=document.createElement('div');
    capEl.setAttribute('data-narration-caption','1');
    capEl.setAttribute('aria-live','off');
    capEl.style.cssText='position:fixed;left:50%;bottom:76px;transform:translateX(-50%);z-index:2147482999;max-width:min(86vw,900px);'
      +'background:rgba(15,23,42,.82);color:#fff;border-radius:10px;padding:6px 14px;font-size:18px;line-height:1.5;'
      +'text-align:center;white-space:pre-line;pointer-events:none;display:none';
    document.body.appendChild(capEl);
    return capEl;
  }
  function paintCaption(){
    if(!audio || !cues.length || !captionsOn() || window.__teacherNarrationRecording){ if(capEl) capEl.style.display='none'; return; }
    var t=audio.currentTime, hit=null;
    for(var i=0;i<cues.length;i++){ if(t>=cues[i].start && t<cues[i].end){ hit=cues[i]; break; } }
    var el=ensureCaptionEl();
    if(hit){ el.textContent=hit.text; el.style.display='block'; } else { el.style.display='none'; }
  }
  function loadCaptions(narration){
    if(!narration || narration.kind!=='teacher' || !narration.id) return;
    var token=narration.id;
    fetch('/api/materials/'+encodeURIComponent(narration.id)+'/subtitles/approved',{credentials:'same-origin',cache:'no-store'})
      .then(function(r){ return r.ok?r.json():{}; })
      .then(function(data){
        var url=data && data.subtitle && data.subtitle.vttUrl;
        if(!url || !current || current.id!==token) return null;
        return fetch(url,{credentials:'same-origin'}).then(function(r){ return r.ok?r.text():''; });
      })
      .then(function(text){
        if(!text || !current || current.id!==token) return;
        cues=parseVtt(text);
        if(cues.length && bar) addCaptionButton();
      })
      .catch(function(){});
  }
  var ccBtn=null;
  function addCaptionButton(){
    if(!bar || ccBtn) return;
    ccBtn=document.createElement('button'); ccBtn.type='button';
    ccBtn.style.cssText='background:transparent;color:inherit;border:0;cursor:pointer;font-weight:700';
    function paintCc(){ ccBtn.textContent=captionsOn()?'💬 字幕開':'💬 字幕關'; }
    ccBtn.addEventListener('click', function(){ writeFlag(CC_KEY,!captionsOn()); paintCc(); paintCaption(); });
    paintCc(); bar.appendChild(ccBtn);
  }

  // ---- AI 語音：講完一張就停，翻到下一張才播下一段 ----
  function playPage(page, btn){
    var seg=segmentForPage(current && current.segments, page);
    segPage=page; segDone=false;
    if(!seg || !(Number(seg.endMs)>Number(seg.startMs))){ stopAt=-1; try{ audio.pause(); }catch(e){} paint(btn); return; }
    try{ audio.currentTime=Number(seg.startMs)/1000; }catch(e){}
    stopAt=Number(seg.endMs);
    if(!getMuted()) audio.play().catch(function(){ paint(btn); });
    paint(btn);
  }
  function replayCurrent(btn){
    var page=viewerIndex();
    if(page<0) page=segPage>=0?segPage:0;
    playPage(page, btn);
  }
  function startSegments(btn){
    segTimer=setInterval(function(){
      if(!audio || !current || window.__teacherNarrationRecording) return;
      var shown=viewerIndex();
      if(shown>=0 && shown!==segPage && audio.readyState>=1) playPage(shown, btn);
      if(stopAt>=0 && reachedEnd(audio.currentTime, stopAt)){
        stopAt=-1; segDone=true;
        try{ audio.pause(); }catch(e){}
        paint(btn);
      }
    }, 100);
  }

  function start(narration, materialId){
    stop();
    if(!narration || !narration.viewUrl) return;
    if(window.__teacherNarrationRecording) return;
    current=narration; sourceId=materialId||''; following=true; autoPage=-1; ccBtn=null; followBtn=null;
    audio=new Audio(narration.viewUrl); audio.preload='auto'; audio.muted=getMuted();
    bar=document.createElement('div');
    bar.setAttribute('data-narration-bar','1');
    bar.style.cssText='position:fixed;right:16px;bottom:16px;z-index:2147483000;display:flex;gap:6px;align-items:center;background:#1e1b4b;color:#fff;border-radius:999px;padding:6px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.3)';
    var btn=document.createElement('button'); btn.type='button';
    btn.style.cssText='background:transparent;color:inherit;border:0;cursor:pointer;font-weight:700';
    btn.addEventListener('click', function(){
      if(segMode){
        if(getMuted()){ setMuted(false); audio.muted=false; replayCurrent(btn); }
        else if(audio.paused){ replayCurrent(btn); }
        else { setMuted(true); audio.muted=true; try{ audio.pause(); }catch(e){} }
        paint(btn); return;
      }
      if(getMuted()){ setMuted(false); audio.muted=false; audio.play().catch(function(){}); }
      else if(audio.paused){ audio.play().catch(function(){}); }
      else { setMuted(true); audio.muted=true; }
      paint(btn);
    });
    audio.addEventListener('play', function(){ paint(btn); });
    audio.addEventListener('pause', function(){ paint(btn); });
    audio.addEventListener('ended', function(){ paint(btn); flushHeard(false); });
    audio.addEventListener('pause', function(){ flushHeard(false); });
    audio.addEventListener('timeupdate', markHeard);
    audio.addEventListener('loadedmetadata', paintHeard);
    bar.appendChild(btn);
    heardBtnEl=document.createElement('span');
    heardBtnEl.setAttribute('data-narration-heard','1');
    heardBtnEl.style.cssText='font-weight:700;opacity:.9';
    bar.appendChild(heardBtnEl);
    loadHeard();
    flushTimer=setInterval(function(){ flushHeard(false); }, 15000);
    if(narration.kind==='teacher' && !narration.stale && Array.isArray(narration.timeline) && narration.timeline.length){
      followBtn=document.createElement('button'); followBtn.type='button';
      followBtn.style.cssText='background:transparent;color:inherit;border:0;cursor:pointer;font-weight:700';
      followBtn.addEventListener('click', function(){
        if(following){ readFreely(); } else { listenFromHere(); }
      });
      bar.appendChild(followBtn); refreshFollowButton();
    }
    document.body.appendChild(bar); paint(btn);
    segMode=isSegmented(narration);
    if(segMode){ startSegments(btn); paint(btn); }
    else audio.play().catch(function(){ paint(btn); });
    // 檢視視窗關閉後自動停止並移除控制列
    timer=setInterval(function(){ if(!viewerOpen()) stop(); }, 800);
    setTimeout(function(){ if(bar && !viewerOpen()) stop(); }, 4000);
    if(narration.kind==='teacher'){
      syncTimer=setInterval(function(){ syncPages(); paintCaption(); }, 250);
      loadCaptions(narration);
    }
  }
  function wrap(){
    var original=window.openMaterial;
    if(typeof original!=='function' || original.__narrationWrapped) return;
    var wrapped=function(id){
      var result=original.apply(this, arguments);
      try{
        var list=window.cachedSlidesList||[];
        var m=list.find(function(x){ return x && x.id===id; });
        if(m && m.narration) start(m.narration, id); else stop();
      }catch(e){}
      return result;
    };
    wrapped.__narrationWrapped=true;
    window.openMaterial=wrapped;
  }
  window.LearnerNarration1100={stop:stop, parseVtt:parseVtt, isSegmented:isSegmented, segmentForPage:segmentForPage, reachedEnd:reachedEnd};
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', wrap); else wrap();
  window.addEventListener('load', wrap);
})();
