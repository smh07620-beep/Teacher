from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, text):
    (ROOT / path).write_text(text.rstrip() + '\n', encoding='utf-8')


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, f'{label}: expected exactly one match, got {count}'
    return text.replace(old, new, 1)

# --- Canonical AI runtime: auto-select up to 3 exam-linked materials. ---
path = 'static/admin-ai-questions.js'
text = read(path)
text = replace_once(
    text,
    "  const state = id => picker[id] || (picker[id] = {selected:new Set(),limit:12});",
    "  const state = id => picker[id] || (picker[id] = {selected:new Set(),limit:12,autoLinked:false});",
    'AI picker state',
)

summary_pattern = re.compile(r"  function summary\(id\) \{.*?\n  function renderPicker", re.S)
match = summary_pattern.search(text)
assert match, 'AI material summary block not found'
summary_new = '''  function summary(id) {
    const el=document.getElementById(`ai-selected-${id}`),s=state(id),items=(catalog[id]||[]).filter(m=>s.selected.has(String(m.id)));
    if(!el)return;
    if(!items.length){el.innerHTML='<span class="text-slate-400">尚未選擇教材；若考卷已關聯教材會自動帶入最多 3 份。</span>';return;}
    const label=s.autoLinked?`已自動帶入 ${items.length} 份關聯教材`:`已選 ${items.length} / 4`;
    el.innerHTML=`<div class="flex items-center gap-1.5 flex-wrap"><span class="font-black text-violet-800 mr-1">${label}</span>${items.map(m=>`<button type="button" onclick="toggleAiMaterialSelection('${id}','${String(m.id).replaceAll("'","\\\\'")}',false)" class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-violet-100 text-violet-800 font-bold max-w-[260px]" title="移除此教材"><span class="truncate">${escapeHtml(m.title||m.filename)}</span><span>×</span></button>`).join('')}</div>`;
  }
  function renderPicker'''
text = text[:match.start()] + summary_new + text[match.end():]

toggle_pattern = re.compile(r"  window\.toggleAiMaterialSelection=.*?\n  window\.filterAiMaterials", re.S)
match = toggle_pattern.search(text)
assert match, 'AI material toggle block not found'
toggle_new = '''  window.toggleAiMaterialSelection=(id,item,checked)=>{const s=state(id),key=String(item),m=(catalog[id]||[]).find(x=>String(x.id)===key);s.autoLinked=false;if(checked){if(!s.selected.has(key)&&s.selected.size>=4){alert('一次最多選 4 份教材');return renderPicker(id,true);}if(m&&kind(m)[0]==='video'&&[...s.selected].some(x=>{const other=(catalog[id]||[]).find(y=>String(y.id)===x);return other&&kind(other)[0]==='video';})){alert('一次最多選 1 支影片；可再搭配字幕、圖片或文件');return renderPicker(id,true);}s.selected.add(key);}else s.selected.delete(key);renderPicker(id,true);};
  window.filterAiMaterials'''
text = text[:match.start()] + toggle_new + text[match.end():]

recommend_pattern = re.compile(r"  window\.recommendAiMaterials=.*?\n  window\.loadAiMaterialOptions=.*?\n  function progress", re.S)
match = recommend_pattern.search(text)
assert match, 'AI material recommend/load block not found'
recommend_new = '''  function autoSelectLinkedAiMaterials(id,mats){
    const s=state(id),linked=(mats||[]).filter(m=>m.category===id);
    if(s.selected.size||!linked.length) return;
    const nonVideo=linked.filter(m=>kind(m)[0]!=='video');
    const video=linked.find(m=>kind(m)[0]==='video');
    const chosen=nonVideo.slice(0,video?2:3);
    if(video&&chosen.length<3) chosen.push(video);
    s.selected=new Set(chosen.slice(0,3).map(m=>String(m.id)));
    s.autoLinked=true;
  }
  window.recommendAiMaterials=id=>{const s=state(id),all=catalog[id]||[],linked=all.filter(m=>m.category===id),pool=linked.length?linked:all,nonVideo=pool.filter(m=>kind(m)[0]!=='video'),video=pool.find(m=>kind(m)[0]==='video'),chosen=nonVideo.slice(0,video?2:3);if(video&&chosen.length<3)chosen.push(video);s.selected=new Set(chosen.slice(0,3).map(m=>String(m.id)));s.autoLinked=linked.length>0;renderPicker(id,true);};
  window.loadAiMaterialOptions=async id=>{const box=document.getElementById(`ai-materials-${id}`);if(!box)return;const group=box.dataset.group||'',area=box.dataset.area||currentTrainingArea;box.innerHTML='<div class="text-xs text-slate-400">讀取本組教材中…</div>';try{const r=await fetch(`/api/slides?area=${encodeURIComponent(area)}`),list=await r.json();const mats=(Array.isArray(list)?list:[]).filter(m=>m.group===group&&(m.area||'internal')===area&&!m.isBuiltin);catalog[id]=mats;autoSelectLinkedAiMaterials(id,mats);if(!mats.length){box.innerHTML='<div class="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-xs text-slate-500">尚無可供 AI 讀取的教材，請先到「課程與教材」上傳 PPT/PDF/圖片/影音/字幕。</div>';return summary(id);}renderPicker(id);}catch(_e){box.innerHTML='<div class="text-xs text-rose-500">教材清單讀取失敗</div>';}};
  function progress'''
