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

# 1) Give the canonical AI section a stable mount contract and simplify bulk actions.
path = 'static/admin-question-bank.js'
text = read(path)
text = replace_once(
    text,
    '<section class="rounded-2xl border border-violet-200 bg-white overflow-hidden">\n                      <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white',
    '<section data-ai-question-studio="${c.id}" class="rounded-2xl border border-violet-200 bg-white overflow-hidden">\n                      <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white',
    'AI studio mount marker',
)
old_toolbar = '''<div id="qtoolbar-${c.id}" class="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 flex items-center gap-2 flex-wrap">
                          <label class="text-xs font-bold text-slate-700 inline-flex items-center gap-1.5"><input id="qselect-all-${c.id}" type="checkbox" onchange="adminSelectAllQuestions('${c.id}',this.checked)" class="rounded"> 全選</label>
                          <button onclick="adminEditSelectedQuestions('${c.id}',false)" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold">✏️ 編輯已選</button>
                          <button onclick="adminEditSelectedQuestions('${c.id}',true)" class="text-[11px] bg-violet-700 hover:bg-violet-600 text-white px-3 py-1.5 rounded-lg font-bold">📝 全選編輯</button>
                          <button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存展開編輯</button>
                          <span class="h-5 w-px bg-slate-300 hidden sm:block"></span>
                          <button onclick="adminBulkSetQuestionTag('${c.id}')" class="text-[11px] bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg">🏷️ 批次分類</button>
                          <button onclick="adminBulkSetQuestionActive('${c.id}',true)" class="text-[11px] bg-white border border-emerald-200 hover:bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg">▶ 批次啟用</button>
                          <button onclick="adminBulkSetQuestionActive('${c.id}',false)" class="text-[11px] bg-white border border-amber-200 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg">⏸ 批次停用</button>
                          <button onclick="adminBulkDeleteQuestions('${c.id}')" class="text-[11px] bg-white border border-slate-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700 px-3 py-1.5 rounded-lg">更多：批次刪除</button>
                          <span id="qbulk-progress-${c.id}" class="text-[11px] text-slate-500"></span>
                      </div>'''
new_toolbar = '''<div id="qtoolbar-${c.id}" class="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 flex items-center gap-2 flex-wrap">
                          <label class="text-xs font-bold text-slate-700 inline-flex items-center gap-1.5"><input id="qselect-all-${c.id}" type="checkbox" onchange="adminSelectAllQuestions('${c.id}',this.checked)" class="rounded"> 全選</label>
                          <span class="text-[11px] text-slate-400">勾選題目後顯示批次操作</span>
                          <div id="qbulk-actions-${c.id}" class="hidden flex items-center gap-2 flex-wrap">
                              <button onclick="adminEditSelectedQuestions('${c.id}',false)" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold">✏️ 編輯已選</button>
                              <button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存修改</button>
                              <details class="relative"><summary class="list-none cursor-pointer text-[11px] bg-white border border-slate-300 text-slate-700 px-3 py-1.5 rounded-lg font-bold">⋯ 批次操作</summary><div class="absolute right-0 z-40 mt-1 w-40 rounded-xl border border-slate-200 bg-white p-2 shadow-xl space-y-1"><button onclick="adminBulkSetQuestionTag('${c.id}')" class="w-full text-left text-[11px] hover:bg-slate-50 px-2 py-1.5 rounded-lg">🏷️ 分類</button><button onclick="adminBulkSetQuestionActive('${c.id}',true)" class="w-full text-left text-[11px] hover:bg-emerald-50 text-emerald-700 px-2 py-1.5 rounded-lg">▶ 啟用</button><button onclick="adminBulkSetQuestionActive('${c.id}',false)" class="w-full text-left text-[11px] hover:bg-amber-50 text-amber-700 px-2 py-1.5 rounded-lg">⏸ 停用</button><button onclick="adminBulkDeleteQuestions('${c.id}')" class="w-full text-left text-[11px] hover:bg-rose-50 text-rose-700 px-2 py-1.5 rounded-lg">🗑️ 刪除</button></div></details>
                          </div>
                          <span id="qbulk-progress-${c.id}" class="text-[11px] text-slate-500"></span>
                      </div>'''
