/* Teacher 10/14: present narration as free local Kokoro, never OpenAI TTS. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  if (typeof R.hasPermission !== 'function' || !R.hasPermission('material.manage')) return;

  function applyStatus(data) {
    if (!data) return;
    const provider = document.getElementById('teacher-audio-provider-1014');
    if (provider) provider.textContent = data.readyForPreview
      ? `AI 語音可用｜本機 Kokoro / ${data.model || 'Kokoro'}`
      : data.enabled ? 'AI 語音待 AI Worker' : '待設定｜本機 Kokoro AI Worker + Cloudflare R2';
    const status = document.getElementById('teacher-audio-status-1014');
    if (status && !data.enabled && (status.textContent || '').includes('OPENAI_API_KEY')) {
      status.textContent = '免費 AI 語音尚未啟用；請確認本機 Kokoro AI Worker 與 R2 設定。';
    }
  }

  async function apply() {
    const section = document.getElementById('teacher-media-audio-1014');
    if (!section) return false;

    const title = section.querySelector('h4');
    if (title) title.textContent = '🎧 已核准講稿 → 免費 AI 語音';

    const lead = title?.parentElement?.querySelector('p.mt-1');
    if (lead) lead.textContent = '只有授課教師已核准的講稿才能送出。語音由院內 Windows AI Worker 使用本機 Kokoro 產生，完成後保存至 R2 並加入原課程教材；不呼叫 OpenAI TTS。';

    const button = document.getElementById('teacher-audio-generate-1014');
    if (button) button.textContent = '🎧 產生免費 AI 語音';

    const instruction = document.getElementById('teacher-audio-instructions-1014');
    const instructionLabel = instruction?.closest('label');
    if (instructionLabel) {
      instructionLabel.classList.add('hidden');
      instructionLabel.setAttribute('aria-hidden', 'true');
    }

    applyStatus(window.TeacherMediaAudioStatus1014 || null);
    return true;
  }

  if (!(await apply())) {
    const observer = new MutationObserver(async () => {
      if (await apply()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.addEventListener('teacher-media-audio-status-1014', event => {
    applyStatus(event.detail?.status || null);
  });

  window.TeacherMediaFreeTTS1014 = Object.freeze({ refresh: apply });
})();