text = text[:match.start()] + recommend_new + text[match.end():]
write(path, text)

# --- Studio orchestration: fast bounded preparation + compact materials/advanced controls. ---
path = 'static/teacher-content-studio-71.js'
text = read(path)
anchor = "  const aiMount = {section:null, placeholder:null, catId:''};\n"
addition = '''  const AI_PREPARE_DEADLINE_77 = 6000;

  function withTimeout77(task,ms,label){
    const promise=Promise.resolve(task);
    return Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(new Error(`${label}逾時，請重新嘗試。`)),Math.max(250,ms||250)))]);
  }

  function aiPrepareStatus77(host,label,detail=''){
    if(!host) return;
    host.innerHTML=`<div class="rounded-2xl border border-violet-100 bg-violet-50 p-5 text-sm text-violet-700"><div class="font-black">${esc(label)}</div>${detail?`<div class="mt-1 text-xs text-violet-500">${esc(detail)}</div>`:''}</div>`;
  }

  function compactAiStudio77(section,catId){
    if(!section) return;
    const search=document.getElementById(`ai-material-search-${catId}`);
    const materialBlock=search?.closest('[class*="lg:col-span-3"]');
    const selectedBox=document.getElementById(`ai-selected-${catId}`);
    if(materialBlock&&selectedBox&&!section.querySelector('[data-ai-material-summary-77]')){
      const compact=document.createElement('div');
      compact.dataset.aiMaterialSummary77='1';
      compact.className='lg:col-span-3 rounded-2xl border border-violet-100 bg-violet-50/50 p-3';
      compact.innerHTML=`<div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black text-violet-900">📚 出題教材</div><div class="mt-1 text-[11px] text-slate-500">依所選考卷自動帶入最多 3 份關聯教材；影片最多 1 支。</div></div><button type="button" data-ai-adjust-materials-77 class="rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-bold text-violet-700">調整教材</button></div><div data-ai-linked-summary-77 class="mt-2"></div>`;
      materialBlock.before(compact);
      compact.querySelector('[data-ai-linked-summary-77]')?.appendChild(selectedBox);
      materialBlock.classList.add('hidden');
      compact.querySelector('[data-ai-adjust-materials-77]')?.addEventListener('click',()=>materialBlock.classList.toggle('hidden'));
    }

    const controlNames=['type','difficulty','count','strategy','focus'];
    const wrappers=[...new Set(controlNames.map(name=>document.getElementById(`ai-${name}-${catId}`)?.parentElement).filter(Boolean))];
    if(wrappers.length&&!section.querySelector('[data-ai-advanced-77]')){
      const parent=wrappers[0].parentElement;
      const details=document.createElement('details');
      details.dataset.aiAdvanced77='1';
      details.className='lg:col-span-3 rounded-xl border border-slate-200 bg-slate-50 p-3';
      details.innerHTML='<summary class="cursor-pointer text-xs font-black text-slate-700">⚙️ 進階設定（題型／難度／題數／策略／出題重點）</summary><div data-ai-advanced-grid-77 class="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-3"></div>';
      parent?.insertBefore(details,wrappers[0]);
      const grid=details.querySelector('[data-ai-advanced-grid-77]');
      wrappers.forEach(node=>grid?.appendChild(node));
    }
  }
'''
text = replace_once(text, anchor, anchor + addition, 'Studio 7.7 helpers anchor')