text = replace_once(text, old_toolbar, new_toolbar, 'question bulk toolbar')
write(path, text)

# 2) Make each question card mobile-safe and collapse destructive/state actions into one menu.
path = 'static/admin-question-editor-ui.js'
text = read(path)
pattern = re.compile(r"  window\.adminQuestionRowHTML = function\(q,i,catId\)\{.*?\n  \};\n\n  window\.adminSelectedQuestionIds", re.S)
match = pattern.search(text)
assert match, 'adminQuestionRowHTML block not found'
new_row = '''  window.adminQuestionRowHTML = function(q,i,catId){
    return `<div id="qrow-${q.id}" class="border ${q.active===false?'border-amber-200 bg-amber-50/50':'border-slate-200 bg-white'} rounded-xl p-3 overflow-visible">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div class="w-full min-w-0 flex-1 text-xs flex items-start gap-2.5">
          <input type="checkbox" class="qselect-${catId} mt-1 rounded shrink-0" data-qid="${q.id}" onchange="adminUpdateQuestionSelection('${catId}')">
          <div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="font-bold text-slate-800 break-words">${i+1}. ${escapeHtml(q.question)}</span><span class="text-[10px] px-2 py-0.5 rounded-full ${q.active===false?'bg-amber-100 text-amber-800':'bg-emerald-50 text-emerald-700'}">${q.active===false?'停用':'啟用'}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${questionTypeLabel(q.questionType||'choice')}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${({basic:'基礎',standard:'一般',advanced:'進階'})[q.difficulty||'standard']||'一般'}</span></div><div class="text-slate-500 mt-1 break-words">${window.adminAnswerSummary(q)}${q.tag?' · 分類：'+escapeHtml(q.tag):''}</div></div>
        </div>
        <div class="w-full sm:w-auto flex items-center justify-end gap-2 shrink-0">
          <button onclick="adminToggleInlineQuestionEditor('${q.id}','${catId}',true)" class="text-[11px] bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-2 rounded-lg font-bold">✏️ 編輯</button>
          <details class="relative"><summary class="list-none cursor-pointer text-lg leading-none bg-white border border-slate-300 text-slate-600 px-3 py-1.5 rounded-lg" aria-label="更多題目操作">⋯</summary><div class="absolute right-0 z-40 mt-1 w-36 rounded-xl border border-slate-200 bg-white p-2 shadow-xl space-y-1"><button onclick="adminToggleQuizQuestion('${q.id}','${catId}',${q.active===false?'true':'false'})" class="w-full text-left text-[11px] ${q.active===false?'text-emerald-700 hover:bg-emerald-50':'text-amber-700 hover:bg-amber-50'} px-2 py-2 rounded-lg">${q.active===false?'▶ 啟用':'⏸ 停用'}</button><button onclick="adminDeleteQuizQuestion('${q.id}','${catId}')" class="w-full text-left text-[11px] text-rose-700 hover:bg-rose-50 px-2 py-2 rounded-lg">🗑️ 刪除</button></div></details>
        </div>
      </div>${window.adminQuestionEditFormHTML(q,catId)}
    </div>`;
  };

  window.adminSelectedQuestionIds'''
text = text[:match.start()] + new_row + text[match.end():]
old_update = '''    const badge=document.getElementById(`qselected-${catId}`);
    if(badge) badge.textContent=`已選 ${selected.length} 題`;
    const master=document.getElementById(`qselect-all-${catId}`);'''
new_update = '''    const badge=document.getElementById(`qselected-${catId}`);
    if(badge) badge.textContent=`已選 ${selected.length} 題`;
    document.getElementById(`qbulk-actions-${catId}`)?.classList.toggle('hidden',selected.length===0);
    const master=document.getElementById(`qselect-all-${catId}`);'''
text = replace_once(text, old_update, new_update, 'selection action visibility')
write(path, text)

