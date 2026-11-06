/* 2026-11-06 · 成績紀錄：依人員一鍵匯出 Word ＋ 產生 QP15-L03 人員能力評估考核紀錄表。
 * 兩個按鈕都依照畫面上的篩選（考卷、通過成績／每次作答、結果、搜尋），包含所有分頁。
 */
(function(){
  'use strict';

  const L03_TEMPLATE_URL = '/templates/QP15-L03.docx';
  const SETTINGS_KEY = 'teacher.qp15l03.settings.v1';
  const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  const safeName = v => String(v || '').replace(/[\\/:*?"<>|]/g, '_').trim().slice(0, 60) || '未命名';
  const esc = v => (window.escapeHtml ? window.escapeHtml(v) : String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));

  function taipeiDate(raw){
    const text = (window.formatTaipeiTime ? window.formatTaipeiTime(raw) : String(raw || '')).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : '';
  }
  const dotted = iso => iso ? iso.replace(/-/g, '.') : '';
  function plusOneYear(iso){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return '';
    const [y, m, d] = iso.split('-').map(Number);
    const day = (m === 2 && d === 29) ? 28 : d;
    return `${y + 1}.${String(m).padStart(2, '0')}.${String(day).padStart(2, '0')}`;
  }
  const groupName = label => String(label || '').replace(/^\s*\d+\s*/, '').trim();
  const rocYear = () => new Date().getFullYear() - 1911;

  function loadSettings(){ try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {}; } catch (_) { return {}; } }
  function saveSettings(v){ try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(v)); } catch (_) {} }

  async function visibleRecords(){
    if(typeof window.adminResultsVisibleRecords !== 'function') throw new Error('成績清單尚未載入，請重新整理頁面。');
    const rows = await window.adminResultsVisibleRecords();
    return (rows || []).filter(r => r && r.reviewStatus !== 'pending');
  }

  /* ---------- 1. 依人員一鍵匯出 Word ---------- */
  const templateCache = new Map();
  function pickLocalTemplate(){
    return new Promise(resolve => {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = '.docx';
      input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if(!file) return resolve(null);
        file.arrayBuffer().then(resolve, () => resolve(null));
      });
      input.click();
    });
  }
  async function templateFor(groupKey){
    if(templateCache.has(groupKey)) return templateCache.get(groupKey);
    let buffer = null;
    try {
      const res = await fetch(`/api/doc-templates/${encodeURIComponent(groupKey)}/download`, {credentials:'same-origin'});
      if(res.ok) buffer = await res.arrayBuffer();
    } catch (_) {}
    if(!buffer){
      const label = (window.GROUPS && window.GROUPS[groupKey]?.label) || groupKey;
      alert(`「${label}」尚未在後台設定 Word 範本。\n請在接下來的視窗選擇本機的「附件1.docx」。`);
      buffer = await pickLocalTemplate();
    }
    templateCache.set(groupKey, buffer);
    return buffer;
  }
  function renderDocx(buffer, payload){
    const doc = new window.docxtemplater(new PizZip(buffer), {paragraphLoop:true, linebreaks:true});
    doc.render(payload);
    return doc.getZip().generate({type:'uint8array'});
  }

  window.exportWordByPerson = async function(button){
    const label = button ? button.textContent : '';
    try {
      if(button){ button.disabled = true; button.textContent = '⏳ 匯出中…'; }
      const rows = await visibleRecords();
      if(!rows.length){ alert('目前篩選條件下沒有可匯出的考卷。'); return; }
      const people = new Map();
      for(const r of rows){
        const key = `${r.empId || ''}|${r.name || ''}`;
        if(!people.has(key)) people.set(key, []);
        people.get(key).push(r);
      }
      const zip = new PizZip();
      let count = 0;
      for(const list of people.values()){
        const folder = `${safeName(list[0].name)}--匯出考卷`;
        list.sort((a,b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
        const used = new Set();
        for(const r of list){
          const buffer = await templateFor(r.groupKey || 'grpBio');
          if(!buffer) throw new Error('沒有可用的 Word 範本，已停止匯出。');
          const {payload} = window.buildRecordDocPayload(r);
          let file = `${safeName(r.quizTitle)}_${dotted(taipeiDate(r.timestamp))}`;
          while(used.has(file)) file += '_2';
          used.add(file);
          zip.file(`${folder}/附件1.${file}.docx`, renderDocx(buffer, payload));
          count++;
        }
      }
      const blob = zip.generate({type:'blob', mimeType:'application/zip'});
      const only = people.size === 1 ? [...people.values()][0][0] : null;
      const zipName = only ? `${safeName(only.name)}--匯出考卷.zip` : `考卷依人員_${people.size}人_${new Date().toISOString().slice(0,10)}.zip`;
      saveAs(blob, zipName);
      alert(`已匯出 ${people.size} 人、共 ${count} 份考卷。\n解壓縮後，每個人一個資料夾（例如「張嘉琴--匯出考卷」）。`);
    } catch (error) {
      console.error(error);
      alert(`匯出失敗：${error.message}`);
    } finally {
      if(button){ button.disabled = false; button.textContent = label; }
    }
  };

  /* ---------- 2. QP15-L03 人員能力評估考核紀錄表 ---------- */
  function examGroups(rows){
    const map = new Map();
    for(const r of rows){
      const key = String(r.quizCategoryId || r.quizTitle || '');
      if(!map.has(key)) map.set(key, {key, title: r.quizTitle || '（未命名考卷）', rows: []});
      map.get(key).rows.push(r);
    }
    for(const g of map.values()){
      g.rows.sort((a,b) => String(a.empId || '').localeCompare(String(b.empId || '')) || String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hant'));
      const dates = g.rows.map(r => taipeiDate(r.timestamp)).filter(Boolean).sort();
      g.first = dates[0] || ''; g.last = dates[dates.length - 1] || '';
    }
    return [...map.values()].sort((a,b) => a.title.localeCompare(b.title, 'zh-Hant'));
  }

  function closeDialog(){ document.getElementById('qp15-l03-dialog')?.remove(); }

  window.openQp15L03Dialog = async function(){
    let rows;
    try { rows = await visibleRecords(); } catch (e) { alert(e.message); return; }
    if(!rows.length){ alert('目前篩選條件下沒有已完成的考核紀錄。'); return; }
    const exams = examGroups(rows);
    const saved = loadSettings();
    const lastDate = exams.map(g => g.last).filter(Boolean).sort().pop() || '';
    const defaultTitle = `${rocYear()}年${groupName(rows[0].groupLabel) || '生化組'}教育訓練`;
    closeDialog();
    const box = document.createElement('div');
    box.id = 'qp15-l03-dialog';
    box.className = 'fixed inset-0 z-[90] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4';
    box.innerHTML = `<div class="w-full max-w-3xl rounded-2xl bg-white p-5 shadow-2xl space-y-4 my-6">
      <div class="flex items-start justify-between gap-3"><div><h3 class="text-lg font-black text-slate-900">📋 產生 QP15-L03 人員能力評估考核紀錄表</h3>
      <p class="text-xs text-slate-500 mt-1">依目前畫面的篩選：${exams.length} 份考卷、${rows.length} 筆紀錄。每份考卷印成一張表，表內列出所有考核者。</p></div>
      <button type="button" data-qp15-close class="text-slate-400 hover:text-slate-700 text-xl leading-none">✕</button></div>
      <div class="grid sm:grid-cols-2 gap-3">
        <label class="text-xs font-bold text-slate-700">名稱<input data-qp15-title class="learning-input mt-1 w-full" value="${esc(saved.title || defaultTitle)}"></label>
        <label class="text-xs font-bold text-slate-700">課程結束日（有效日期＝這天＋1年）<input type="date" data-qp15-end class="learning-input mt-1 w-full" value="${esc(saved.endDate || lastDate)}"></label>
      </div>
      <p class="text-xs text-slate-500">有效日期：<b data-qp15-valid class="text-slate-800"></b>　·　備註欄留空。</p>
      <div class="overflow-x-auto rounded-xl border border-slate-200"><table class="w-full text-xs"><thead class="bg-slate-50 text-slate-700"><tr><th class="p-2 text-left">考卷</th><th class="p-2 text-left">評估項目（可修改）</th><th class="p-2 text-left">教育訓練日期</th><th class="p-2 text-left">考核日期</th><th class="p-2 text-center">人數</th></tr></thead>
      <tbody class="divide-y divide-slate-100">${exams.map((g,i) => {
        const range = g.first === g.last ? dotted(g.first) : `${dotted(g.first)}～${dotted(g.last)}`;
        const train = (saved.training || {})[g.key] || '';
        return `<tr><td class="p-2 text-slate-600">${esc(g.title)}</td><td class="p-2"><input data-qp15-item="${i}" class="learning-input w-full" value="${esc(g.title)}"></td><td class="p-2"><input data-qp15-train="${i}" class="learning-input w-full" placeholder="例：2026.10.20" value="${esc(train)}"></td><td class="p-2"><input data-qp15-exam="${i}" class="learning-input w-full" value="${esc(range)}"></td><td class="p-2 text-center">${g.rows.length}</td></tr>`;
      }).join('')}</tbody></table></div>
      <div class="flex justify-end gap-2"><button type="button" data-qp15-close class="border border-slate-300 bg-white text-slate-700 text-xs font-bold px-3 py-2 rounded-lg">取消</button>
      <button type="button" data-qp15-go class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-4 py-2 rounded-lg">📄 產生 Word</button></div></div>`;
    document.body.appendChild(box);
    const endInput = box.querySelector('[data-qp15-end]');
    const paintValid = () => { box.querySelector('[data-qp15-valid]').textContent = plusOneYear(endInput.value) || '（請先選課程結束日）'; };
    endInput.addEventListener('input', paintValid); paintValid();
    box.querySelectorAll('[data-qp15-close]').forEach(b => b.addEventListener('click', closeDialog));
    box.querySelector('[data-qp15-go]').addEventListener('click', async ev => {
      const btn = ev.currentTarget;
      const title = box.querySelector('[data-qp15-title]').value.trim();
      const endDate = endInput.value;
      if(!endDate){ alert('請先選「課程結束日」，才能算出有效日期。'); return; }
      const validUntil = plusOneYear(endDate);
      const training = {};
      const payload = {exams: exams.map((g,i) => {
        training[g.key] = box.querySelector(`[data-qp15-train="${i}"]`).value.trim();
        return {
          title,
          item: box.querySelector(`[data-qp15-item="${i}"]`).value.trim(),
          trainingDate: training[g.key],
          examDate: box.querySelector(`[data-qp15-exam="${i}"]`).value.trim(),
          rows: g.rows.map(r => {
            const pass = r.status === '合格';
            return {name: r.name || '', evaluator: r.evaluatorName || '', date: dotted(taipeiDate(r.timestamp)), yes: pass ? '■' : '□', no: pass ? '□' : '■', validUntil: pass ? validUntil : '', note: ''};
          })
        };
      })};
      saveSettings({title, endDate, training});
      btn.disabled = true; btn.textContent = '⏳ 產生中…';
      try {
        const res = await fetch(L03_TEMPLATE_URL, {credentials:'same-origin'});
        if(!res.ok) throw new Error('讀不到 QP15-L03 範本');
        const data = renderDocx(await res.arrayBuffer(), payload);
        saveAs(new Blob([data], {type: DOCX_MIME}), `QP15-L03_${safeName(title)}.docx`);
        closeDialog();
      } catch (error) {
        console.error(error);
        alert(`產生失敗：${error.message}`);
        btn.disabled = false; btn.textContent = '📄 產生 Word';
      }
    });
  };

  /* ---------- 按鈕：放在「匯出 CSV」旁邊 ---------- */
  function mountButtons(){
    document.querySelectorAll('[data-csp-click="exportToCSV()"]').forEach(csv => {
      if(csv.parentElement?.querySelector('[data-batch-word-1106]')) return;
      const make = (text, attr, cls, handler) => {
        const b = document.createElement('button');
        b.type = 'button'; b.setAttribute(attr, ''); b.className = cls; b.textContent = text;
        b.addEventListener('click', () => handler(b));
        return b;
      };
      const word = make('📦 依人員匯出 Word', 'data-batch-word-1106', 'bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-3 py-2 rounded-lg', b => window.exportWordByPerson(b));
      word.title = '依目前篩選，一次匯出所有人的考卷 Word，每人一個資料夾';
      const l03 = make('📋 QP15-L03 紀錄表', 'data-qp15-l03-1106', 'bg-white border border-indigo-300 hover:bg-indigo-50 text-indigo-800 text-xs font-bold px-3 py-2 rounded-lg', () => window.openQp15L03Dialog());
      l03.title = '依目前篩選，產生人員能力評估考核紀錄表（每份考卷一張）';
      csv.insertAdjacentElement('afterend', l03);
      csv.insertAdjacentElement('afterend', word);
    });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountButtons); else mountButtons();
  window.mountResultsBatchExport = mountButtons;
})();
