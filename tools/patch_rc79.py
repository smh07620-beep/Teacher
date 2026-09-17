from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace(path,old,new,count=1):
    p=ROOT/path
    s=p.read_text(encoding='utf-8')
    if s.count(old)!=count:
        raise SystemExit(f'{path}: expected {count} matches, found {s.count(old)} for {old[:80]!r}')
    p.write_text(s.replace(old,new,count),encoding='utf-8')

# 1) Flatten the public homepage outer shell only; keep inner cards/hero intact.
replace(Path('static/portal-v56.css'),
".v56-shell{width:min(1380px,calc(100% - 36px));margin:18px auto 0;background:rgba(255,255,255,.92);border:1px solid #deedf4;border-radius:16px;box-shadow:0 18px 58px rgba(35,86,115,.13);overflow:hidden;backdrop-filter:blur(12px)}",
".v56-shell{width:100%;margin:0;background:transparent;border:0;border-radius:0;box-shadow:none;overflow:visible;backdrop-filter:none}")

# 2) Always collapse legacy qpanels after list presentation helpers run.
bank=ROOT/'static/admin-question-bank.js'
s=bank.read_text(encoding='utf-8')
needle="""  function renderQuizList78(){\n    const box=document.getElementById('admin-quiz-categories-list');if(!box)return;\n"""
insert="""  function collapseQuizPanels78(box=document.getElementById('admin-quiz-categories-list')){\n    box?.querySelectorAll('[id^=\"qpanel-\"]').forEach(panel=>panel.classList.add('hidden'));\n  }\n\n  function renderQuizList78(){\n    const box=document.getElementById('admin-quiz-categories-list');if(!box)return;\n"""
if s.count(needle)!=1: raise SystemExit('admin-question-bank.js renderQuizList78 anchor mismatch')
s=s.replace(needle,insert,1)
old="""    window.exposeQuestionDeleteActions(box);\n    updateQuizWorkspacePresentation();\n  }\n"""
new="""    window.exposeQuestionDeleteActions(box);\n    updateQuizWorkspacePresentation();\n    collapseQuizPanels78(box);\n    setTimeout(()=>collapseQuizPanels78(box),0);\n  }\n"""
if s.count(old)!=1: raise SystemExit('admin-question-bank.js presentation anchor mismatch')
s=s.replace(old,new,1)
bank.write_text(s,encoding='utf-8')

# 3) Make exam-container action cards explicit click owners instead of relying only on delegation.
studio=ROOT/'static/teacher-content-studio-71.js'
s=studio.read_text(encoding='utf-8')
for action in ('question','image','video','ai','questions','settings'):
    old=f'<button type="button" data-exam-action="{action}" data-exam-id="${{esc(catId)}}"'
    new=f'<button type="button" onclick="event.stopPropagation();window.teacherContentStudioExamAction?.(\'{action}\',\'${{esc(catId)}}\')" data-exam-action="{action}" data-exam-id="${{esc(catId)}}"'
    if s.count(old)!=1: raise SystemExit(f'studio action anchor mismatch: {action} ({s.count(old)})')
    s=s.replace(old,new,1)

export_anchor="""  window.openTeacherContentExam=async function(catId){openStudio();await renderExamContainer(catId);};\n"""
export_new="""  window.teacherContentStudioExamAction=(action,catId)=>runExamAction(action,catId);\n  window.openTeacherContentExam=async function(catId){openStudio();await renderExamContainer(catId);};\n"""
if s.count(export_anchor)!=1: raise SystemExit('studio export anchor mismatch')
s=s.replace(export_anchor,export_new,1)

