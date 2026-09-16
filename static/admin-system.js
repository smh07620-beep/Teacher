/* Phase 3E · Admin system/storage runtime.
 * Loaded after the legacy admin bundle so these functions become the
 * canonical runtime implementation while system-admin.js remains a
 * compatibility fallback during the incremental split.
 */
(function(){
  'use strict';

  window.renderStorageStatus = async function(force=false){
    const box = document.getElementById('admin-storage-status');
    if (!box) return;
    const key = await getAdminKey();
    if (!key) return;
    box.textContent = '讀取檔案儲存狀態中…';
    try {
      const res = await fetch(`/api/storage-status${force?'?refresh=1':''}`, {headers:{'X-Admin-Key':key}});
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

  window.migrateMaterialsToMega = async function(){
    if (!confirm('要將目前仍可讀取的既有教材搬移到 MEGA 嗎？\n\n新檔成功存入 MEGA 後才會更新資料庫；免費模式會在接近網站設定容量上限時停止上傳。')) return;
    const key=await getAdminKey();
    if(!key) return;
    const btn=document.getElementById('migrate-mega-btn');
    try {
      if(btn){btn.disabled=true;btn.textContent='⏳ 搬移到 MEGA 中…';}
      const res=await fetch('/api/storage/migrate-to-mega',{method:'POST',headers:{'X-Admin-Key':key}});
      const d=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(d.error||'搬移失敗');
      alert(`MEGA 搬移完成：成功 ${d.migrated||0} 份、略過 ${(d.skipped||[]).length} 份、失敗 ${(d.failed||[]).length} 份。`);
      await window.renderStorageStatus(true);
      invalidateAdminMaterialsCache();
      await renderAdminMaterials(true);
      await renderAdminCourseMaterialHub(true);
      await renderSlidesGrid();
    } catch(e){
      alert('搬移失敗：'+e.message);
    } finally {
      if(btn){btn.disabled=false;btn.textContent='☁️ 搬移既有教材到 MEGA';}
    }
  };

  window.migrateMaterialsToGoogleDrive = async function(){
    if (!confirm('要將目前尚未存於 Google Drive 的教材搬移到 Google Drive 嗎？\n\n可搬移仍存在 Render 本機的教材；若教材目前在 R2 且 R2 金鑰仍有效，也會先讀出再搬到 Google Drive。搬移成功後舊雲端/本機副本會移除，資料庫與課程/成績資料不會刪除。')) return;
    const key = await getAdminKey();
    if (!key) return;
    const btn = document.getElementById('migrate-gdrive-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移到 Google Drive 中…'; }
    try {
      const res = await fetch('/api/storage/migrate-to-gdrive', {method:'POST', headers:{'X-Admin-Key':key}});
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
    const key = await getAdminKey();
    if (!key) return;
    const btn = document.getElementById('migrate-r2-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移中…'; }
    try {
      const res = await fetch('/api/storage/migrate-to-r2', {method:'POST', headers:{'X-Admin-Key':key}});
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
})();
