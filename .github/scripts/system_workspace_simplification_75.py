from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text.rstrip() + "\n", encoding="utf-8")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


# 1) Persistent course/material workspace: remove instructional STEP cards and stale ADMIN_KEY copy.
system_path = "static/system.html"
system = read(system_path)
if "RC75_WORKSPACE_SIMPLIFIED" not in system:
    anchor = system.index('id="admin-section-content"')
    start = system.index('<div class="grid md:grid-cols-4 gap-3">', anchor)
    end = system.index('<section id="admin-course-workspace"', start)
    removed = system[start:end]
    for marker in ("STEP 1", "STEP 2", "STEP 3", "STEP 4", "AI 候選題需人工確認後才匯入"):
        if marker not in removed:
            raise SystemExit(f"system.html step block missing marker: {marker}")
    system = system[:start] + '<!-- RC75_WORKSPACE_SIMPLIFIED: persistent teaching instructions removed; creation begins from Teacher Content Studio. -->\n                    ' + system[end:]
    system = replace_once(
        system,
        'ADMIN_KEY、MEGA 帳密、Google OAuth、Supabase 密碼與 Groq API Key 請只放 Render Environment Variables，不要寫入 GitHub。',
        'MEGA 帳密、Google OAuth、Supabase 密碼與 Groq API Key 請只放 Render Environment Variables；後台權限以登入 Session 與 RBAC 為準。',
        'system security copy',
    )
    write(system_path, system)


# 2) Teacher Content Studio: make course creation an explicit task and keep material executor off the daily surface.
studio_path = "static/teacher-content-studio-71.js"
studio = read(studio_path)
if "teacher75MaterialExecutorRoot" not in studio:
    studio = replace_once(
        studio,
        "  const canMaterial = () => has('material.manage') || has('course.manage');\n  const canOpen = () => canQuestion() || canMaterial();",
        "  const canMaterial = () => has('material.manage') || has('course.manage');\n  const canCourse = () => has('course.manage');\n  const canOpen = () => canQuestion() || canMaterial();",
        'studio course permission',
    )
    studio = replace_once(
        studio,
        "        <div class=\"grid sm:grid-cols-2 lg:grid-cols-3 gap-3\">\n          ${card('material','📄','上傳教材'",
        "        <div class=\"grid sm:grid-cols-2 lg:grid-cols-3 gap-3\">\n          ${canCourse()?card('course','🪄','建立課程','建立課程並視需要串接教材與考卷；進階欄位只在流程中出現。','violet'):''}\n          ${card('material','📄','上傳教材'",
        'studio course card',
    )
    studio = replace_once(
        studio,
        "    if(action === 'material') return openMaterialUpload('standard');",
        "    if(action === 'course'){\n      closeStudio();\n      await window.openAdminWorkspace?.('course-materials');\n      window.teacher75OpenCourseWizard?.();\n      return;\n    }\n    if(action === 'material') return openMaterialUpload('standard');",
        'studio course launch',
    )
    func_start = studio.index('  function consolidateMaterialWorkspace(){')
    func_end = studio.index('  function ensureLauncher(){', func_start)
    old_func = studio[func_start:func_end]
    for marker in ('教材處理與背景工作', '建立入口已統一', 'admin-pptx-upload-input'):
        if marker not in old_func:
            raise SystemExit(f"consolidateMaterialWorkspace missing marker: {marker}")
    new_func = '''  function consolidateMaterialWorkspace(){
    const root=document.getElementById('admin-material-workspace');
    if(!root) return;
    // RC 7.5: this DOM remains the canonical upload executor, but it is not a daily management surface.
    root.dataset.teacher75MaterialExecutorRoot='1';
    root.classList.add('hidden');
    root.setAttribute('aria-hidden','true');

    const fileInput=document.getElementById('admin-pptx-upload-input');
    hideMaterialExecutorNode(fileInput?.parentElement);
    hideMaterialExecutorNode(document.getElementById('admin-material-title')?.closest('.grid'));
    hideMaterialExecutorNode(document.getElementById('admin-atlas-fields'));
    hideMaterialExecutorNode(document.getElementById('admin-upload-btn')?.parentElement);

    const external=[...root.querySelectorAll('button')].find(button=>(button.getAttribute('onclick')||'').includes('openExternalMaterialDrawer'));
    hideMaterialExecutorNode(external);
  }

'''
    studio = studio[:func_start] + new_func + studio[func_end:]
    write(studio_path, studio)