# 4) Mount course/material hub first, then refresh in background instead of failing the whole container at 3.5s.
old="""      await timeout77(window.renderAdminCourseMaterialHub?.(true),3500,'整理課程與教材');\n      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher78MaterialHubPlaceholder='1';root.before(placeholder);materialHubMount.root=root;materialHubMount.placeholder=placeholder;\n      host.innerHTML=`<div class=\"mx-auto max-w-5xl\"><div class=\"mb-4 flex items-start justify-between gap-3 flex-wrap\"><div><button type=\"button\" data-studio-back class=\"text-sm font-bold text-slate-500\">← 返回建立首頁</button><h4 class=\"mt-2 text-xl font-black text-slate-950\">📚 教材與課程管理</h4><p class=\"mt-1 text-xs text-slate-500\">先選課程，再管理該課程的教材與考卷；未歸類內容只保留作為整理入口。</p></div>${canCourse()?'<button type=\"button\" data-studio-action=\"course\" class=\"rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white\">＋ 建立課程</button>':''}</div><div data-material-hub-host-78></div></div>`;\n      host.querySelector('[data-material-hub-host-78]')?.appendChild(root);\n"""
new="""      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher78MaterialHubPlaceholder='1';root.before(placeholder);materialHubMount.root=root;materialHubMount.placeholder=placeholder;\n      host.innerHTML=`<div class=\"mx-auto max-w-5xl\"><div class=\"mb-4 flex items-start justify-between gap-3 flex-wrap\"><div><button type=\"button\" data-studio-back class=\"text-sm font-bold text-slate-500\">← 返回建立首頁</button><h4 class=\"mt-2 text-xl font-black text-slate-950\">📚 教材與課程管理</h4><p class=\"mt-1 text-xs text-slate-500\">先選課程，再管理該課程的教材與考卷；未歸類內容只保留作為整理入口。</p></div>${canCourse()?'<button type=\"button\" data-studio-action=\"course\" class=\"rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white\">＋ 建立課程</button>':''}</div><div data-material-refresh-status-79 class=\"mb-3 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-xs text-teal-700\">正在背景更新課程與教材…</div><div data-material-hub-host-78></div></div>`;\n      host.querySelector('[data-material-hub-host-78]')?.appendChild(root);\n      const refreshStatus=host.querySelector('[data-material-refresh-status-79]');\n      timeout77(window.renderAdminCourseMaterialHub?.(false),8000,'更新課程與教材').then(()=>refreshStatus?.remove()).catch(error=>{if(refreshStatus){refreshStatus.className='mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700';refreshStatus.textContent=`⚠️ ${error.message}；目前畫面仍可使用，可稍後按更新重試。`;}});\n"""
if s.count(old)!=1: raise SystemExit(f'material manager block mismatch ({s.count(old)})')
s=s.replace(old,new,1)
studio.write_text(s,encoding='utf-8')

# Regression contract.
test=ROOT/'tests/test_rc79_container_runtime_regressions.py'
test.write_text('''from pathlib import Path\nimport subprocess\nimport unittest\n\nROOT=Path(__file__).resolve().parents[1]\n\nclass RC79ContainerRuntimeRegressions(unittest.TestCase):\n    def src(self,path): return (ROOT/path).read_text(encoding="utf-8")\n\n    def test_home_outer_surface_is_flat(self):\n        css=self.src("static/portal-v56.css")\n        self.assertIn(".v56-shell{width:100%;margin:0;background:transparent;border:0;border-radius:0;box-shadow:none",css)\n        self.assertNotIn(".v56-shell{width:min(1380px,calc(100% - 36px));margin:18px auto 0",css)\n\n    def test_quiz_list_recollapses_runtime_panels(self):\n        bank=self.src("static/admin-question-bank.js")\n        self.assertIn("function collapseQuizPanels78",bank)\n        self.assertIn("setTimeout(()=>collapseQuizPanels78(box),0)",bank)\n\n    def test_exam_container_cards_have_explicit_handlers(self):\n        studio=self.src("static/teacher-content-studio-71.js")\n        self.assertIn("window.teacherContentStudioExamAction=(action,catId)=>runExamAction(action,catId)",studio)\n        for action in ("question","image","video","ai","questions","settings"):\n            self.assertIn(f"window.teacherContentStudioExamAction?.('{action}'",studio)\n\n    def test_material_container_mounts_before_background_refresh(self):\n        studio=self.src("static/teacher-content-studio-71.js")\n        self.assertIn("data-material-refresh-status-79",studio)\n        self.assertIn("renderAdminCourseMaterialHub?.(false),8000",studio)\n        self.assertNotIn("renderAdminCourseMaterialHub?.(true),3500,'整理課程與教材'",studio)\n\n    def test_browser_js_syntax(self):\n        for asset in ("teacher-content-studio-71.js","admin-question-bank.js"):\n            r=subprocess.run(["node","--check",str(ROOT/"static"/asset)],capture_output=True,text=True)\n            self.assertEqual(r.returncode,0,r.stderr or r.stdout)\n\nif __name__=="__main__": unittest.main()\n''',encoding='utf-8')
print('RC79 patch applied')
