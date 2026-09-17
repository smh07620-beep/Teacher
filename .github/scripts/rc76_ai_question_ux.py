from pathlib import Path


def replace_once(path, old, new):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if text.count(old)!=1:
        raise SystemExit(f'{path}: expected one match, got {text.count(old)}')
    p.write_text(text.replace(old,new),encoding='utf-8')

# AI stage 2 must not reopen the entire admin modal/course workspace before switching to assessment.
p='static/teacher-content-studio-71.js'
text=Path(p).read_text(encoding='utf-8')
old="""      await window.openAdminWorkspace?.('assessment');
      const area = document.getElementById('admin-quiz-area');"""
new="""      // Studio is already inside the authenticated admin modal. Reopening the modal first
      // routes through course/material loading and can leave mobile Safari waiting forever.
      if(typeof window.switchAdminWorkspace !== 'function') throw new Error('題庫工作區尚未載入，請重新開啟後台。');
      await Promise.race([
        window.switchAdminWorkspace('assessment', true),
        new Promise((_, reject) => setTimeout(() => reject(new Error('題庫載入逾時，請重新嘗試。')), 12000))
      ]);
      const area = document.getElementById('admin-quiz-area');"""
if text.count(old)!=1: raise SystemExit('studio: stage2 owner match failed')
text=text.replace(old,new)
old2="""      await window.renderAdminQuizCategories?.(true);
      const panel = document.getElementById(`qpanel-${catId}`);
      if(!panel) throw new Error('找不到指定考卷，請重新選擇。');
      if(panel.classList.contains('hidden')) await window.toggleQuizQuestionsPanel?.(catId);
      const section = panel.querySelector('[data-ai-question-studio]');"""
new2="""      await Promise.race([
        Promise.resolve(window.renderAdminQuizCategories?.(true)),
        new Promise((_, reject) => setTimeout(() => reject(new Error('考卷同步逾時，請重新嘗試。')), 12000))
      ]);
      const panel = document.getElementById(`qpanel-${catId}`);
      if(!panel) throw new Error('找不到指定考卷，請重新選擇。');
      if(panel.classList.contains('hidden')) await window.toggleQuizQuestionsPanel?.(catId);
      else {
        await Promise.allSettled([
          Promise.resolve(window.loadAiMaterialOptions?.(catId)),
          Promise.resolve(window.refreshAiQuestionStatus?.(catId))
        ]);
      }
      const section = panel.querySelector('[data-ai-question-studio]');"""
if text.count(old2)!=1: raise SystemExit('studio: panel load match failed')
text=text.replace(old2,new2)
old3="""      host.innerHTML = `<div class=\"mx-auto max-w-4xl\"><div class=\"mb-4 flex items-start justify-between gap-3\"><div><button type=\"button\" data-studio-back class=\"text-sm font-bold text-slate-500\">← 重新選擇考卷</button><h4 class=\"mt-2 text-lg font-black text-slate-950\">✨ AI 輔助出題</h4><p class=\"mt-1 text-xs text-slate-500\">AI 設定、產生候選題與人工審核都留在同一個建立流程。</p></div></div><div data-teacher75-ai-host></div></div>`;"""
new3="""      host.innerHTML = `<div class=\"mx-auto max-w-4xl\"><div class=\"mb-4\"><button type=\"button\" data-studio-back class=\"text-sm font-bold text-slate-500\">← 重新選擇考卷</button><div class=\"mt-3 grid grid-cols-3 gap-2 text-[11px] font-bold\"><div class=\"rounded-lg bg-slate-100 px-2 py-2 text-slate-500\">1 選考卷 ✓</div><div class=\"rounded-lg bg-violet-100 px-2 py-2 text-violet-800\">2 AI 出題設定</div><div class=\"rounded-lg bg-slate-100 px-2 py-2 text-slate-500\">3 審核匯入</div></div><h4 class=\"mt-4 text-lg font-black text-slate-950\">✨ AI 輔助出題</h4><p class=\"mt-1 text-xs text-slate-500\">快速模式只需選教材、題數、題型與難度；其他設定需要時再調整。產生後在同一頁審核再匯入。</p></div><div data-teacher75-ai-host></div></div>`;"""
if text.count(old3)!=1: raise SystemExit('studio: stage header match failed')
Path(p).write_text(text.replace(old3,new3),encoding='utf-8')

