/* Phase 3E · Canonical admin system/storage runtime. */
(function(){
  'use strict';

  window.renderStorageStatus = async function(force=false){
    const box = document.getElementById('admin-storage-status');
    if (!box) return;
    box.textContent = '讀取檔案儲存狀態中…';
    try {
      const res = await fetch(`/api/storage-status${force?'?refresh=1':''}`, {});
      const d = await res.json().catch(()=>({}));
      if (!res.ok) throw new Error(d.error || '無法讀取儲存狀態');
      const active = d.activeBackend === 'mega' ? '🟣 MEGA 教材庫' : (d.activeBackend === 'oci' ? '🔴 Oracle（舊）' : (d.activeBackend === 'gdrive' ? '🟢 Google Drive（舊）' : (d.activeBackend === 'r2' ? '☁️ Cloudflare R2（舊）' : (d.activeBackend === 'local' ? '💾 本機儲存' : '❌ 設定錯誤'))));
      const counts = d.materials || {};
      let cloudState='';
      if(d.megaConfigured){
        const sp=d.megaSpace||{};
        const used=sp.usedGb==null?'?':sp.usedGb;
        const total=sp.totalGb==null?'?':sp.totalGb;
        cloudState = `　<span class="text-fuchsia-700">✅ MEGA 已連線・帳號 ${used}/${total} GB・網站硬上限 ${d.megaFreeLimitGb||18} GB${d.megaFreeOnly?'・免費模式':''}</span>`;
      } else if(d.activeBackend==='oci') cloudState='　<span class="text-red-700">Oracle 舊後端仍可讀取</span>';
      else if(d.activeBackend==='gdrive') cloudState=d.gdriveConnected?'　<span class="text-emerald-700">Google Drive 舊後端已連線</span>':'　<span class="text-rose-600">Google Drive 舊後端失效</span>';
      else if(d.activeBackend==='r2') cloudState='　<span class="text-cyan-700">R2 舊後端已啟用</span>';
      else cloudState='　<span class="text-amber-700">⚠️ 請在 Render 設定 MEGA_EMAIL / MEGA_PASSWORD</span>';
      const fallbackState=d.failoverOnFull?(d.fallbackReady?`<div class="text-emerald-700 mt-1">↪ 容量滿載備援：${escapeHtml(d.fallbackBackend||'')} 已就緒</div>`:`<div class="text-amber-700 mt-1">↪ 已要求容量滿載備援，但備援尚未完成設定</div>`):'';
      box.innerHTML = `<b>目前教材儲存：</b>${active}　<span class="text-slate-400">｜</span> MEGA ${counts.mega||0} 份、Oracle ${counts.oci||0} 份、Google Drive ${counts.gdrive||0} 份、R2 ${counts.r2||0} 份、本機 ${counts.local||0} 份` + cloudState + fallbackState +
        (d.error ? `<div class="text-rose-600 mt-1">${escapeHtml(d.error)}</div>` : '');
    } catch (err) {
      box.innerHTML = `<span class="text-rose-600">❌ ${escapeHtml(err.message)}</span>`;
    }
  };


  window.migrateMaterialsToGoogleDrive = async function(){
    if (!confirm('要將目前尚未存於 Google Drive 的教材搬移到 Google Drive 嗎？\n\n可搬移仍存在 Render 本機的教材；若教材目前在 R2 且 R2 金鑰仍有效，也會先讀出再搬到 Google Drive。搬移成功後舊雲端/本機副本會移除，資料庫與課程/成績資料不會刪除。')) return;
    const btn = document.getElementById('migrate-gdrive-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移到 Google Drive 中…'; }
    try {
      const res = await fetch('/api/storage/migrate-to-gdrive', {method:'POST', });
      const d = await res.json().catch(()=>({}));
      if (!res.ok) throw new Error(d.error || '搬移失敗');
      const skipped = Array.isArray(d.skipped) ? d.skipped.length : 0;
      const failed = Array.isArray(d.failed) ? d.failed.length : 0;
      let msg = `Google Drive 搬移完成：成功 ${d.migrated||0} 份、略過 ${skipped} 份、失敗 ${failed} 份。`;
      if (skipped) msg += '\n略過通常表示 Render 本機舊檔已不存在。';
      if (failed && d.failed?.[0]?.reason) msg += `\n第一筆錯誤：${d.failed[0].reason}`;
      alert(msg);
      await window.renderStorageStatus(true);
      invalidateAdminMaterialsCache();
      await renderAdminMaterials(true);
      await renderAdminCourseMaterialHub(true);
      await renderSlidesGrid();
    } catch (err) {
      alert(`❌ ${err.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🟢 搬移既有教材到 Google Drive'; }
    }
  };

  window.migrateLocalMaterialsToR2 = async function(){
    if (!confirm('要將目前仍存於本機、而且伺服器上仍存在原始檔的教材搬移到 Cloudflare R2 嗎？\n\n搬移成功後，本機教材檔會刪除；資料庫與課程/成績資料不會刪除。')) return;
    const btn = document.getElementById('migrate-r2-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移中…'; }
    try {
      const res = await fetch('/api/storage/migrate-to-r2', {method:'POST', });
      const d = await res.json().catch(()=>({}));
      if (!res.ok) throw new Error(d.error || '搬移失敗');
      const skipped = Array.isArray(d.skipped) ? d.skipped.length : 0;
      const failed = Array.isArray(d.failed) ? d.failed.length : 0;
      alert(`R2 搬移完成：成功 ${d.migrated||0} 份、略過 ${skipped} 份、失敗 ${failed} 份。` + (skipped ? '\n略過通常表示 Render 本機檔案已不存在。' : ''));
      await window.renderStorageStatus(true);
      invalidateAdminMaterialsCache();
      await renderAdminMaterials(true);
      await renderAdminCourseMaterialHub(true);
      await renderSlidesGrid();
    } catch (err) {
      alert(`❌ ${err.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '☁️ 搬移本機教材到 R2（備援）'; }
    }
  };

  // Final convergence: canonical owner migrated from system-admin.js.
  function systemStatusCard(icon,title,state,detail,tone='slate'){const classes={emerald:'is-good',amber:'is-warning',rose:'is-error',slate:'is-neutral'};return `<div class="admin-system-status-card ${classes[tone]||classes.slate}"><div class="admin-system-status-icon">${icon}</div><div class="min-w-0"><div class="text-xs font-black text-slate-600">${escapeHtml(title)}</div><div class="text-base font-black text-slate-950 mt-1">${escapeHtml(state)}</div><div class="text-[11px] text-slate-500 mt-1 break-all">${escapeHtml(detail||'')}</div></div></div>`;}

  async function renderAdminSystemStatus(force=false){
    const cards=document.getElementById('admin-system-health'),storage=document.getElementById('admin-system-storage');
    if(!cards||!storage)return;
    cards.innerHTML='<div class="col-span-full text-xs text-slate-400">檢查服務中…</div>';
    storage.textContent='讀取儲存狀態中…';
    try{
      const [hr,sr,ar]=await Promise.all([
        fetch('/health',{credentials:'same-origin',cache:'no-store'}),
        fetch(`/api/storage-status${force?'?refresh=1':''}`,{credentials:'same-origin',cache:'no-store'}),
        fetch('/api/ai-questions/status',{credentials:'same-origin',cache:'no-store'})
      ]);
      const h=await hr.json().catch(()=>({})),s=await sr.json().catch(()=>({})),a=await ar.json().catch(()=>({}));
      if(!hr.ok)throw new Error(h.error||`核心健康檢查失敗（HTTP ${hr.status}）`);
      const dbOk=Boolean(h.database?.ok ?? h.ok);
      const diagnosticsOk=Boolean(h.configuration?.ok && h.migrations?.ok);
      const deploy=h.deployment||{};
      const deploymentDetail=[
        deploy.provider||'',
        deploy.branch||'',
        deploy.commit||''
      ].filter(Boolean).join(' · ') || `版本 ${h.version||'未知'}`;
      const storageOk=sr.ok;
      const aiOk=ar.ok;
      cards.innerHTML=
        systemStatusCard('🖥️','Render / Web',h.ok?'正常':'異常',deploymentDetail,h.ok?'emerald':'rose')+
        systemStatusCard('🩺','系統診斷',diagnosticsOk?'正常':'待確認',
          diagnosticsOk
            ? `設定與資料庫 migration 均正常 · v${h.version||'—'}`
            : `設定：${h.configuration?.ok?'正常':'待確認'} · migrations：${h.migrations?.ok?'正常':'待確認'}`,
          diagnosticsOk?'emerald':'amber')+
        systemStatusCard('🗄️','Supabase / Database',dbOk?'可連線':'待確認',
          dbOk?`${h.database?.kind||'database'} · required migrations ${(h.migrations?.required||[]).length}`:'資料庫健康檢查未通過',
          dbOk?'emerald':'amber')+
        systemStatusCard('🟣','MEGA',
          storageOk?(s.megaConfigured?(s.megaError?'已設定但檢查失敗':'已設定'):'未設定'):`HTTP ${sr.status}`,
          storageOk?(s.megaSpace?`${s.megaSpace.usedGb??'?'} / ${s.megaSpace.totalGb??'?'} GB；網站上限 ${s.megaFreeLimitGb||18} GB`:(s.megaError||'')):(s.error||'儲存狀態端點不可用'),
          storageOk&&s.megaConfigured&&!s.megaError?'emerald':(storageOk&&s.megaConfigured?'amber':'rose'))+
        systemStatusCard('🤖','Groq AI',
          aiOk?(a.configured?'已設定':'未設定'):`HTTP ${ar.status}`,
          aiOk?`${a.provider||''} ${a.model||''}`:(a.error||'AI 狀態端點不可用'),
          aiOk&&a.configured?'emerald':'amber');
      if(!storageOk){
        storage.innerHTML=`<div class="font-black text-rose-700">教材儲存狀態讀取失敗</div><div class="mt-2 text-xs text-slate-500">HTTP ${sr.status} · ${escapeHtml(s.error||'請重新檢查')}</div>`;
        return;
      }
      const g=s.gdriveConfigured?(s.gdriveConnected?'✅ Google Drive 備援已連線':((s.activeBackend||s.configuredMode)==='gdrive'?'⚠️ Google Drive 目前使用中，但連線尚未驗證':'ℹ️ Google Drive 備援已設定，尚未執行連線測試（不影響目前主要儲存）')):'○ Google Drive 備援未設定';
      storage.innerHTML=`<div class="font-black text-slate-900">教材儲存策略</div><div class="mt-2">主要：<b>${escapeHtml(s.activeBackend||s.configuredMode||'')}</b>　｜　備援：<b>${escapeHtml(s.fallbackBackend||'')}</b>　｜　免費模式：<b>${s.megaFreeOnly?'是':'否'}</b></div><div class="mt-2">${g}</div><div class="mt-2 text-xs text-slate-500">MEGA ${s.materials?.mega||0} 份、Google Drive ${s.materials?.gdrive||0} 份、R2 ${s.materials?.r2||0} 份、本機 ${s.materials?.local||0} 份</div>${s.error?`<div class="mt-2 text-rose-600">${escapeHtml(s.error)}</div>`:''}`;
    }catch(e){
      cards.innerHTML=systemStatusCard('⚠️','系統狀態','檢查失敗',e.message,'rose');
      storage.textContent='無法讀取儲存狀態';
    }
  }

  window.systemStatusCard=systemStatusCard;
  window.renderAdminSystemStatus=renderAdminSystemStatus;
})();
