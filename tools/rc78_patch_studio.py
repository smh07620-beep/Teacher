from pathlib import Path
p=Path('static/teacher-content-studio-71.js')
s=p.read_text(encoding='utf-8')
s=s.replace("  const courseMount = {root:null, placeholder:null};","  const courseMount = {root:null, placeholder:null};\n  const materialHubMount = {root:null, placeholder:null};",1)
old='''    const materialCards = canMaterial() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📚 教材與課程</h4><p class="text-xs text-slate-500 mt-1">課程與教材從同一建立流程開始。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${canCourse()?card('course','🪄','建立課程','在此完成課程、教材與考卷串接，不離開建立視窗。','violet'):''}
          ${card('material','📄','上傳教材','PDF、PPTX、DOCX、圖片等檔案，使用統一建立流程。','teal')}
          ${card('video-material','🎥','上傳影音教材','影片與影音檔也從同一建立入口開始。','teal')}
          ${card('external','🔗','外部影音／連結','建立 YouTube、Shorts 或其他支援的外部教學連結。','sky')}
          ${card('atlas','🔬','顯微鏡／血球圖譜','建立顯微鏡、血球、尿液沉渣或菌落圖譜。','emerald')}
        </div>
      </section>` : '';'''
new='''    const materialCards = canMaterial() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📚 教材與課程</h4><p class="text-xs text-slate-500 mt-1">先進入課程容器，再管理教材、影音、圖譜與對應考卷。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('materials-manager','📚','教材與課程管理','管理既有課程與教材；新增內容先從課程開始，避免未歸類教材持續增加。','teal')}
        </div>
      </section>` : '';'''
assert s.count(old)==1
s=s.replace(old,new,1)
s=s.replace('''  function renderHome(){
    restoreAiPanel();
    restoreCourseWizard();''','''  function renderHome(){
    restoreAiPanel();
    restoreCourseWizard();
    restoreMaterialHub();''',1)
s=s.replace('''  function closeStudio(){
    restoreAiPanel();
    restoreCourseWizard();''','''  function closeStudio(){
    restoreAiPanel();
    restoreCourseWizard();
    restoreMaterialHub();''',1)
insert_at=s.index('  function restoreCourseWizard(){')
material='''  function restoreMaterialHub(){
    if(!materialHubMount.root)return;
    if(materialHubMount.placeholder?.isConnected)materialHubMount.placeholder.replaceWith(materialHubMount.root);
    else materialHubMount.root.remove();
    materialHubMount.root=null; materialHubMount.placeholder=null;
  }

  async function mountMaterialManagerInStudio(){
    restoreAiPanel();restoreCourseWizard();restoreMaterialHub();
    const host=document.getElementById('teacher-content-studio-body-71');if(!host)return;
    host.innerHTML='<div class="rounded-2xl border border-teal-100 bg-teal-50 p-5 text-sm text-teal-700">正在整理課程與教材…</div>';
    try{
      let root=document.getElementById('admin-course-material-hub');
      if(!root){await timeout77(window.openAdminWorkspace?.('course-materials'),2200,'開啟教材與課程管理');root=await waitFor77('#admin-course-material-hub',2400);}
      if(!root)throw new Error('教材與課程管理尚未載入，請重新嘗試。');
      await timeout77(window.renderAdminCourseMaterialHub?.(true),3500,'整理課程與教材');
      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher78MaterialHubPlaceholder='1';root.before(placeholder);materialHubMount.root=root;materialHubMount.placeholder=placeholder;
      host.innerHTML=`<div class="mx-auto max-w-5xl"><div class="mb-4 flex items-start justify-between gap-3 flex-wrap"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回建立首頁</button><h4 class="mt-2 text-xl font-black text-slate-950">📚 教材與課程管理</h4><p class="mt-1 text-xs text-slate-500">先選課程，再管理該課程的教材與考卷；未歸類內容只保留作為整理入口。</p></div>${canCourse()?'<button type="button" data-studio-action="course" class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">＋ 建立課程</button>':''}</div><div data-material-hub-host-78></div></div>`;
      host.querySelector('[data-material-hub-host-78]')?.appendChild(root);
    }catch(error){restoreMaterialHub();host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3 flex gap-2"><button type="button" data-studio-action="materials-manager" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;}
  }

'''
s=s[:insert_at]+material+s[insert_at:]
s=s.replace('''  async function mountCourseWizardInStudio(){
    restoreAiPanel(); restoreCourseWizard();''','''  async function mountCourseWizardInStudio(){
    restoreAiPanel(); restoreCourseWizard(); restoreMaterialHub();''',1)
s=s.replace("    if(action==='course')return mountCourseWizardInStudio();","    if(action==='course')return mountCourseWizardInStudio();\n    if(action==='materials-manager')return mountMaterialManagerInStudio();",1)
anchor='  function hideMaterialExecutorNode(node){'
assert s.count(anchor)==1
s=s.replace(anchor,"  window.openTeacherContentExam=async function(catId){openStudio();await renderExamContainer(catId);};\n\n"+anchor,1)
p.write_text(s,encoding='utf-8')
