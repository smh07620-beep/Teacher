/* 2026-11-06 · 成績紀錄：依人員一鍵匯出 Word ＋ 產生 QP15-L03 人員能力評估考核紀錄表。
 * 兩個按鈕都依照畫面上的篩選（考卷、通過成績／每次作答、結果、搜尋），包含所有分頁。
 */
(function(){
  'use strict';

  const L03_TEMPLATE_URL = '/templates/QP15-L03.docx';
  const SETTINGS_KEY = 'teacher.qp15l03.settings.v1';
  const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

  // Word 套件：外部網站（cdnjs）被醫院網路擋住時，改用本站 /vendor 的同版本備份。
  const VENDOR = [
    ['PizZip', '/vendor/pizzip-3.1.4.min.js'],
    ['docxtemplater', '/vendor/docxtemplater-3.37.11.js'],
    ['saveAs', '/vendor/FileSaver-2.0.5.min.js'],
  ];
  function loadScript(src){
    return new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = src; el.async = false;
      el.onload = resolve; el.onerror = () => reject(new Error(`無法載入 ${src}`));
      document.head.appendChild(el);
    });
  }
  async function ensureWordLibs(){
    for(const [name, src] of VENDOR){
      if(typeof window[name] === 'undefined') await loadScript(src);
    }
    if(typeof window.PizZip === 'undefined' || typeof window.docxtemplater === 'undefined') throw new Error('Word 匯出元件載入失敗，請重新整理頁面再試。');
  }

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
    const doc = new window.docxtemplater(new window.PizZip(buffer), {paragraphLoop:true, linebreaks:true});
    doc.render(payload);
    return doc.getZip().generate({type:'uint8array'});
  }

  window.exportWordByPerson = async function(button, onlyRows){
    const label = button ? button.textContent : '';
    try {
      if(button){ button.disabled = true; button.textContent = '⏳ 匯出中…'; }
      await ensureWordLibs();
      const rows = Array.isArray(onlyRows) ? onlyRows.filter(r => r && r.reviewStatus !== 'pending') : await visibleRecords();
      if(!rows.length){ alert('目前篩選條件下沒有可匯出的考卷。'); return; }
      const people = new Map();
      for(const r of rows){
        const key = `${r.empId || ''}|${r.name || ''}`;
        if(!people.has(key)) people.set(key, []);
        people.get(key).push(r);
      }
      const zip = new window.PizZip();
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
      if(!onlyRows) alert(`已匯出 ${people.size} 人、共 ${count} 份考卷。\n解壓縮後，每個人一個資料夾（例如「張嘉琴--匯出考卷」）。`);
    } catch (error) {
      console.error(error);
      alert(`匯出失敗：${error.message}`);
    } finally {
      if(button){ button.disabled = false; button.textContent = label; }
    }
  };


  /* ---------- 合併成一份 Word（方便一次列印） ---------- */
  // 把各組附件1 範本整個包進 {#records}…{/records}，每份考卷從新的一頁開始。
  function mergedTemplate(buffer){
    const zip = new window.PizZip(buffer);
    const doc = new DOMParser().parseFromString(zip.file('word/document.xml').asText(), 'application/xml');
    const NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
    const body = doc.getElementsByTagNameNS(NS, 'body')[0];
    const tagPara = text => {
      const p = doc.createElementNS(NS, 'w:p'), r = doc.createElementNS(NS, 'w:r'), t = doc.createElementNS(NS, 'w:t');
      t.textContent = text; r.appendChild(t); p.appendChild(r); return p;
    };
    const items = [...body.childNodes].filter(n => n.nodeType === 1 && n.localName !== 'sectPr');
    let first = items[0];
    if(!first || first.localName !== 'p'){ first = doc.createElementNS(NS, 'w:p'); body.insertBefore(first, items[0] || null); }
    let ppr = [...first.childNodes].find(n => n.localName === 'pPr');
    if(!ppr){ ppr = doc.createElementNS(NS, 'w:pPr'); first.insertBefore(ppr, first.firstChild); }
    ppr.insertBefore(doc.createElementNS(NS, 'w:pageBreakBefore'), ppr.firstChild);
    body.insertBefore(tagPara('{#records}'), first);
    const sect = [...body.childNodes].find(n => n.nodeType === 1 && n.localName === 'sectPr');
    body.insertBefore(tagPara('{/records}'), sect || null);
    // 「與下段同頁」串在一起時，舊版 Word 開大檔會一直重排而卡住；每份只有一頁，拿掉不影響版面。
    ['keepNext', 'keepLines'].forEach(name => [...body.getElementsByTagNameNS(NS, name)].forEach(el => el.parentNode.removeChild(el)));
    zip.file('word/document.xml', new XMLSerializer().serializeToString(doc));
    return zip.generate({type:'arraybuffer'});
  }

  window.exportMergedWord = async function(button, onlyRows){
    const label = button ? button.textContent : '';
    try {
      if(button){ button.disabled = true; button.textContent = '⏳ 合併中…'; }
      await ensureWordLibs();
      const rows = Array.isArray(onlyRows) ? onlyRows.filter(r => r && r.reviewStatus !== 'pending') : await visibleRecords();
      if(!rows.length){ alert('目前篩選條件下沒有可匯出的考卷。'); return; }
      const sorted = [...rows].sort((a,b) => String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hant') || String(a.empId || '').localeCompare(String(b.empId || '')) || String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
      const byGroup = new Map();
      sorted.forEach(r => { const g = r.groupKey || 'grpBio'; if(!byGroup.has(g)) byGroup.set(g, []); byGroup.get(g).push(r); });
      const files = [];
      for(const [groupKey, list] of byGroup){
        const buffer = await templateFor(groupKey);
        if(!buffer) throw new Error('沒有可用的 Word 範本，已停止匯出。');
        const records = list.map(r => window.buildRecordDocPayload(r).payload);
        const people = new Set(list.map(r => `${r.empId || ''}|${r.name || ''}`)).size;
        const label2 = groupName(list[0].groupLabel) || '考卷';
        const prefix = people === 1 ? `${safeName(list[0].name)}--考卷合併` : `${label2}_考卷合併_${people}人${list.length}份`;
        files.push({name: `${prefix}_${new Date().toISOString().slice(0,10)}.docx`, data: renderDocx(mergedTemplate(buffer), {records})});
      }
      if(files.length === 1){
        saveAs(new Blob([files[0].data], {type: DOCX_MIME}), files[0].name);
      } else {
        const zip = new window.PizZip();
        files.forEach(f => zip.file(f.name, f.data));
        saveAs(zip.generate({type:'blob', mimeType:'application/zip'}), `考卷合併_各組_${new Date().toISOString().slice(0,10)}.zip`);
      }
    } catch (error) {
      console.error(error);
      alert(`合併失敗：${error.message}`);
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


  /* ---------- QP15-L03 範本：內建版 or 上傳的新版 QP15 ---------- */
  const L03_KEY = 'qp15L03';
  const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
  const wq = (el, name) => [...el.getElementsByTagNameNS(W, name)];
  const kids = (el, name) => [...el.childNodes].filter(n => n.nodeType === 1 && n.namespaceURI === W && n.localName === name);
  const textOf = el => wq(el, 't').map(t => t.textContent).join('');

  function setPara(p, text){
    const doc = p.ownerDocument;
    const runs = kids(p, 'r');
    [...p.childNodes].forEach(n => { if(n.nodeType === 1 && n.localName !== 'pPr' && n !== runs[0]) p.removeChild(n); });
    let run = runs[0];
    if(!run){ run = doc.createElementNS(W, 'w:r'); p.appendChild(run); }
    [...run.childNodes].forEach(n => { if(n.localName !== 'rPr') run.removeChild(n); });
    const t = doc.createElementNS(W, 'w:t');
    t.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
    t.textContent = text;
    run.appendChild(t);
  }


  // 頁尾「第 PAGE 頁」換成固定的 {pageNo}（依 QP15 中 L03 的頁碼）。
  function lockPageField(xml){
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    const makeRun = like => {
      const r = doc.createElementNS(W, 'w:r');
      const rpr = like && kids(like, 'rPr')[0];
      if(rpr) r.appendChild(rpr.cloneNode(true));
      const t = doc.createElementNS(W, 'w:t'); t.textContent = '{pageNo}';
      r.appendChild(t);
      return r;
    };
    wq(doc, 'p').forEach(p => {
      const runs = wq(p, 'r');
      for(let i = 0; i < runs.length; i++){
        const fc = kids(runs[i], 'fldChar')[0];
        if(!fc || fc.getAttributeNS(W, 'fldCharType') !== 'begin') continue;
        let j = i, instr = '';
        for(; j < runs.length; j++){
          instr += kids(runs[j], 'instrText').map(t => t.textContent).join('');
          const f2 = kids(runs[j], 'fldChar')[0];
          if(f2 && f2.getAttributeNS(W, 'fldCharType') === 'end') break;
        }
        if(instr.trim().split(/\s+/)[0] === 'PAGE'){
          runs[i].parentNode.insertBefore(makeRun(runs[i]), runs[i]);
          runs.slice(i, j + 1).forEach(r => r.parentNode && r.parentNode.removeChild(r));
        }
        i = j;
      }
    });
    wq(doc, 'fldSimple').forEach(fs => {
      if((fs.getAttributeNS(W, 'instr') || '').trim().split(/\s+/)[0] !== 'PAGE') return;
      fs.parentNode.insertBefore(makeRun(kids(fs, 'r')[0]), fs);
      fs.parentNode.removeChild(fs);
    });
    return new XMLSerializer().serializeToString(doc);
  }

  // 從整份 SMH-LAB-QP15 擷取「附件6 QP15-L03」，填入網站欄位，回傳新的 .docx（ArrayBuffer）。
  window.buildQp15L03Template = function(buffer){
    const zip = new window.PizZip(buffer);
    const file = zip.file('word/document.xml');
    if(!file) throw new Error('這不是 Word（.docx）檔。');
    const doc = new DOMParser().parseFromString(file.asText(), 'application/xml');
    const body = wq(doc, 'body')[0];
    const els = [...body.childNodes].filter(n => n.nodeType === 1);
    const start = els.findIndex(e => textOf(e).trim().startsWith('附件6'));
    if(start < 0) throw new Error('找不到「附件6.」段落。');
    let end = els.findIndex((e, i) => i > start && textOf(e).includes('附件7'));
    if(end < 0) end = els.length - 1;
    const sectOf = e => e.localName === 'sectPr' ? e : wq(e, 'sectPr')[0];
    const firstSect = els.map(sectOf).find(Boolean);
    let sect = els.slice(end).map(sectOf).find(Boolean);
    if(!sect) throw new Error('找不到附件6 的版面設定。');
    sect = sect.cloneNode(true);
    if(!kids(sect, 'headerReference').length && firstSect){
      kids(firstSect, 'headerReference').concat(kids(firstSect, 'footerReference'))
        .filter(r => r.getAttributeNS(W, 'type') === 'default')
        .reverse().forEach(r => sect.insertBefore(r.cloneNode(true), sect.firstChild));
    }
    const keep = els.slice(start, end + 1);
    els.forEach(e => { if(!keep.includes(e)) body.removeChild(e); });
    const paras = keep.filter(e => e.localName === 'p');
    const find = prefix => paras.find(p => textOf(p).replace(/\s/g, '').startsWith(prefix));
    const titleP = find('名稱'), itemP = find('評估項目'), dateP = find('教育訓練日期');
    if(!titleP || !itemP || !dateP) throw new Error('附件6 要有「名稱：」「評估項目：」「教育訓練日期」這三行。');
    setPara(titleP, '名稱：{title}');
    setPara(itemP, '評估項目：{item}');
    setPara(dateP, '教育訓練日期：{trainingDate}　　　　考核日期：{examDate}');
    const last = keep[keep.length - 1];
    if(last.localName === 'p' && textOf(last).includes('附件7')){
      setPara(last, textOf(last).split('附件7')[0].trim());
      wq(last, 'br').forEach(b => b.parentNode.removeChild(b));
    }
    const tbl = keep.find(e => e.localName === 'tbl' && textOf(kids(e, 'tr')[0] || e).includes('姓名'));
    if(!tbl) throw new Error('附件6 找不到「姓名／考核者／考核日期…」那張表。');
    const rows = kids(tbl, 'tr');
    const cells = rows[1] ? kids(rows[1], 'tc') : [];
    if(cells.length < 6) throw new Error('附件6 的表格要有 6 欄（姓名、考核者、考核日期、是否通過、有效日期、備註）。');
    rows.slice(2).forEach(r => tbl.removeChild(r));
    ['{#rows}{name}', '{evaluator}', '{date}', '{yes}是{no}否', '{validUntil}', '{note}{/rows}'].forEach((v, i) => {
      const ps = kids(cells[i], 'p');
      ps.slice(1).forEach(p => cells[i].removeChild(p));
      setPara(ps[0], v);
    });
    const first = keep[0];
    let ppr = kids(first, 'pPr')[0];
    if(!ppr){ ppr = doc.createElementNS(W, 'w:pPr'); first.insertBefore(ppr, first.firstChild); }
    ppr.insertBefore(doc.createElementNS(W, 'w:pageBreakBefore'), ppr.firstChild);
    const open = titleP.cloneNode(true); setPara(open, '{#exams}');
    const close = titleP.cloneNode(true); setPara(close, '{/exams}');
    body.insertBefore(open, body.firstChild);
    wq(body, 'sectPr').forEach(sp => sp.parentNode.removeChild(sp));
    body.appendChild(close);
    body.appendChild(sect);
    zip.file('word/document.xml', new XMLSerializer().serializeToString(doc));
    Object.keys(zip.files).filter(n => /^word\/(footer|header)\d*\.xml$/.test(n)).forEach(n => {
      zip.file(n, lockPageField(zip.file(n).asText()));
    });
    return zip.generate({type:'arraybuffer'});
  };

  async function l03TemplateBuffer(){
    try {
      const res = await fetch(`/api/doc-templates/${L03_KEY}/download`, {credentials:'same-origin'});
      if(res.ok) return await res.arrayBuffer();
    } catch (_) {}
    const res = await fetch(L03_TEMPLATE_URL, {credentials:'same-origin'});
    if(!res.ok) throw new Error('讀不到 QP15-L03 範本');
    return await res.arrayBuffer();
  }

  async function paintL03Source(box){
    const el = box.querySelector('[data-qp15-source]');
    if(!el) return;
    let info = {};
    try { const r = await fetch(`/api/doc-templates/${L03_KEY}/info`, {credentials:'same-origin'}); if(r.ok) info = await r.json(); } catch (_) {}
    el.innerHTML = info.exists
      ? `目前版面：<b>你上傳的「${esc(info.filename)}」</b>（${esc(String(info.uploadedAt || '').slice(0,10))}）`
      : '目前版面：<b>內建版</b>（QP15 第 14 版，2026.08.05）';
    box.querySelector('[data-qp15-reset]')?.classList.toggle('hidden', !info.exists);
  }

  async function uploadL03(box){
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.docx';
    input.addEventListener('change', async () => {
      const f = input.files && input.files[0];
      if(!f) return;
      try {
        await ensureWordLibs();
        const built = window.buildQp15L03Template(await f.arrayBuffer());
        const form = new FormData();
        form.append('file', new Blob([built], {type: DOCX_MIME}), f.name);
        const res = await fetch(`/api/doc-templates/${L03_KEY}`, {method:'POST', body: form, credentials:'same-origin'});
        const data = await res.json().catch(() => ({}));
        if(!res.ok) throw new Error(data.error || '上傳失敗');
        alert('已換成新版 QP15-L03，之後產生的紀錄表都會用這個版面。');
        paintL03Source(box);
      } catch (error) {
        alert(`無法使用這份檔案：${error.message}\n\n只改文字、字型、版次都可以；若附件6 的表格整個重新設計，請把檔案傳給系統維護者處理。`);
      }
    });
    input.click();
  }

  async function resetL03(box){
    if(!confirm('要改回網站內建的 QP15-L03 版面嗎？')) return;
    const res = await fetch(`/api/doc-templates/${L03_KEY}`, {method:'DELETE', credentials:'same-origin'});
    const data = await res.json().catch(() => ({}));
    if(!res.ok){ alert(data.error || '改回失敗'); return; }
    paintL03Source(box);
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
      <label class="text-xs font-bold text-slate-700 flex items-center gap-2">頁尾頁碼：第 <input data-qp15-page class="learning-input w-20 text-center" value="${esc(saved.pageNo || '21')}"> 頁<span class="font-normal text-slate-400">（依 QP15 中 L03 所在頁，固定不跳號）</span></label>
      <p class="text-xs text-slate-500">有效日期：<b data-qp15-valid class="text-slate-800"></b>　·　備註欄留空。</p>
      <div class="overflow-x-auto rounded-xl border border-slate-200"><table class="w-full text-xs"><thead class="bg-slate-50 text-slate-700"><tr><th class="p-2 text-left">考卷</th><th class="p-2 text-left">評估項目（可修改）</th><th class="p-2 text-left">教育訓練日期</th><th class="p-2 text-left">考核日期</th><th class="p-2 text-center">人數</th></tr></thead>
      <tbody class="divide-y divide-slate-100">${exams.map((g,i) => {
        const range = g.first === g.last ? dotted(g.first) : `${dotted(g.first)}～${dotted(g.last)}`;
        const train = (saved.training || {})[g.key] || '';
        return `<tr><td class="p-2 text-slate-600">${esc(g.title)}</td><td class="p-2"><input data-qp15-item="${i}" class="learning-input w-full" value="${esc(g.title)}"></td><td class="p-2"><input data-qp15-train="${i}" class="learning-input w-full" placeholder="例：2026.10.20" value="${esc(train)}"></td><td class="p-2"><input data-qp15-exam="${i}" class="learning-input w-full" value="${esc(range)}"></td><td class="p-2 text-center">${g.rows.length}</td></tr>`;
      }).join('')}</tbody></table></div>
      <div class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-600"><span data-qp15-source>目前版面：讀取中…</span><span class="flex gap-2"><button type="button" data-qp15-upload class="border border-indigo-300 bg-white text-indigo-800 font-bold px-2.5 py-1.5 rounded-lg">⬆️ 上傳新版 QP15</button><button type="button" data-qp15-reset class="hidden border border-slate-300 bg-white text-slate-600 px-2.5 py-1.5 rounded-lg">改回內建版</button></span></div>
      <div class="flex justify-end gap-2"><button type="button" data-qp15-close class="border border-slate-300 bg-white text-slate-700 text-xs font-bold px-3 py-2 rounded-lg">取消</button>
      <button type="button" data-qp15-go class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-4 py-2 rounded-lg">📄 產生 Word</button></div></div>`;
    document.body.appendChild(box);
    const endInput = box.querySelector('[data-qp15-end]');
    const paintValid = () => { box.querySelector('[data-qp15-valid]').textContent = plusOneYear(endInput.value) || '（請先選課程結束日）'; };
    endInput.addEventListener('input', paintValid); paintValid();
    paintL03Source(box);
    box.querySelector('[data-qp15-upload]').addEventListener('click', () => uploadL03(box));
    box.querySelector('[data-qp15-reset]').addEventListener('click', () => resetL03(box));
    box.querySelectorAll('[data-qp15-close]').forEach(b => b.addEventListener('click', closeDialog));
    box.querySelector('[data-qp15-go]').addEventListener('click', async ev => {
      const btn = ev.currentTarget;
      const title = box.querySelector('[data-qp15-title]').value.trim();
      const endDate = endInput.value;
      if(!endDate){ alert('請先選「課程結束日」，才能算出有效日期。'); return; }
      const validUntil = plusOneYear(endDate);
      const pageNo = box.querySelector('[data-qp15-page]').value.trim() || '21';
      const training = {};
      const payload = {pageNo, exams: exams.map((g,i) => {
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
      saveSettings({title, endDate, training, pageNo});
      btn.disabled = true; btn.textContent = '⏳ 產生中…';
      try {
        await ensureWordLibs();
        const data = renderDocx(await l03TemplateBuffer(), payload);
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
      const merged = make('🖨️ 合併成一份 Word', 'data-merged-word-1106', 'bg-white border border-indigo-300 hover:bg-indigo-50 text-indigo-800 text-xs font-bold px-3 py-2 rounded-lg', b => window.exportMergedWord(b));
      merged.title = '依目前篩選，把所有考卷合成一個 Word，每份一頁，方便一次列印';
      csv.insertAdjacentElement('afterend', merged);
      csv.insertAdjacentElement('afterend', word);
    });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountButtons); else mountButtons();
  window.mountResultsBatchExport = mountButtons;
})();