# 3) Evolve Teacher Content Studio AI orchestration without taking over the AI API owner.
path = 'static/teacher-content-studio-71.js'
text = read(path)
anchor = '  async function chooseExamForAi(){\n'
assert anchor in text, 'AI chooser anchor missing'
helpers = r'''  const AI_PRESETS_76 = {
    auto: {label:'自動均衡', type:'mixed_all', count:5, difficulty:'standard', strategy:'auto', focus:'依教材重點自動配置單選、多選、填空與問答題。'},
    newcomer: {label:'新人基礎考核', type:'mixed_choice_multi', count:10, difficulty:'basic', strategy:'balanced', focus:'以基礎概念、流程與常見注意事項為主；單選題為主，多選題少量，避免過度刁鑽。'},
    pgy: {label:'PGY 核心能力', type:'mixed_all', count:10, difficulty:'standard', strategy:'balanced', focus:'涵蓋核心知識、操作判斷、臨床情境與反思；混合單選、多選、填空與問答。'},
    case: {label:'案例判讀', type:'mixed', count:5, difficulty:'advanced', strategy:'scenario', focus:'以案例資訊整合、判讀依據與下一步處置為主；情境單選與問答混合。'},
    quality: {label:'品質管理／異常處理', type:'mixed_all', count:10, difficulty:'standard', strategy:'safety', focus:'聚焦 QC、異常辨識、故障排除、通報與病人安全；混合單選、多選與問答。'},
    advanced: {label:'進階組內訓練', type:'mixed_all', count:10, difficulty:'advanced', strategy:'scenario', focus:'提高多步推理與情境整合比例，增加多選與問答，避免只考記憶。'},
    image: {label:'圖片判讀', type:'choice', count:5, difficulty:'standard', strategy:'recognition', focus:'優先根據圖片／Atlas 視覺證據出題，要求辨識特徵與判讀依據。'},
    video: {label:'影片互動', type:'video_mixed', count:5, difficulty:'standard', strategy:'workflow', focus:'依影片流程與關鍵操作時間點設計互動題，混合選擇、填空與問答。'},
  };

  function setAiControl76(catId, name, value){
    const el=document.getElementById(`ai-${name}-${catId}`); if(!el) return false;
    if(el.tagName==='SELECT' && ![...el.options].some(o=>String(o.value)===String(value))){
      const option=document.createElement('option'); option.value=String(value); option.textContent=String(value); el.appendChild(option);
    }
    el.value=String(value); el.dispatchEvent(new Event('change',{bubbles:true})); return true;
  }

  function applyAiPreset76(catId,key){
    const preset=AI_PRESETS_76[key]||AI_PRESETS_76.auto;
    setAiControl76(catId,'type',preset.type); setAiControl76(catId,'count',preset.count); setAiControl76(catId,'difficulty',preset.difficulty); setAiControl76(catId,'strategy',preset.strategy);
    const focus=document.getElementById(`ai-focus-${catId}`); if(focus) focus.value=preset.focus;
    const note=document.querySelector(`[data-ai-preset-note-76="${CSS.escape(String(catId))}"]`); if(note) note.textContent=`${preset.label}：${preset.focus}`;
    const custom=document.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`); custom?.classList.add('hidden');
  }

  function applyAiCustomMix76(catId){
    const root=document.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`); if(!root) return;
    const counts={choice:0,multi:0,fill:0,essay:0};
    Object.keys(counts).forEach(type=>{counts[type]=Math.max(0,Number(root.querySelector(`[data-mix-type="${type}"]`)?.value||0));});
    const active=Object.entries(counts).filter(([,n])=>n>0),total=active.reduce((sum,[,n])=>sum+n,0);
    if(!total){alert('請至少設定一種題型的題數');return;}
    let type='mixed_all';
    if(active.length===1) type=active[0][0];
    else if(active.every(([t])=>['choice','multi'].includes(t))) type='mixed_choice_multi';
    else if(active.every(([t])=>['choice','essay'].includes(t))) type='mixed';
    setAiControl76(catId,'type',type); setAiControl76(catId,'count',total);
    const labels={choice:'單選',multi:'多選',fill:'填空',essay:'問答'};
    const request=active.map(([t,n])=>`${labels[t]} ${n} 題`).join('、');
    const focus=document.getElementById(`ai-focus-${catId}`); if(focus) focus.value=`[自訂題型配置] 目標共 ${total} 題：${request}。請盡量嚴格依此配置產生，題目內容仍須完全根據所選教材。`;
    const note=document.querySelector(`[data-ai-preset-note-76="${CSS.escape(String(catId))}"]`); if(note) note.textContent=`自訂混搭：${request}（共 ${total} 題）`;
  }

  function aiPresetPanel76(catId){
    return `<section data-ai-ux-76 class="mb-4 rounded-2xl border border-violet-200 bg-violet-50/50 p-4"><div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black tracking-wide text-violet-700">STEP 2 / 3 · 出題策略</div><h5 class="mt-1 font-black text-slate-900">依教學需求自動混搭題型</h5><p class="mt-1 text-xs text-slate-500">先選用途快速套用；需要精準配置時再使用自訂混搭。</p></div><span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-violet-700 border border-violet-100">產生後進入 STEP 3 審核</span></div><div class="mt-3 grid sm:grid-cols-[1fr_auto] gap-2"><select data-ai-preset-select-76 class="w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm"><option value="auto">✨ 自動均衡</option><option value="newcomer">🌱 新人基礎考核</option><option value="pgy">🎯 PGY 核心能力</option><option value="case">🧩 案例判讀</option><option value="quality">🛡️ 品質管理／異常處理</option><option value="advanced">🧠 進階組內訓練</option><option value="image">🖼️ 圖片判讀</option><option value="video">🎬 影片互動</option><option value="custom">⚙️ 自訂混搭</option></select><button type="button" data-ai-apply-preset-76 class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">套用</button></div><p data-ai-preset-note-76="${esc(catId)}" class="mt-2 text-[11px] leading-5 text-violet-700">自動均衡：系統依教材重點配置題型。</p><div data-ai-custom-mix-76="${esc(catId)}" class="hidden mt-3 rounded-xl border border-violet-100 bg-white p-3"><div class="grid grid-cols-2 sm:grid-cols-4 gap-2">${[['choice','單選',4],['multi','多選',2],['fill','填空',2],['essay','問答',2]].map(([t,l,n])=>`<label class="text-xs font-bold text-slate-600">${l}<input data-mix-type="${t}" type="number" min="0" max="30" value="${n}" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"></label>`).join('')}</div><button type="button" data-ai-apply-custom-76 class="mt-3 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white">套用自訂題型配置</button><p class="mt-2 text-[10px] leading-4 text-slate-400">自訂混搭會沿用同一支 AI 出題服務，以總題數＋明確配置要求產生候選題；教師仍需在匯入前審核。</p></div></section>`;
  }

  async function waitForAiSection76(catId,timeout=6500){
    const started=Date.now();
    while(Date.now()-started<timeout){
      const panel=document.getElementById(`qpanel-${catId}`); const section=panel?.querySelector('[data-ai-question-studio]');
      if(section) return section;
      await new Promise(resolve=>setTimeout(resolve,120));
    }
    return null;
  }

'''
text = text.replace(anchor, helpers + anchor, 1)
# Mark chooser as step 1.
text = text.replace('<div class="text-xs font-black tracking-wide text-violet-700">AI 輔助出題</div><h4', '<div class="text-xs font-black tracking-wide text-violet-700">STEP 1 / 3 · 目標考卷</div><h4', 1)
# Replace mount section lookup with bounded wait and add retry-capable error.
old_lookup = '''      const section = panel.querySelector('[data-ai-question-studio]');
      if(!section) throw new Error('AI 出題工作室尚未載入，請重新開啟。');'''