# 3) Course Wizard: keep canonical implementation, hide persistent card until Studio explicitly opens it.
ux_path = "static/teacher-ux-convergence-72.js"
ux = read(ux_path)
if "teacher75OpenCourseWizard" not in ux:
    start = ux.index('  function compactLegacyCourseWizard(){')
    end = ux.index('  function getStartSelection(){', start)
    old = ux[start:end]
    for marker in ('快速建立整套課程', 'data-teacher72-course-wizard'):
        if marker not in old:
            raise SystemExit(f"course wizard convergence missing marker: {marker}")
    new = '''  function compactLegacyCourseWizard(){
    const existing=document.querySelector('[data-teacher72-course-wizard]');
    if(existing)return existing;
    const heading=[...document.querySelectorAll('h4')].find(node=>node.textContent.includes('快速建立整套課程'));
    if(!heading)return null;
    const card=heading.closest('.rounded-2xl')||heading.parentElement?.parentElement;
    if(!card)return null;
    card.dataset.teacher72Compact='1';
    const details=document.createElement('details');
    details.dataset.teacher72CourseWizard='1';
    details.className='hidden rounded-2xl border border-violet-200 bg-white shadow-sm';
    details.setAttribute('aria-hidden','true');
    const summary=document.createElement('summary');
    summary.className='cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3';
    summary.innerHTML='<span><span class="font-black text-slate-900">建立整套課程</span><span class="ml-2 text-xs text-slate-500">課程＋教材＋考卷</span></span><span class="text-xs font-bold text-violet-700">收合</span>';
    card.parentNode?.insertBefore(details,card);
    details.appendChild(summary);
    details.appendChild(card);
    card.classList.remove('rounded-2xl','shadow-sm');
    card.classList.add('border-0','shadow-none');
    details.addEventListener('toggle',()=>{
      if(!details.open&&details.dataset.teacher75Explicit==='1'){
        details.classList.add('hidden');
        details.setAttribute('aria-hidden','true');
        delete details.dataset.teacher75Explicit;
      }
    });
    return details;
  }

  function openCourseWizardFromStudio(){
    const details=compactLegacyCourseWizard();
    if(!details)return false;
    details.dataset.teacher75Explicit='1';
    details.classList.remove('hidden');
    details.removeAttribute('aria-hidden');
    details.open=true;
    requestAnimationFrame(()=>details.scrollIntoView({behavior:'smooth',block:'start'}));
    return true;
  }
  window.teacher75OpenCourseWizard=openCourseWizardFromStudio;

'''
    ux = ux[:start] + new + ux[end:]
    write(ux_path, ux)


# 4) System-admin-only advanced maintenance: move background jobs out of daily course/material page.
workspace_path = "static/workspace-shell-70.js"
workspace = read(workspace_path)
if "system-advanced-maintenance-75" not in workspace:
    insert_at = workspace.index('  function button(id, label, workspace) {')
    helper = '''  function ensureSystemAdvancedMaintenance(){
    if(!isSystemAdmin)return;
    const systemPanel=document.getElementById('admin-section-system');
    if(!systemPanel)return;
    let details=document.getElementById('system-advanced-maintenance-75');
    if(!details){
      details=document.createElement('details');
      details.id='system-advanced-maintenance-75';
      details.className='bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden';
      details.innerHTML=`<summary class="cursor-pointer list-none p-5 flex items-center justify-between gap-3"><div><h4 class="font-black text-slate-950">🧰 進階維護</h4><p class="mt-1 text-xs text-slate-500">只在儲存搬移或背景工作異常時使用；日常教學不需要展開。</p></div><span class="text-xs font-bold text-slate-500">需要時展開</span></summary><div class="border-t border-slate-100 p-5 space-y-4"><div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">僅 system_admin 顯示。教材建立請使用「＋ 建立教學內容」；這裡只保留高風險維運工具。</div><div class="flex flex-wrap gap-2"><button id="system75-refresh-status" type="button" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold">🔄 重新檢查系統狀態</button><button id="system75-migrate-mega" type="button" class="rounded-xl bg-fuchsia-700 px-3 py-2 text-xs font-bold text-white">☁️ 搬移既有教材到 MEGA</button><button id="system75-migrate-r2" type="button" class="rounded-xl border border-cyan-300 bg-white px-3 py-2 text-xs font-bold text-cyan-800">☁️ R2 舊備援搬移</button></div><div data-system75-jobs></div></div>`;
      systemPanel.appendChild(details);
      details.querySelector('#system75-refresh-status').onclick=()=>window.renderAdminSystemStatus?.(true);
      details.querySelector('#system75-migrate-mega').onclick=async()=>{await window.migrateMaterialsToMega?.();await window.renderAdminSystemStatus?.(true);};
      details.querySelector('#system75-migrate-r2').onclick=async()=>{await window.migrateLocalMaterialsToR2?.();await window.renderAdminSystemStatus?.(true);};
    }
    const jobs=document.getElementById('admin-material-jobs-panel');
    const host=details.querySelector('[data-system75-jobs]');
    if(jobs&&host&&jobs.parentElement!==host){
      jobs.classList.remove('hidden');
      jobs.removeAttribute('aria-hidden');
      host.appendChild(jobs);
    }
  }

'''
    workspace = workspace[:insert_at] + helper + workspace[insert_at:]
    workspace = replace_once(
        workspace,
        "    if (show) {\n      moveMaintenanceCard();\n      if (isSystemAdmin) buildSystemNavigation();",
        "    if (show) {\n      moveMaintenanceCard();\n      ensureSystemAdvancedMaintenance();\n      if (isSystemAdmin) buildSystemNavigation();",
        'workspace modal maintenance mount',
    )
    workspace = replace_once(
        workspace,
        "  buildSystemNavigation();\n  addEducationMaintenanceNavigation();",
        "  ensureSystemAdvancedMaintenance();\n  buildSystemNavigation();\n  addEducationMaintenanceNavigation();",
        'workspace initial maintenance mount',
    )
    write(workspace_path, workspace)