# Bulk controls stay quiet until at least one question is selected; remove duplicate always-visible actions.
p='static/admin-question-bank.js'; text=Path(p).read_text(encoding='utf-8')
old="""                          <button onclick=\"adminEditSelectedQuestions('${c.id}',false)\" class=\"text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold\">✏️ 編輯已選</button>
                          <button onclick=\"adminEditSelectedQuestions('${c.id}',true)\" class=\"text-[11px] bg-violet-700 hover:bg-violet-600 text-white px-3 py-1.5 rounded-lg font-bold\">📝 全選編輯</button>
                          <button onclick=\"adminSaveExpandedQuestionEdits('${c.id}')\" class=\"text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold\">💾 儲存展開編輯</button>
                          <span class=\"h-5 w-px bg-slate-300 hidden sm:block\"></span>
                          <button onclick=\"adminBulkSetQuestionTag('${c.id}')\" class=\"text-[11px] bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg\">🏷️ 批次分類</button>
                          <button onclick=\"adminBulkSetQuestionActive('${c.id}',true)\" class=\"text-[11px] bg-white border border-emerald-200 hover:bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg\">▶ 批次啟用</button>
                          <button onclick=\"adminBulkSetQuestionActive('${c.id}',false)\" class=\"text-[11px] bg-white border border-amber-200 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg\">⏸ 批次停用</button>
                          <button onclick=\"adminBulkDeleteQuestions('${c.id}')\" class=\"text-[11px] bg-white border border-slate-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700 px-3 py-1.5 rounded-lg\">更多：批次刪除</button>"""
new="""                          <span class=\"text-[11px] text-slate-400\">勾選題目後顯示批次工具</span>
                          <div id=\"qselection-actions-${c.id}\" class=\"hidden contents\">
                            <button onclick=\"adminEditSelectedQuestions('${c.id}',false)\" class=\"text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold\">✏️ 編輯已選</button>
                            <button onclick=\"adminBulkSetQuestionTag('${c.id}')\" class=\"text-[11px] bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg\">🏷️ 分類</button>
                            <button onclick=\"adminBulkSetQuestionActive('${c.id}',true)\" class=\"text-[11px] bg-white border border-emerald-200 hover:bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg\">▶ 啟用</button>
                            <button onclick=\"adminBulkSetQuestionActive('${c.id}',false)\" class=\"text-[11px] bg-white border border-amber-200 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg\">⏸ 停用</button>
                            <button onclick=\"adminBulkDeleteQuestions('${c.id}')\" class=\"text-[11px] bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-1.5 rounded-lg\">🗑️ 刪除</button>
                          </div>"""
if text.count(old)!=1: raise SystemExit('question bank: toolbar match failed')
text=text.replace(old,new)
oldsticky="""<div id=\"qlist-${c.id}\" class=\"space-y-2\"></div><div id=\"qsticky-save-${c.id}\" class=\"sticky bottom-2 z-20 mt-3 rounded-xl border border-teal-200 bg-white/95 backdrop-blur shadow-lg p-2.5 flex items-center justify-between gap-3\"><span class=\"text-[11px] text-slate-500\">批次編輯後可直接在此儲存，不必回頁首。</span><button onclick=\"adminSaveExpandedQuestionEdits('${c.id}')\" class=\"text-xs bg-teal-700 hover:bg-teal-600 text-white px-4 py-2 rounded-lg font-bold\">💾 儲存全部修改</button></div>"""
newsticky="""<div id=\"qlist-${c.id}\" class=\"space-y-2\"></div>"""
if text.count(oldsticky)!=1: raise SystemExit('question bank: sticky save match failed')
Path(p).write_text(text.replace(oldsticky,newsticky),encoding='utf-8')

# Regression gate for the user-observed blocker and mobile action convergence.
Path('tests/test_rc76_ai_question_mobile_ux.py').write_text('''from pathlib import Path\n\nROOT=Path(__file__).resolve().parents[1]\n\ndef source(path): return (ROOT/path).read_text(encoding="utf-8")\n\ndef test_ai_stage2_does_not_reopen_admin_modal():\n    s=source("static/teacher-content-studio-71.js")\n    assert "await window.openAdminWorkspace?.('assessment')" not in s\n    assert "window.switchAdminWorkspace('assessment', true)" in s\n    assert "題庫載入逾時" in s\n    assert "考卷同步逾時" in s\n    assert "1 選考卷 ✓" in s and "3 審核匯入" in s\n\ndef test_question_rows_use_one_primary_action_and_overflow_menu():\n    s=source("static/admin-question-editor-ui.js")\n    assert "✏️ 編輯</button><details" in s\n    assert "✏️ 快速編輯" not in s\n    assert "qselection-actions-" in s\n    assert "actions?.classList.toggle('hidden',selected.length===0)" in s\n    assert "if(cb) cb.checked=true" not in s\n\ndef test_bulk_toolbar_is_selection_driven_and_duplicate_sticky_save_is_gone():\n    s=source("static/admin-question-bank.js")\n    assert "勾選題目後顯示批次工具" in s\n    assert "qselection-actions-${c.id}" in s\n    assert "📝 全選編輯" not in s\n    assert "qsticky-save-" not in s\n''',encoding='utf-8')