new_lookup = '''      let section = panel.querySelector('[data-ai-question-studio]');
      if(!section) section = await waitForAiSection76(catId);
      if(!section) throw new Error('AI 出題工作室載入逾時，請按「重新嘗試」。');'''
text = replace_once(text, old_lookup, new_lookup, 'bounded AI mount wait')
old_host = '''      host.innerHTML = `<div class="mx-auto max-w-4xl"><div class="mb-4 flex items-start justify-between gap-3"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 重新選擇考卷</button><h4 class="mt-2 text-lg font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">AI 設定、產生候選題與人工審核都留在同一個建立流程。</p></div></div><div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      requestAnimationFrame(() => section.scrollIntoView({behavior:'smooth', block:'start'}));'''
new_host = '''      host.innerHTML = `<div class="mx-auto max-w-4xl"><div class="mb-4 flex items-start justify-between gap-3"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 重新選擇考卷</button><h4 class="mt-2 text-lg font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">AI 設定、產生候選題與人工審核都留在同一個建立流程。</p></div></div>${aiPresetPanel76(catId)}<div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      const presetSelect=host.querySelector('[data-ai-preset-select-76]');
      const presetButton=host.querySelector('[data-ai-apply-preset-76]');
      const customBox=host.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`);
      presetSelect?.addEventListener('change',()=>customBox?.classList.toggle('hidden',presetSelect.value!=='custom'));
      presetButton?.addEventListener('click',()=>{if(presetSelect?.value==='custom'){customBox?.classList.remove('hidden');return;}applyAiPreset76(catId,presetSelect?.value||'auto');});
      host.querySelector('[data-ai-apply-custom-76]')?.addEventListener('click',()=>applyAiCustomMix76(catId));
      applyAiPreset76(catId,'auto');
      requestAnimationFrame(() => section.scrollIntoView({behavior:'smooth', block:'start'}));'''
