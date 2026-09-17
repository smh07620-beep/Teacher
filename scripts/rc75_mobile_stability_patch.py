from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:90]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) The canonical workspace router must never re-promote the hidden upload executor.
replace_once(
    "static/admin-workspace.js",
    """      document.getElementById('admin-course-workspace')?.classList.remove('hidden');
      document.getElementById('admin-material-workspace')?.classList.remove('hidden');
      document.getElementById('admin-material-advanced')?.classList.remove('hidden');
      // Storage/worker probes remain intentionally deferred until their panels open.
""",
    """      document.getElementById('admin-course-workspace')?.classList.remove('hidden');
      const materialExecutor = document.getElementById('admin-material-workspace');
      materialExecutor?.classList.add('hidden');
      materialExecutor?.setAttribute('aria-hidden', 'true');
      document.getElementById('admin-material-advanced')?.classList.remove('hidden');
      // RC 7.5 mobile stability: the canonical upload executor stays mounted but is never promoted into the daily workspace.
      // Storage/worker probes remain intentionally deferred until their panels open.
""",
)

# 2) Prevent first-paint flash before the convergence JS has executed.
replace_once(
    "static/system.html",
    '<section id="admin-material-workspace" class="bg-white border border-teal-200 rounded-2xl p-5 shadow-sm space-y-4">',
    '<section id="admin-material-workspace" class="hidden bg-white border border-teal-200 rounded-2xl p-5 shadow-sm space-y-4" aria-hidden="true">',
)

# 3) Give the canonical AI editor a stable mount point. The AI implementation itself stays in admin-ai-questions.js.
replace_once(
    "static/admin-question-bank.js",
    '''                  <section class="rounded-2xl border border-violet-200 bg-white overflow-hidden">
                      <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap">''',
    '''                  <section data-ai-question-studio="${c.id}" class="rounded-2xl border border-violet-200 bg-white overflow-hidden">
                      <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap">''',
)

# 4) Keep AI authoring inside the unified Studio by mounting the canonical AI DOM there.
replace_once(
    "static/teacher-content-studio-71.js",
    """  const studioId = 'teacher-content-studio-71';
  const launcherId = 'teacher-content-studio-launcher-71';
""",
    """  const studioId = 'teacher-content-studio-71';
  const launcherId = 'teacher-content-studio-launcher-71';
  const aiMount = {section:null, placeholder:null, catId:''};
""",
)

replace_once(
    "static/teacher-content-studio-71.js",
    """      const confirmQuestion = event.target.closest('[data-studio-question-confirm]');
      if(confirmQuestion) confirmQuestionPreset(confirmQuestion.dataset.preset || 'choice');
""",
    """      const confirmQuestion = event.target.closest('[data-studio-question-confirm]');
      if(confirmQuestion) confirmQuestionPreset(confirmQuestion.dataset.preset || 'choice');
      const confirmAi = event.target.closest('[data-studio-ai-confirm]');
      if(confirmAi) mountAiPanel(document.getElementById('teacher-studio-ai-exam-75')?.value || '');
""",
)

replace_once(
    "static/teacher-content-studio-71.js",
    """  function renderHome(){
    const body = document.getElementById('teacher-content-studio-body-71');
    if(body) body.innerHTML = baseBody();
  }
""",
    """  function renderHome(){
    restoreAiPanel();
    const body = document.getElementById('teacher-content-studio-body-71');
    if(body) body.innerHTML = baseBody();
  }
""",
)

replace_once(
    "static/teacher-content-studio-71.js",
    """  function closeStudio(){
    document.getElementById(studioId)?.classList.add('hidden');
    delete document.body.dataset.teacherContentStudioOpen;
  }
""",
    """  function closeStudio(){
    restoreAiPanel();
    document.getElementById(studioId)?.classList.add('hidden');
    delete document.body.dataset.teacherContentStudioOpen;
  }
""",
)