mount_pattern = re.compile(r"  async function mountAiPanel\(catId\)\{.*?\n  \}\n\n  async function chooseExamForQuestion", re.S)
match = mount_pattern.search(text)
assert match, 'mountAiPanel block not found'
mount_new = '''  async function mountAiPanel(catId){
    if(!catId) return;
    const host=document.getElementById('teacher-content-studio-body-71');
    if(!host) return;
    const selectedScope=scope(),deadline=Date.now()+AI_PREPARE_DEADLINE_77;
    const remain=()=>Math.max(250,deadline-Date.now());
    const bounded=(task,label,maxMs=2600)=>withTimeout77(task,Math.min(maxMs,remain()),label);
    restoreAiPanel();
    try{
      let panel=document.getElementById(`qpanel-${catId}`);
      if(!panel){
        aiPrepareStatus77(host,'正在切換到考核工作區…','只在需要時建立考卷／題庫 DOM。');
        await bounded(window.openAdminWorkspace?.('assessment'),'切換考核工作區',1800);
        const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');
        if(area) area.value=selectedScope.area;
        if(group) group.value=selectedScope.group;
        panel=document.getElementById(`qpanel-${catId}`);
        if(!panel){
          aiPrepareStatus77(host,'正在讀取考卷…','同步目前組別的考卷與關聯教材。');
          await bounded(window.renderAdminQuizCategories?.(true),'讀取考卷',2600);
          panel=document.getElementById(`qpanel-${catId}`);
        }
      }
      if(!panel) throw new Error('找不到指定考卷，請重新選擇。');
      if(panel.classList.contains('hidden')){
        aiPrepareStatus77(host,'正在開啟題庫…','準備既有 AI 出題工作室。');
        await bounded(window.toggleQuizQuestionsPanel?.(catId),'開啟題庫',1600);
      }
      aiPrepareStatus77(host,'正在掛載 AI 出題工作室…','完成後會自動帶入本考卷關聯教材。');
      let section=panel.querySelector('[data-ai-question-studio]');
      if(!section) section=await waitForAiSection76(catId,Math.min(1400,remain()));
      if(!section) throw new Error('AI 出題工作室載入逾時，請按「重新嘗試」。');
      const placeholder=document.createElement('div');
      placeholder.hidden=true;
      placeholder.dataset.teacher75AiPlaceholder=String(catId);
      section.before(placeholder);
      aiMount.section=section;
      aiMount.placeholder=placeholder;
      aiMount.catId=String(catId);
      host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="mb-4 flex items-start justify-between gap-3"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 重新選擇考卷</button><h4 class="mt-2 text-lg font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">教材依考卷關聯自動帶入；常用設定由用途 preset 管理，細節需要時再展開。</p></div></div>${aiPresetPanel76(catId)}<div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      compactAiStudio77(section,catId);
      const presetSelect=host.querySelector('[data-ai-preset-select-76]'),presetButton=host.querySelector('[data-ai-apply-preset-76]'),customBox=host.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`);
      presetSelect?.addEventListener('change',()=>customBox?.classList.toggle('hidden',presetSelect.value!=='custom'));
      presetButton?.addEventListener('click',()=>{if(presetSelect?.value==='custom'){customBox?.classList.remove('hidden');return;}applyAiPreset76(catId,presetSelect?.value||'auto');});
      host.querySelector('[data-ai-apply-custom-76]')?.addEventListener('click',()=>applyAiCustomMix76(catId));
      applyAiPreset76(catId,'auto');
      requestAnimationFrame(()=>host.querySelector('[data-ai-ux-76]')?.scrollIntoView({behavior:'smooth',block:'start'}));
    }catch(error){
      restoreAiPanel();
      host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message||'AI 出題工作室開啟失敗')}<div class="mt-3 flex gap-2 flex-wrap"><button type="button" data-ai-retry-76 class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
      host.querySelector('[data-ai-retry-76]')?.addEventListener('click',()=>mountAiPanel(catId));
    }
  }

  async function chooseExamForQuestion'''
text = text[:match.start()] + mount_new + text[match.end():]
write(path, text)

# --- Regression contract. ---
test = '''import unittest\nfrom pathlib import Path\n\nROOT=Path(__file__).resolve().parents[1]\n\nclass AiAuthoringUxConvergence77Tests(unittest.TestCase):\n    def test_exam_linked_materials_are_auto_selected_with_three_item_default(self):\n        js=(ROOT/'static/admin-ai-questions.js').read_text(encoding='utf-8')\n        for token in ('autoSelectLinkedAiMaterials','m.category===id','slice(0,3)','autoLinked=true','一次最多選 4 份教材'):\n            self.assertIn(token,js)\n\n    def test_studio_compacts_material_picker_and_duplicate_controls(self):\n        js=(ROOT/'static/teacher-content-studio-71.js').read_text(encoding='utf-8')\n        for token in ('data-ai-material-summary-77','依所選考卷自動帶入最多 3 份關聯教材','調整教材','data-ai-advanced-77','進階設定（題型／難度／題數／策略／出題重點）'):\n            self.assertIn(token,js)\n\n    def test_ai_prepare_flow_has_fast_path_and_global_deadline(self):\n        js=(ROOT/'static/teacher-content-studio-71.js').read_text(encoding='utf-8')\n        self.assertIn('AI_PREPARE_DEADLINE_77 = 6000',js)\n        self.assertIn('let panel=document.getElementById(`qpanel-${catId}`)',js)\n        self.assertIn('if(!panel){',js)\n        self.assertIn('withTimeout77',js)\n        self.assertIn('正在掛載 AI 出題工作室',js)\n        self.assertIn('重新嘗試',js)\n\nif __name__=='__main__':\n    unittest.main()\n'''
write('tests/test_ai_authoring_ux_convergence_77.py', test)
print('AI Authoring UX 7.7 patch applied')
