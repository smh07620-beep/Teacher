/* Teacher AI media studio: one source, one active mode, existing media APIs. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const canManage = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role))
    && typeof R.hasPermission === 'function' && R.hasPermission('material.manage');
  if (!canManage || document.getElementById('teacher-ai-media-studio-1018')) return;

  const $ = id => document.getElementById(id);
  let sourceMaterials = [];
  let activeMode = 'narration';

  function isCaptionSource(item) {
    const text = [item?.materialType, item?.mimeType, item?.sourceMimeType, item?.filename, item?.title]
      .filter(Boolean).join(' ').toLowerCase();
    return /video\/|audio\/|\.(mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|oga|flac)\b/.test(text)
      || String(item?.storageBackend || '').toLowerCase() === 'external';
  }

  function syncSourceOptions() {
    const legacy = $('teacher-script-material-1014');
    const shared = $('teacher-media-source-1018');
    if (!legacy || !shared) return;
    const previous = shared.value || legacy.value;
    shared.replaceChildren(...[...legacy.options].map(option => {
      const clone = option.cloneNode(true);
      clone.disabled = option.disabled;
      return clone;
    }));
    if ([...shared.options].some(option => option.value === previous)) shared.value = previous;
    updateRecommendation();
  }

  function selectedMaterial() {
    const id = $('teacher-media-source-1018')?.value || '';
    return sourceMaterials.find(item => String(item?.id || '') === id) || null;
  }

  function updateRecommendation() {
    const message = $('teacher-media-next-step-1018');
    if (!message) return;
    const item = selectedMaterial();
    if (!item) {
      message.textContent = '選擇教材後，製作室會推薦可進行的下一步。';
      return;
    }
    if (isCaptionSource(item)) {
      message.textContent = '推薦下一步：這是影音來源，可在「AI 字幕」建立字幕草稿，再由教師核准發布。';
      return;
    }
    const presentation = $('teacher-ai-video-presentation-1015');
    if (presentation?.value) {
      message.textContent = '推薦下一步：已有可用 PowerPoint，可在「教學影片」選擇旁白後建立影片。';
      return;
    }
    message.textContent = '推薦下一步：先在「AI 配音」建立並核准講稿，再產生 AI 語音。';
  }

  function syncSharedSource() {
    const shared = $('teacher-media-source-1018');
    const legacy = $('teacher-script-material-1014');
    if (!shared || !legacy) return;
    if (legacy.value !== shared.value) {
      legacy.value = shared.value;
      legacy.dispatchEvent(new Event('change', { bubbles: true }));
    }
    window.TeacherMediaSubtitle1014?.selectMaterial?.(shared.value || '');
    void refreshPresentationChoices(shared.value || '');
    updateRecommendation();
  }

  async function refreshPresentationChoices(materialId) {
    const select = $('teacher-ai-video-presentation-1015');
    if (!select || select.tagName !== 'SELECT') return;
    const prior = select.value;
    select.replaceChildren(new Option(materialId ? '讀取可用 PowerPoint…' : '請先選擇來源教材', ''));
    select.disabled = !materialId;
    if (!materialId) return;
    try {
      const response = await fetch(`/api/ai-presentations?materialId=${encodeURIComponent(materialId)}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      const rows = await response.json().catch(() => []);
      if (!response.ok) throw new Error(rows?.error || '無法讀取 PowerPoint 版本');
      const usable = (Array.isArray(rows) ? rows : []).filter(item =>
        item?.artifactReady && ['approved', 'published'].includes(String(item.status || ''))
      );
      select.replaceChildren(new Option(usable.length ? '選擇已核准 PowerPoint…' : '尚無已核准 PowerPoint', ''));
      usable.forEach(item => {
        const label = `${item.title || '教學 PowerPoint'}｜版本 ${Number(item.revisionNumber || 1)}${item.status === 'published' ? '｜已發布' : '｜已核准'}`;
        select.appendChild(new Option(label, String(item.id || '')));
      });
      select.disabled = !usable.length;
      if (usable.some(item => String(item.id) === prior)) select.value = prior;
      else if (usable.length === 1) select.value = String(usable[0].id || '');
      select.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (error) {
      select.replaceChildren(new Option('PowerPoint 版本讀取失敗', ''));
      select.disabled = true;
      const status = $('teacher-ai-video-status-1015');
      if (status) status.textContent = error.message;
    } finally {
      updateRecommendation();
    }
  }

  function showMode(next, focus = false) {
    activeMode = next;
    ['narration', 'subtitle', 'video'].forEach(mode => {
      const tab = $(`teacher-media-tab-${mode}-1018`);
      const panel = $(`teacher-media-panel-${mode}-1018`);
      const selected = mode === next;
      if (tab) {
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        tab.classList.toggle('bg-slate-900', selected);
        tab.classList.toggle('text-white', selected);
        tab.classList.toggle('bg-white', !selected);
        tab.classList.toggle('text-slate-700', !selected);
      }
      if (panel) panel.hidden = !selected;
    });
    if (focus) $(`teacher-media-tab-${next}-1018`)?.focus();
  }

  function installTabs(studio) {
    const tabs = document.createElement('div');
    tabs.className = 'teacher-media-tabs-1018 flex gap-2 overflow-x-auto';
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'AI 媒體製作模式');
    [['narration', '🎙️ AI 配音'], ['subtitle', '💬 AI 字幕'], ['video', '🎬 教學影片']].forEach(([mode, label]) => {
      const tab = document.createElement('button');
      tab.id = `teacher-media-tab-${mode}-1018`;
      tab.type = 'button';
      tab.className = 'shrink-0 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-black';
      tab.textContent = label;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', `teacher-media-panel-${mode}-1018`);
      tab.addEventListener('click', () => showMode(mode));
      tab.addEventListener('keydown', event => {
        const order = ['narration', 'subtitle', 'video'];
        const index = order.indexOf(mode);
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const target = event.key === 'Home' ? 0 : event.key === 'End' ? order.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + order.length) % order.length;
        showMode(order[target], true);
      });
      tabs.appendChild(tab);
    });
    studio.appendChild(tabs);
    const host = document.createElement('div');
    host.className = 'teacher-media-panels-1018';
    ['narration', 'subtitle', 'video'].forEach(mode => {
      const panel = document.createElement('section');
      panel.id = `teacher-media-panel-${mode}-1018`;
      panel.className = 'teacher-media-panel-1018 space-y-4';
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', `teacher-media-tab-${mode}-1018`);
      panel.tabIndex = 0;
      host.appendChild(panel);
    });
    studio.appendChild(host);
  }

  function makeDetails(summary, id) {
    const details = document.createElement('details');
    details.id = id;
    details.className = 'rounded-2xl border border-slate-200 bg-slate-50 p-3';
    const heading = document.createElement('summary');
    heading.className = 'cursor-pointer text-sm font-black text-slate-800';
    heading.textContent = summary;
    details.appendChild(heading);
    return details;
  }

  function humanizeExistingPanels() {
    const audioProvider = $('teacher-audio-provider-1014');
    if (audioProvider) audioProvider.textContent = '本機 AI｜隱私模式';
    const videoProvider = $('teacher-ai-video-provider-1015');
    if (videoProvider) videoProvider.textContent = '本機 AI｜隱私模式';
    const renderer = $('teacher-ai-video-renderer-1015');
    if (renderer) renderer.textContent = '品質檢查與教師核准後才能發布';
    const audio = $('teacher-media-audio-1014');
    const video = $('teacher-ai-video-1015');
    audio?.querySelector('h4') && (audio.querySelector('h4').textContent = '🎙️ 已核准講稿 → AI 配音');
    video?.querySelector('h4') && (video.querySelector('h4').textContent = '🎬 PowerPoint + 旁白 → 教學影片');
    audio?.querySelector('p.mt-1') && (audio.querySelector('p.mt-1').textContent = '只使用教師已核准的講稿；完成後仍進入既有審查與發布流程。');
    video?.querySelector('p.mt-1') && (video.querySelector('p.mt-1').textContent = '選擇已核准 PowerPoint 與旁白後建立影片；品質、預覽、核准與發布流程維持不變。');
  }

  function replaceVideoIdInput() {
    const input = $('teacher-ai-video-presentation-1015');
    if (!input || input.tagName === 'SELECT') return;
    const label = input.closest('label');
    const select = document.createElement('select');
    select.id = input.id;
    select.className = input.className;
    select.disabled = true;
    select.appendChild(new Option('請先選擇來源教材', ''));
    input.replaceWith(select);
    if (label?.firstChild?.nodeType === Node.TEXT_NODE) label.firstChild.textContent = '已核准 PowerPoint';
    select.addEventListener('change', updateRecommendation);
  }

  function movePanels(studio) {
    const narration = $('teacher-media-panel-narration-1018');
    const subtitle = $('teacher-media-panel-subtitle-1018');
    const video = $('teacher-media-panel-video-1018');
    const audioPanel = $('teacher-media-audio-1014');
    const subtitlePanel = $('teacher-media-subtitle-1014');
    const videoPanel = $('teacher-ai-video-1015');
    const scriptPanel = $('teacher-media-script-1014');
    const presentationPanel = $('teacher-ai-presentation-1016');
    if (!narration || !subtitle || !video || !audioPanel || !subtitlePanel || !videoPanel || !scriptPanel) return false;

    humanizeExistingPanels();
    replaceVideoIdInput();
    narration.appendChild(audioPanel);
    const scriptDetails = makeDetails('講稿草稿與版本', 'teacher-media-script-history-1018');
    scriptPanel.classList.remove('hidden');
    scriptPanel.removeAttribute('aria-hidden');
    const scriptSource = $('teacher-script-material-1014')?.closest('label');
    scriptSource?.classList.add('teacher-media-legacy-source-1018');
    $('teacher-script-refresh-materials-1014')?.parentElement?.classList.add('teacher-media-legacy-source-1018');
    scriptDetails.appendChild(scriptPanel);
    narration.appendChild(scriptDetails);

    subtitle.appendChild(subtitlePanel);
    $('teacher-subtitle-material-1017')?.closest('label')?.classList.add('teacher-media-legacy-source-1018');
    video.appendChild(videoPanel);
    const advanced = makeDetails('PowerPoint 版本、歷史與進階資訊', 'teacher-media-advanced-1018');
    if (presentationPanel) advanced.appendChild(presentationPanel);
    const technical = document.createElement('p');
    technical.className = 'mt-3 text-xs leading-5 text-slate-600';
    technical.textContent = '此處保留版本、來源追溯、品質檢查與發布紀錄。背景服務與儲存設定不會顯示敏感識別值。';
    advanced.appendChild(technical);
    studio.appendChild(advanced);
    return true;
  }

  function install() {
    const shell = $('teacher-media-studio-shell-1018');
    const media = $('teacher-media-production-1014');
    const legacySource = $('teacher-script-material-1014');
    if (!shell || !media || !legacySource) return false;
    const studio = document.createElement('section');
    studio.id = 'teacher-ai-media-studio-1018';
    studio.dataset.teacherMediaStudioPrimary = '1';
    studio.className = 'space-y-4';
    const sourceBox = document.createElement('div');
    sourceBox.className = 'rounded-2xl border border-cyan-100 bg-cyan-50/50 p-4';
    sourceBox.innerHTML = '<label class="block text-sm font-black text-slate-800">來源教材／來源內容<select id="teacher-media-source-1018" class="learning-input mt-2"></select></label><p id="teacher-media-next-step-1018" class="mt-2 text-xs font-bold text-cyan-900" aria-live="polite"></p>';
    studio.appendChild(sourceBox);
    installTabs(studio);
    shell.insertAdjacentElement('afterend', studio);
    if (!movePanels(studio)) { studio.remove(); return false; }
    syncSourceOptions();
    $('teacher-media-source-1018')?.addEventListener('change', syncSharedSource);
    window.addEventListener('teacher-media-source-options-1014', event => {
      sourceMaterials = Array.isArray(event.detail?.materials) ? event.detail.materials : [];
      syncSourceOptions();
      if (event.detail?.selectedId) $('teacher-media-source-1018').value = event.detail.selectedId;
      syncSharedSource();
    });
    void window.TeacherMediaSourceFix1014?.refreshMaterials?.();
    showMode(activeMode);
    syncSharedSource();
    return true;
  }

  // All contributing panels are loaded before this manifest entry.  A bounded
  // retry covers an asynchronous RBAC bootstrap without retaining an observer.
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (install()) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
})();