text = replace_once(text, old_host, new_host, 'AI preset host')
old_catch = '''      host.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message || 'AI 出題工作室開啟失敗')}<div class="mt-3"><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;'''
new_catch = '''      host.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message || 'AI 出題工作室開啟失敗')}<div class="mt-3 flex gap-2 flex-wrap"><button type="button" data-ai-retry-76 class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
      host.querySelector('[data-ai-retry-76]')?.addEventListener('click',()=>mountAiPanel(catId));'''
text = replace_once(text, old_catch, new_catch, 'AI retry state')
write(path, text)

# 4) Focused regression contract.
test = r'''from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AiAuthoringUxConvergence76Tests(unittest.TestCase):
    def test_ai_mount_has_stable_contract_and_bounded_retry(self):
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        self.assertIn('data-ai-question-studio="${c.id}"', bank)
        self.assertIn('waitForAiSection76', studio)
        self.assertIn('data-ai-retry-76', studio)
        self.assertNotIn("assessment681Tab?.('ai')", studio)

    def test_ai_presets_and_custom_mix_are_orchestration_only(self):
        studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        for label in ('新人基礎考核','PGY 核心能力','案例判讀','品質管理／異常處理','進階組內訓練','圖片判讀','影片互動','自訂混搭'):
            self.assertIn(label, studio)
        for token in ('mixed_all','mixed_choice_multi','video_mixed','[自訂題型配置]','data-mix-type="choice"','data-mix-type="essay"'):
            self.assertIn(token, studio)
        self.assertNotIn("fetch('/api/ai-questions/generate'", studio)
        ai = ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')
        self.assertIn("fetch('/api/ai-questions/generate'", ai)

    def test_mobile_question_actions_are_collapsed(self):
        editor = ROOT.joinpath('static/admin-question-editor-ui.js').read_text(encoding='utf-8')
        bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')
        self.assertIn('flex flex-col sm:flex-row', editor)
        self.assertIn('aria-label="更多題目操作"', editor)
        self.assertIn('✏️ 編輯', editor)
        self.assertIn('qbulk-actions-${c.id}', bank)
        self.assertIn('勾選題目後顯示批次操作', bank)
        self.assertIn("classList.toggle('hidden',selected.length===0)", editor)
        self.assertNotIn('📝 全選編輯', bank)


if __name__ == '__main__':
    unittest.main()
'''
write('tests/test_ai_authoring_ux_convergence_76.py', test)

print('AI Authoring UX 7.6 patch applied')
