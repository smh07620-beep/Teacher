/* Teacher 10/14 media workspace: keep guidance available without occupying the main work surface. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const hasTeachingRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!hasTeachingRole) return;

  function setPanelOpen(button, panel, open) {
    const expanded = Boolean(open);
    panel.hidden = !expanded;
    if (expanded) panel.style.removeProperty('display');
    else panel.style.setProperty('display', 'none', 'important');
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    button.textContent = expanded ? '收起說明' : '？ 使用說明與架設需求';
  }

  function install() {
    const media = document.getElementById('teacher-media-production-1014');
    const shell = document.getElementById('teacher-media-studio-shell-1018');
    if (!media || !shell) return false;
    if (document.getElementById('teacher-media-help-toggle-1014')) return true;

    const lead = shell.querySelector('h4')?.parentElement?.querySelector('p.mt-1');
    if (lead) lead.style.setProperty('display', 'none', 'important');

    const actions = shell.querySelector('.teacher-media-shell-actions-1014') || shell;
    const button = document.createElement('button');
    button.id = 'teacher-media-help-toggle-1014';
    button.type = 'button';
    button.className = 'shrink-0 rounded-xl border border-cyan-200 bg-white px-3 py-2 text-xs font-black text-cyan-800 hover:bg-cyan-50';
    button.setAttribute('aria-controls', 'teacher-media-help-panel-1014');
    button.setAttribute('aria-expanded', 'false');
    button.textContent = '？ 使用說明與架設需求';
    actions.prepend(button);

    document.getElementById('teacher-media-help-panel-1014')?.remove();
    const panel = document.createElement('section');
    panel.id = 'teacher-media-help-panel-1014';
    panel.className = 'rounded-2xl border border-cyan-100 bg-cyan-50/40 p-4';
    panel.innerHTML = `
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs leading-5 text-slate-700">
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">AI PowerPoint</b><p class="mt-1">加入檔案、既有教材或貼入文字，產生大綱後由教師修正與核准，再產生正式簡報。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">講稿與配音</b><p class="mt-1">講稿建立、教師核准、Kokoro 試聽與正式配音放在同一條流程，不需要跨頁搬資料。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">老師自己錄影</b><p class="mt-1">可使用麥克風、攝影機或螢幕分享；瀏覽器需允許權限，完成後沿用 Browser → R2 → Worker。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">AI 教學影片</b><p class="mt-1">可由核准 PowerPoint／來源內容建立影片，再校正字幕與預覽，最後由教師確認發布。</p></div>
      </div>
      <details class="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
        <summary class="cursor-pointer font-black">架設／技術需求</summary>
        <div class="mt-2">AI 工作由院內 AI Worker 執行；Kokoro、FFmpeg、R2 與 AI provider 狀態請由系統管理／Worker 狀態確認。一般教師只需要依畫面完成來源、審核與發布，不需要操作技術設定。</div>
      </details>`;
    shell.insertAdjacentElement('afterend', panel);
    setPanelOpen(button, panel, false);
    button.addEventListener('click', () => setPanelOpen(button, panel, panel.hidden));
    return true;
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