# 5) Regression gate for the simplified responsibility split.
test_path = ROOT / "tests/test_system_workspace_simplification_75.py"
test_path.write_text('''from pathlib import Path\nimport unittest\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass SystemWorkspaceSimplification75Tests(unittest.TestCase):\n    def source(self, path):\n        return ROOT.joinpath(path).read_text(encoding="utf-8")\n\n    def test_persistent_step_tutorial_is_removed(self):\n        html = self.source("static/system.html")\n        self.assertIn("RC75_WORKSPACE_SIMPLIFIED", html)\n        for marker in ("STEP 1", "STEP 2", "STEP 3", "STEP 4", "AI 候選題需人工確認後才匯入"):\n            self.assertNotIn(marker, html)\n\n    def test_course_creation_is_explicitly_routed_from_studio(self):\n        studio = self.source("static/teacher-content-studio-71.js")\n        ux = self.source("static/teacher-ux-convergence-72.js")\n        self.assertIn("const canCourse", studio)\n        self.assertIn("card('course'", studio)\n        self.assertIn("teacher75OpenCourseWizard", studio)\n        self.assertIn("teacher75OpenCourseWizard", ux)\n        self.assertIn("details.className='hidden", ux)\n\n    def test_material_executor_is_not_a_daily_surface(self):\n        studio = self.source("static/teacher-content-studio-71.js")\n        self.assertIn("teacher75MaterialExecutorRoot", studio)\n        self.assertNotIn("教材處理與背景工作", studio)\n        self.assertNotIn("建立入口已統一", studio)\n\n    def test_advanced_maintenance_is_system_admin_only_and_collapsed(self):\n        shell = self.source("static/workspace-shell-70.js")\n        self.assertIn("system-advanced-maintenance-75", shell)\n        self.assertIn("if(!isSystemAdmin)return", shell)\n        self.assertIn("admin-material-jobs-panel", shell)\n        self.assertIn("migrateMaterialsToMega", shell)\n        self.assertIn("migrateLocalMaterialsToR2", shell)\n\n    def test_session_rbac_copy_replaces_admin_key_guidance(self):\n        html = self.source("static/system.html")\n        self.assertNotIn("ADMIN_KEY、MEGA", html)\n        self.assertIn("後台權限以登入 Session 與 RBAC 為準", html)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")


# 6) Living architecture note.
doc_path = "ARCHITECTURE_FINAL_CONVERGENCE.md"
doc = read(doc_path)
marker = "## RC 7.5 workspace simplification"
if marker not in doc:
    doc += '''\n\n## RC 7.5 workspace simplification\n\n- `課程＋教材` 日常畫面不再顯示 STEP 1–4 教學卡；建立動作由 `＋ 建立教學內容` 統一承接。\n- Course Wizard 仍是 canonical course bundle owner，但預設不佔據管理畫面；只有從 Studio 選擇「建立課程」才顯示。\n- `admin-material-workspace` 保留為 hidden canonical upload executor，不再同時扮演日常維護 UI。\n- MEGA/R2 搬移與背景 Worker 狀態移到 `system_admin` 專用、預設收合的「進階維護」；一般教學角色看不到。\n- `getAdminKey()` compatibility seam 與 DOCX fallback state 本輪不變。\n'''
    write(doc_path, doc)

print("RC 7.5 workspace simplification patch applied")