ai_functions = r'''
  function restoreAiPanel(){
    const section = aiMount.section;
    if(!section) return;
    const placeholder = aiMount.placeholder;
    const panel = document.getElementById(`qpanel-${aiMount.catId}`);
    if(placeholder?.isConnected) placeholder.replaceWith(section);
    else if(panel) panel.appendChild(section);
    else section.remove();
    aiMount.section = null;
    aiMount.placeholder = null;
    aiMount.catId = '';
  }

  async function chooseExamForAi(){
    restoreAiPanel();
    const host = document.getElementById('teacher-content-studio-body-71');
    if(!host) return;
    host.innerHTML = '<p class="text-sm text-slate-500">正在讀取可使用 AI 出題的考卷…</p>';
    try{
      const categories = await loadCategories();
      if(!categories.length){
        host.innerHTML = `<div class="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h4 class="font-black text-amber-950">目前組別還沒有考卷</h4><p class="mt-1 text-sm text-amber-800">AI 候選題必須先指定要加入的考卷。</p><div class="mt-4 flex gap-2"><button type="button" data-studio-action="exam" class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">建立考卷</button><button type="button" data-studio-back class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">返回</button></div></div>`;
        return;
      }
      host.innerHTML = `<div class="mx-auto max-w-2xl"><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回內容類型</button><div class="mt-4 rounded-2xl border border-violet-200 bg-white p-5"><div class="text-xs font-black tracking-wide text-violet-700">AI 輔助出題</div><h4 class="mt-1 text-lg font-black text-slate-900">先選擇要加入的考卷</h4><p class="mt-1 text-xs leading-5 text-slate-500">下一步仍留在「建立教學內容」視窗，直接使用既有 AI 教材出題工作室，不會跳離目前流程。</p><label class="block mt-4 text-sm font-bold text-slate-700">加入哪一份考卷？<select id="teacher-studio-ai-exam-75" class="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">${categories.map(c => `<option value="${esc(c.id)}">${esc(c.title || c.id)}</option>`).join('')}</select></label><div class="mt-5 flex flex-wrap justify-end gap-2"><button type="button" data-studio-back class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button type="button" data-studio-ai-confirm class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">下一步：AI 出題設定</button></div></div></div>`;
    }catch(error){
      host.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3"><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
    }
  }

  async function mountAiPanel(catId){
    if(!catId) return;
    const host = document.getElementById('teacher-content-studio-body-71');
    if(!host) return;
    const selectedScope = scope();
    restoreAiPanel();
    host.innerHTML = '<div class="rounded-2xl border border-violet-100 bg-violet-50 p-5 text-sm text-violet-700">正在準備 AI 教材出題工作室…</div>';
    try{
      await window.openAdminWorkspace?.('assessment');
      const area = document.getElementById('admin-quiz-area');
      const group = document.getElementById('admin-quiz-group');
      if(area) area.value = selectedScope.area;
      if(group) group.value = selectedScope.group;
      await window.renderAdminQuizCategories?.(true);
      const panel = document.getElementById(`qpanel-${catId}`);
      if(!panel) throw new Error('找不到指定考卷，請重新選擇。');
      if(panel.classList.contains('hidden')) await window.toggleQuizQuestionsPanel?.(catId);
      const section = panel.querySelector('[data-ai-question-studio]');
      if(!section) throw new Error('AI 出題工作室尚未載入，請重新開啟。');
      const placeholder = document.createElement('div');
      placeholder.hidden = true;
      placeholder.dataset.teacher75AiPlaceholder = String(catId);
      section.before(placeholder);
      aiMount.section = section;
      aiMount.placeholder = placeholder;
      aiMount.catId = String(catId);
      host.innerHTML = `<div class="mx-auto max-w-4xl"><div class="mb-4 flex items-start justify-between gap-3"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 重新選擇考卷</button><h4 class="mt-2 text-lg font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">AI 設定、產生候選題與人工審核都留在同一個建立流程。</p></div></div><div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      requestAnimationFrame(() => section.scrollIntoView({behavior:'smooth', block:'start'}));
    }catch(error){
      restoreAiPanel();
      host.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message || 'AI 出題工作室開啟失敗')}<div class="mt-3"><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
    }
  }

'''
replace_once(
    "static/teacher-content-studio-71.js",
    "  async function chooseExamForQuestion(preset){\n",
    ai_functions + "  async function chooseExamForQuestion(preset){\n",
)

replace_once(
    "static/teacher-content-studio-71.js",
    """    if(action === 'ai-question'){
      closeStudio();
      await window.openAdminWorkspace?.('assessment');
      window.assessment681Tab?.('ai');
      document.getElementById('assessment-681')?.scrollIntoView({behavior:'smooth', block:'start'});
      return;
    }
""",
    """    if(action === 'ai-question') return chooseExamForAi();
""",
)

# Focused contract test: locks the two user-observed regressions at their owners.
test = r'''import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class RcMobileWorkspaceStability75Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ROOT.joinpath('static/system.html').read_text(encoding='utf-8')
        cls.workspace = ROOT.joinpath('static/admin-workspace.js').read_text(encoding='utf-8')
        cls.studio = ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.bank = ROOT.joinpath('static/admin-question-bank.js').read_text(encoding='utf-8')

    def test_legacy_material_executor_never_flashes_visible(self):
        self.assertRegex(self.html, r'id="admin-material-workspace" class="hidden [^"]+" aria-hidden="true"')
        self.assertNotIn("document.getElementById('admin-material-workspace')?.classList.remove('hidden')", self.workspace)
        self.assertIn("materialExecutor?.classList.add('hidden')", self.workspace)
        self.assertIn("materialExecutor?.setAttribute('aria-hidden', 'true')", self.workspace)
        self.assertIn('canonical upload executor stays mounted but is never promoted', self.workspace)

    def test_ai_authoring_stays_inside_unified_studio(self):
        self.assertIn('data-ai-question-studio="${c.id}"', self.bank)
        for marker in ('chooseExamForAi', 'mountAiPanel', 'restoreAiPanel', 'data-studio-ai-confirm', 'data-teacher75-ai-host'):
            self.assertIn(marker, self.studio)
        self.assertIn("if(action === 'ai-question') return chooseExamForAi();", self.studio)
        self.assertNotIn("assessment681Tab?.('ai')", self.studio)
        self.assertIn('AI 設定、產生候選題與人工審核都留在同一個建立流程', self.studio)

    def test_modified_browser_javascript_syntax(self):
        for asset in ('admin-workspace.js', 'admin-question-bank.js', 'teacher-content-studio-71.js'):
            completed = subprocess.run(
                ['node', '--check', str(ROOT / 'static' / asset)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == '__main__':
    unittest.main()
'''
(ROOT / "tests/test_rc_mobile_workspace_stability_75.py").write_text(test, encoding="utf-8")

print("RC 7.5 mobile stability + in-Studio AI patch applied")
