/* Teacher AI media studio: one source, one active mode, existing media APIs. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const canManage = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role))
    && typeof R.hasPermission === 'function' && R.hasPermission('material.manage');
  if (!canManage) return;

  const $ = id => document.getElementById(id);
  let sourceMaterials = [];
  let activeMode = 'narration';
  let retryGeneration = 0;
  let presentationMaterialId = null;
  let presentationRequest = null;
  let presentationRequestGeneration = 0;

  async function fetchJson(url, options = {}, timeoutMs = 12000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      const body = await response.json().catch(() => []);
      if (!response.ok) throw new Error(body?.error || '服務暫時無法回應');
      return body;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('讀取逾時，請按重新整理後再試。');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function isCaptionSource(item) {
    const text = [item?.materialType, item?.mimeType, item?.sourceMimeType, item?.filename, item?.title]
      .filter(Boolean).join(' ').toLowerCase();
    return /video\/|audio\/|\.(mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|oga|flac)\b/.test(text)
      || String(item?.storageBackend || '').toLowerCase() === 'external';
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

  function syncSourceOptions() {
    const legacy = $('teacher-script-material-1014');
    const shared = $('teacher-media-source-1018');
    if (!shared) return;
    if (!legacy) {
      if (!shared.options.length) shared.replaceChildren(new Option('正在載入可用教材…', ''));
      shared.disabled = true;
      updateRecommendation();
      return;
    }
    const previous = shared.value || legacy.value;
    shared.replaceChildren(...[...legacy.options].map(option => {
      const clone = option.cloneNode(true);
      clone.disabled = option.disabled;
      return clone;
    }));
    if ([...shared.options].some(option => option.value === previous)) shared.value = previous;
    shared.disabled = legacy.disabled || shared.options.length <= 1;
    updateRecommendation();
  }

  function syncSharedSource({forcePresentation = false} = {}) {
    const shared = $('teacher-media-source-1018');
    if (!shared) return;
    const canonical = window.TeacherAIMediaControls1023?.syncSelectedSource;
    if (typeof canonical === 'function') {
      canonical({force: forcePresentation});
      updateRecommendation();
      return;
    }
    const legacy = $('teacher-script-material-1014');
    if (!legacy) return;
    if (legacy.value !== shared.value) {
      legacy.value = shared.value;
      legacy.dispatchEvent(new Event('change', { bubbles: true }));
    }
    window.TeacherMediaSubtitle1014?.selectMaterial?.(shared.value || '');
    const materialId = shared.value || '';
    if (forcePresentation || materialId !== presentationMaterialId) {
      void refreshPresentationChoices(materialId, {force: forcePresentation});
    }
    updateRecommendation();
  }

  async function refreshPresentationChoices(materialId = '', {force = false} = {}) {
    const normalizedMaterialId = String(materialId || '');
    const owner = window.TeacherAIMediaControls1023?.refreshVideoPresentations;
    if (typeof owner === 'function') {
      presentationMaterialId = normalizedMaterialId;
      return owner(normalizedMaterialId, {force});
    }
    const select = $('teacher-ai-video-presentation-1015');
    if (!select || select.tagName !== 'SELECT') return false;
    if (!force && normalizedMaterialId === presentationMaterialId && presentationRequest) {
      return presentationRequest;
    }
    if (!force && normalizedMaterialId === presentationMaterialId && !presentationRequest) return false;
    presentationMaterialId = normalizedMaterialId;
    const generation = ++presentationRequestGeneration;
    const prior = select.value;
    const group = new URLSearchParams(window.location.search).get('group')
      || window.currentGroupKey
      || String(R.user?.preferredGroup || '');
    select.replaceChildren(new Option('讀取所有已核准 PowerPoint…', ''));
    select.disabled = true;
    presentationRequest = (async () => {
      const query = group ? `?group=${encodeURIComponent(group)}` : '';
      const rows = await fetchJson(`/api/ai-presentations${query}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      if (generation !== presentationRequestGeneration || normalizedMaterialId !== presentationMaterialId) return false;
      window.TeacherPresentationChoicesCache1026 = {
        group: String(group || ''),
        loadedAt: Date.now(),
        rows: Array.isArray(rows) ? rows : [],
      };
      const usable = (Array.isArray(rows) ? rows : []).filter(item =>
        item?.artifactReady && ['approved', 'published'].includes(String(item.status || ''))
      );
      select.replaceChildren(new Option(usable.length ? '選擇已核准 PowerPoint…' : '尚無已核准 PowerPoint', ''));
      usable.forEach(item => {
        const preferred = normalizedMaterialId && String(item.materialId || '') === normalizedMaterialId ? '｜目前來源' : '';
        const label = `${item.title || '教學 PowerPoint'}｜版本 ${Number(item.revisionNumber || 1)}${item.status === 'published' ? '｜已發布' : '｜已核准'}${preferred}`;
        select.appendChild(new Option(label, String(item.id || '')));
      });
      select.disabled = !usable.length;
      if (usable.some(item => String(item.id) === prior)) select.value = prior;
      else if (usable.length === 1) select.value = String(usable[0].id || '');
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })();
    try {
      return await presentationRequest;
    } catch (error) {
      if (generation !== presentationRequestGeneration) return;
      select.replaceChildren(new Option('PowerPoint 版本讀取失敗', ''));
      select.disabled = true;
      const status = $('teacher-ai-video-status-1015');
      if (status) status.textContent = `PowerPoint 讀取失敗：${error.message}`;
      return false;
    } finally {
      if (generation === presentationRequestGeneration) presentationRequest = null;
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
    if ($('teacher-media-tab-narration-1018')) return;
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
    select.appendChild(new Option('讀取所有已核准 PowerPoint…', ''));
    input.replaceWith(select);
    if (label?.firstChild?.nodeType === Node.TEXT_NODE) label.firstChild.textContent = '已核准 PowerPoint';
    select.addEventListener('change', updateRecommendation);
  }

  function waiting(panel, id, text) {
    if (!panel || $(id)) return;
    const note = document.createElement('div');
    note.id = id;
    note.className = 'rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs font-bold text-slate-500';
    note.textContent = text;
    panel.appendChild(note);
  }

  function restorePowerPointAuthoring() {
    const panel = $('teacher-ai-presentation-1016');
    const stage = $('teacher-ai-material-presentation-stage-1014');
    if (panel && stage && panel.parentElement !== stage) stage.appendChild(panel);
  }

  function installPowerPointShortcut() {
    // PowerPoint authoring now has one canonical entry in the shared source header.
    // Remove the older duplicate shortcut card if an older hydration pass left it behind.
    $('teacher-media-powerpoint-entry-1018')?.remove();
  }

  function attachPanels(studio) {
    const narration = $('teacher-media-panel-narration-1018');
    const subtitle = $('teacher-media-panel-subtitle-1018');
    const video = $('teacher-media-panel-video-1018');
    if (!narration || !subtitle || !video) return false;

    restorePowerPointAuthoring();
    humanizeExistingPanels();
    replaceVideoIdInput();

    const audioPanel = $('teacher-media-audio-1014');
    if (audioPanel) {
      $('teacher-media-waiting-audio-1018')?.remove();
      if (audioPanel.parentElement !== narration) narration.appendChild(audioPanel);
    } else {
      waiting(narration, 'teacher-media-waiting-audio-1018', 'AI 配音功能載入中…');
    }

    const scriptPanel = $('teacher-media-script-1014');
    if (scriptPanel) {
      let scriptDetails = $('teacher-media-script-history-1018');
      if (!scriptDetails) {
        scriptDetails = makeDetails('講稿草稿與版本', 'teacher-media-script-history-1018');
        narration.appendChild(scriptDetails);
      }
      scriptPanel.classList.remove('hidden');
      scriptPanel.removeAttribute('aria-hidden');
      const scriptSource = $('teacher-script-material-1014')?.closest('label');
      scriptSource?.classList.add('teacher-media-legacy-source-1018');
      $('teacher-script-refresh-materials-1014')?.parentElement?.classList.add('teacher-media-legacy-source-1018');
      if (scriptPanel.parentElement !== scriptDetails) scriptDetails.appendChild(scriptPanel);
    }

    const subtitlePanel = $('teacher-media-subtitle-1014');
    if (subtitlePanel) {
      $('teacher-media-waiting-subtitle-1018')?.remove();
      if (subtitlePanel.parentElement !== subtitle) subtitle.appendChild(subtitlePanel);
      $('teacher-subtitle-material-1017')?.closest('label')?.classList.add('teacher-media-legacy-source-1018');
    } else {
      waiting(subtitle, 'teacher-media-waiting-subtitle-1018', 'AI 字幕功能載入中…');
    }

    const videoPanel = $('teacher-ai-video-1015');
    if (videoPanel) {
      $('teacher-media-waiting-video-1018')?.remove();
      if (videoPanel.parentElement !== video) video.appendChild(videoPanel);
    } else {
      waiting(video, 'teacher-media-waiting-video-1018', '教學影片功能載入中…');
    }

    let advanced = $('teacher-media-advanced-1018');
    if (!advanced) {
      advanced = makeDetails('媒體版本、品質與進階資訊', 'teacher-media-advanced-1018');
      const technical = document.createElement('p');
      technical.id = 'teacher-media-advanced-note-1018';
      technical.className = 'mt-3 text-xs leading-5 text-slate-600';
      technical.textContent = '此處只保留媒體版本、品質檢查與發布說明；AI PowerPoint 製作仍在「教材與課程」主工作台。背景服務與儲存設定不會顯示敏感識別值。';
      advanced.appendChild(technical);
      studio.appendChild(advanced);
    } else {
      const heading = advanced.querySelector(':scope > summary');
      if (heading) heading.textContent = '媒體版本、品質與進階資訊';
      const technical = $('teacher-media-advanced-note-1018');
      if (technical) technical.textContent = '此處只保留媒體版本、品質檢查與發布說明；AI PowerPoint 製作仍在「教材與課程」主工作台。背景服務與儲存設定不會顯示敏感識別值。';
    }
    restorePowerPointAuthoring();
    return true;
  }

  function fullyHydrated() {
    const studio = $('teacher-ai-media-studio-1018');
    if (!studio) return false;
    return ['teacher-media-audio-1014', 'teacher-media-subtitle-1014', 'teacher-ai-video-1015', 'teacher-media-script-1014']
      .every(id => $(id)?.closest('#teacher-ai-media-studio-1018'));
  }

  function bindSharedSource() {
    const shared = $('teacher-media-source-1018');
    if (!shared || shared.dataset.mediaStudioBound === '1') return;
    shared.dataset.mediaStudioBound = '1';
    shared.addEventListener('change', syncSharedSource);
  }

  function install() {
    const shell = $('teacher-media-studio-shell-1018');
    const media = $('teacher-media-production-1014');
    if (!shell || !media) return false;

    let studio = $('teacher-ai-media-studio-1018');
    if (!studio) {
      studio = document.createElement('section');
      studio.id = 'teacher-ai-media-studio-1018';
      studio.dataset.teacherMediaStudioPrimary = '1';
      studio.className = 'space-y-4';
      const sourceBox = document.createElement('div');
      sourceBox.className = 'rounded-2xl border border-cyan-100 bg-cyan-50/50 p-4';
      sourceBox.innerHTML = '<div class="grid lg:grid-cols-[1fr_auto] gap-3 lg:items-end"><label class="block text-sm font-black text-slate-800">來源教材／來源內容（AI 配音、字幕可用）<select id="teacher-media-source-1018" class="learning-input mt-2" disabled><option value="">正在載入可用教材…</option></select></label><div class="rounded-xl border border-violet-200 bg-white p-3 min-w-[240px]"><div class="text-[10px] font-black text-violet-700">AI POWERPOINT</div><button id="teacher-media-direct-powerpoint-1026" type="button" class="mt-1 w-full rounded-lg bg-violet-700 px-3 py-2 text-xs font-black text-white">🖥️ AI PowerPoint 製作</button><div class="mt-1 text-[10px] text-slate-500">同一入口：PDF／Word／PPTX／Excel／圖片／文字，可多選、貼入或拖曳</div></div></div><p id="teacher-media-next-step-1018" class="mt-2 text-xs font-bold text-cyan-900" aria-live="polite"></p>';
      studio.appendChild(sourceBox);
      installTabs(studio);
      installPowerPointShortcut();
      shell.insertAdjacentElement('afterend', studio);
    } else {
      installTabs(studio);
      installPowerPointShortcut();
    }

    attachPanels(studio);
    syncSourceOptions();
    bindSharedSource();
    showMode(activeMode);
    if ($('teacher-script-material-1014')) {
      void window.TeacherMediaSourceFix1014?.refreshMaterials?.();
      syncSharedSource();
    }
    return true;
  }

  function handleSourceOptions(event) {
    sourceMaterials = Array.isArray(event.detail?.materials) ? event.detail.materials : [];
    install();
    syncSourceOptions();
    const shared = $('teacher-media-source-1018');
    if (event.detail?.selectedId && shared) shared.value = event.detail.selectedId;
    syncSharedSource();
  }

  window.addEventListener('teacher-ai-presentation-video-request', async event => {
    const presentationId=String(event.detail?.presentationId||'');
    const materialId=String(event.detail?.materialId||'');
    if(!presentationId)return;
    try { await window.TeacherWorkspace1014?.openMedia?.(); } catch (_) {}
    install();
    const shared=$('teacher-media-source-1018');
    if(shared&&materialId&&[...shared.options].some(option=>option.value===materialId)){
      shared.value=materialId;
      syncSharedSource();
    }
    if(materialId)await refreshPresentationChoices(materialId, {force:true});
    const select=$('teacher-ai-video-presentation-1015');
    if(select&&[...select.options].some(option=>option.value===presentationId)){
      select.value=presentationId;
      select.dispatchEvent(new Event('change',{bubbles:true}));
    }
    showMode('video');
    const status=$('teacher-ai-video-status-1015');
    if(status)status.textContent='已帶入核准 PowerPoint；選擇旁白聲音後即可建立教學影片。';
    $('teacher-media-panel-video-1018')?.scrollIntoView?.({behavior:'smooth',block:'start'});
  });
  window.addEventListener('teacher-media-source-options-1014', handleSourceOptions);

  async function hydrate(generation) {
    for (let attempt = 0; attempt < 48 && generation === retryGeneration; attempt += 1) {
      install();
      if (fullyHydrated()) return;
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }

  function refreshLifecycle() {
    const generation = ++retryGeneration;
    void hydrate(generation);
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => refreshLifecycle());
  document.addEventListener('click', event => {
    if (event.target.closest?.('#teacher-course-media-entry-1014 button,#teacher-nav-media-1014')) {
      setTimeout(refreshLifecycle, 0);
    }
  });

  window.TeacherAIMediaStudio1018 = Object.freeze({
    refresh: refreshLifecycle,
    refreshPresentationChoices: (materialId, options = {}) => refreshPresentationChoices(materialId, options),
  });
  refreshLifecycle();
})();
