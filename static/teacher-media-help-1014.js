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
    if (!media || document.getElementById('teacher-media-help-toggle-1014')) return Boolean(media);

    const summary = [...media.children].find(node => {
      const title = node.querySelector?.('h4')?.textContent || '';
      return title.includes('教材媒體製作');
    });
    if (!summary) return false;

    const children = [...summary.children];
    const header = children[0];
    if (!header) return false;

    const titleBox = header.querySelector('h4')?.parentElement;
    const lead = titleBox?.querySelector('p.mt-1');
    if (lead) lead.style.setProperty('display', 'none', 'important');

    const button = document.createElement('button');
    button.id = 'teacher-media-help-toggle-1014';
    button.type = 'button';
    button.className = 'shrink-0 rounded-xl border border-cyan-200 bg-white px-3 py-2 text-xs font-black text-cyan-800 hover:bg-cyan-50';
    button.setAttribute('aria-controls', 'teacher-media-help-panel-1014');
    button.setAttribute('aria-expanded', 'false');
    button.textContent = '？ 使用說明與架設需求';

    const chip = header.querySelector('.admin-workspace-chip');
    if (chip) chip.replaceWith(button);
    else header.appendChild(button);

    const panel = document.createElement('div');
    panel.id = 'teacher-media-help-panel-1014';
    panel.className = 'space-y-4 rounded-2xl border border-cyan-100 bg-cyan-50/40 p-4';
    panel.innerHTML = `
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs leading-5 text-slate-700">
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">AI 講稿</b><p class="mt-1">是真功能：從已上傳教材抽取文字，建立 AI 草稿，再由老師修改與核准。課程建立畫面的「AI 草稿」是 AI 出題，不是這個講稿功能。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">免費 AI 語音</b><p class="mt-1">只接受老師已核准的講稿。語音由院內 Windows AI Worker 使用本機 Kokoro 產生，不使用 OpenAI TTS，也不產生每次生成的 TTS API 費用。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">老師錄音／錄影</b><p class="mt-1">是真功能：使用瀏覽器麥克風、攝影機或螢幕分享錄製。瀏覽器需允許權限，正式上傳沿用 Browser → R2 → Worker。</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-slate-900">目前沒有自動 AI 影片</b><p class="mt-1">現階段的影片功能是老師自行錄影或錄製螢幕，不是 AI 自動生成虛擬講師影片。</p></div>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
        <b>架設需求</b><br>
        1. AI 講稿／AI 出題：AI_EXTERNAL_PROCESSING_ENABLED=true，並設定免費 AI_PROVIDER 對應金鑰（目前預設 Groq 時使用 GROQ_API_KEY）。<br>
        2. 免費 AI 語音：AI_TTS_PROVIDER=kokoro；本機 AI Worker 安裝 requirements-ai-worker.txt，並設定既有 R2_ACCOUNT_ID、R2_ACCESS_KEY_ID、R2_SECRET_ACCESS_KEY、R2_BUCKET_NAME。<br>
        3. 背景處理：本地 AI Worker 必須持續執行 ai_question_worker.py；Web 只排工作，不執行長時間 AI 任務。<br>
        4. 真人錄音／錄影：使用 HTTPS 網站，瀏覽器允許麥克風／攝影機／螢幕分享即可；上傳仍需要既有 R2/Worker 流程正常。
      </div>`;

    children.slice(1).forEach(node => panel.appendChild(node));
    summary.appendChild(panel);
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
