/* Teacher AI media studio: mode-local sources, one active mode, existing media APIs. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const canManage = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role))
    && typeof R.hasPermission === 'function' && R.hasPermission('material.manage');
  if (!canManage) return;

  const $ = id => document.getElementById(id);
  let sourceMaterials = [];
  let activeMode = 'presentation';
  let retryGeneration = 0;
  let presentationMaterialId = null;

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
      message.textContent = '推薦下一步：這是影音來源，可在「教學影片」內建立字幕草稿，或直接進行老師錄影後續處理。';
      return;
    }
    const presentation = $('teacher-ai-video-presentation-1015');
    if (presentation?.value) {
      message.textContent = '推薦下一步：已有可用 PowerPoint，可在「教學影片」選擇旁白後建立影片。';
      return;
    }
    message.textContent = '推薦下一步：可製作 AI PowerPoint、建立講稿與配音，或直接開始老師錄影。';
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
    presentationMaterialId = normalizedMaterialId;
    const owner = window.TeacherAIMediaControls1023?.refreshVideoPresentations;
    if (typeof owner !== 'function') return false;
    return owner(normalizedMaterialId, {force});
  }

  function showMode(next, focus = false) {
    const modes = ['presentation', 'narration', 'recording', 'video'];
    if (!modes.includes(next)) next = 'narration';
    const previous = activeMode;
    activeMode = next;
    if (previous === 'recording' && next !== 'recording') {
      window.TeacherMediaRecorder1014?.cleanup?.();
    }
    modes.forEach(mode => {
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
    if (next === 'presentation') {
      const host = $('teacher-media-panel-presentation-1018');
      const authoring = window.TeacherAIMaterial1014?.ensureMounted?.(host || null);
      authoring?.classList.remove('hidden');
      authoring?.removeAttribute('aria-hidden');
      // PowerPoint owns its source selection. Do not preselect from the
      // narration compatibility bridge.
      window.TeacherAIMaterial1014?.paintMaterialOptions?.('');
    }
    if (focus) $(`teacher-media-tab-${next}-1018`)?.focus();
  }

  function installTabs(studio) {
    if ($('teacher-media-tab-presentation-1018')) return;
    const tabs = document.createElement('div');
    tabs.className = 'teacher-media-tabs-1018 flex gap-2 overflow-x-auto';
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', '教材媒體製作模式');
    const modes = [
      ['presentation', '🖥️ AI PowerPoint'],
      ['narration', '🎙️ 講稿與配音'],
      ['recording', '📹 老師自己錄影'],
      ['video', '🎬 教學影片'],
    ];
    modes.forEach(([mode, label]) => {
      const tab = document.createElement('button');
      tab.id = `teacher-media-tab-${mode}-1018`;
      tab.type = 'button';
      tab.className = 'shrink-0 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-black';
      tab.textContent = label;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', `teacher-media-panel-${mode}-1018`);
      tab.addEventListener('click', () => showMode(mode));
      tab.addEventListener('keydown', event => {
        const order = modes.map(([key]) => key);
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
    modes.forEach(([mode]) => {
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
    // Provider/renderer readiness text is owned by the audio/video modules.
    // Do not overwrite live Worker/Kokoro diagnostics during studio hydration.
    const renderer = $('teacher-ai-video-renderer-1015');
    if (renderer && !renderer.textContent.trim()) renderer.textContent = '品質檢查與教師核准後才能發布';
    const audio = $('teacher-media-audio-1014');
    const video = $('teacher-ai-video-1015');
    audio?.querySelector('h4') && (audio.querySelector('h4').textContent = '🎙️ 講稿核准後直接 AI 配音');
    video?.querySelector('h4') && (video.querySelector('h4').textContent = '🎬 教學影片製作');
    audio?.querySelector('p.mt-1') && (audio.querySelector('p.mt-1').textContent = '講稿與配音在同一流程完成：建立／修改講稿 → 教師核准 → 選聲音與試聽 → 產生 AI 配音。');
    video?.querySelector('p.mt-1') && (video.querySelector('p.mt-1').textContent = '影片可從現有教材、私人製作來源、PDF、Word、PPTX、圖片、文字或已完成簡報開始；系統需要時會先準備可渲染畫面，不要求先發布成正式教材。');
  }

  function replaceVideoIdInput() {
    const input = $('teacher-ai-video-presentation-1015');
    if (!input || input.tagName === 'SELECT') return;
    const label = input.closest('label');
    const select = document.createElement('select');
    select.id = input.id;
    select.className = input.className;
    select.disabled = true;
    select.appendChild(new Option('讀取已準備影片畫面…', ''));
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
    // PowerPoint authoring belongs to the AI source authoring workspace.
    // Media/video must not recreate a second PowerPoint entry.
    $('teacher-media-powerpoint-entry-1018')?.remove();
    $('teacher-media-direct-powerpoint-1026')?.remove();
    $('teacher-ai-video-powerpoint-author-1027')?.remove();
  }

  function attachPanels(studio) {
    const presentation = $('teacher-media-panel-presentation-1018');
    const narration = $('teacher-media-panel-narration-1018');
    const recording = $('teacher-media-panel-recording-1018');
    const video = $('teacher-media-panel-video-1018');
    if (!presentation || !narration || !recording || !video) return false;

    humanizeExistingPanels();
    replaceVideoIdInput();

    const authoring = window.TeacherAIMaterial1014?.ensureMounted?.(presentation) || $('teacher-ai-material-1014');
    if (authoring) {
      if (authoring.parentElement !== presentation) presentation.appendChild(authoring);
      authoring.classList.remove('hidden');
      authoring.removeAttribute('aria-hidden');
      $('teacher-media-waiting-presentation-1018')?.remove();
    } else {
      waiting(presentation, 'teacher-media-waiting-presentation-1018', 'AI PowerPoint 製作功能載入中…');
    }

    let narrationFlow = $('teacher-media-narration-flow-1028');
    if (!narrationFlow) {
      narrationFlow = document.createElement('div');
      narrationFlow.id = 'teacher-media-narration-flow-1028';
      narrationFlow.className = 'rounded-2xl border border-indigo-100 bg-indigo-50/50 px-4 py-3 text-xs leading-5 text-indigo-950';
      narrationFlow.innerHTML = '<b>講稿與配音是一條流程：</b> ① 選來源／建立講稿 → ② 教師核准 → ③ 選 AI 聲音與試聽 → ④ 產生配音。核准講稿會自動帶到下一步，不需要在兩個區塊來回切換。';
      narration.prepend(narrationFlow);
    }

    const scriptPanel = $('teacher-media-script-1014');
    if (scriptPanel) {
      $('teacher-media-script-history-1018')?.remove();
      scriptPanel.classList.remove('hidden');
      scriptPanel.removeAttribute('aria-hidden');
      $('teacher-script-material-1014')?.closest('label')?.classList.add('teacher-media-legacy-source-1018');
      $('teacher-script-refresh-materials-1014')?.parentElement?.classList.add('teacher-media-legacy-source-1018');
      if (scriptPanel.parentElement !== narration) narration.appendChild(scriptPanel);
    } else {
      waiting(narration, 'teacher-media-waiting-script-1018', '講稿功能載入中…');
    }

    const audioPanel = $('teacher-media-audio-1014');
    if (audioPanel) {
      $('teacher-media-waiting-audio-1018')?.remove();
      if (audioPanel.parentElement !== narration) narration.appendChild(audioPanel);
    } else {
      waiting(narration, 'teacher-media-waiting-audio-1018', 'AI 配音功能載入中…');
    }

    const recorderPanel = $('teacher-recorder-1014');
    if (recorderPanel) {
      $('teacher-media-waiting-recorder-1018')?.remove();
      if (recorderPanel.parentElement !== recording) recording.appendChild(recorderPanel);
    } else {
      waiting(recording, 'teacher-media-waiting-recorder-1018', '老師錄影功能載入中…');
    }

    const videoPanel = $('teacher-ai-video-1015');
    if (videoPanel) {
      $('teacher-media-waiting-video-1018')?.remove();
      if (videoPanel.parentElement !== video) video.appendChild(videoPanel);
    } else {
      waiting(video, 'teacher-media-waiting-video-1018', '教學影片功能載入中…');
    }

    let captions = $('teacher-media-video-captions-1018');
    if (!captions) {
      captions = makeDetails('字幕與校正', 'teacher-media-video-captions-1018');
      const helper = document.createElement('p');
      helper.className = 'mt-2 text-xs leading-5 text-slate-600';
      helper.textContent = 'AI 字幕整合在影片流程內：影音來源完成後產生字幕草稿，由教師校正後再發布。';
      captions.appendChild(helper);
      video.appendChild(captions);
    }
    const subtitlePanel = $('teacher-media-subtitle-1014');
    if (subtitlePanel) {
      $('teacher-media-waiting-subtitle-1018')?.remove();
      if (subtitlePanel.parentElement !== captions) captions.appendChild(subtitlePanel);
      $('teacher-subtitle-material-1017')?.closest('label')?.classList.add('teacher-media-legacy-source-1018');
    } else {
      waiting(captions, 'teacher-media-waiting-subtitle-1018', 'AI 字幕功能載入中…');
    }

    let advanced = $('teacher-media-advanced-1018');
    if (!advanced) {
      advanced = makeDetails('版本、品質與進階資訊', 'teacher-media-advanced-1018');
      const technical = document.createElement('p');
      technical.id = 'teacher-media-advanced-note-1018';
      technical.className = 'mt-3 text-xs leading-5 text-slate-600';
      technical.textContent = 'PowerPoint、講稿／配音、老師錄影與 AI 教學影片共用同一個製作室；背景服務、版本與品質資訊集中在此處。';
      advanced.appendChild(technical);
      studio.appendChild(advanced);
    } else {
      const technical = $('teacher-media-advanced-note-1018');
      if (technical) technical.textContent = 'PowerPoint、講稿／配音、老師錄影與 AI 教學影片共用同一個製作室；背景服務、版本與品質資訊集中在此處。';
    }
    return true;
  }

  function fullyHydrated() {
    const studio = $('teacher-ai-media-studio-1018');
    if (!studio) return false;
    return ['teacher-ai-material-1014', 'teacher-media-audio-1014', 'teacher-media-subtitle-1014', 'teacher-ai-video-1015', 'teacher-media-script-1014', 'teacher-recorder-1014']
      .every(id => $(id)?.closest('#teacher-ai-media-studio-1018'));
  }

  function bindSharedSource() {
    const shared = $('teacher-media-source-1018');
    if (!shared || shared.dataset.mediaStudioBound === '1') return;
    shared.dataset.mediaStudioBound = '1';
    shared.addEventListener('change', () => {
      // Once the canonical controls are present they own source propagation.
      // Keep this fallback only for older/partial hydration so one user change
      // cannot trigger two presentation refreshes and reset the visible select.
      if (window.TeacherAIMediaControls1023) {
        updateRecommendation();
        return;
      }
      syncSharedSource();
    });
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
      const sourceBridge = document.createElement('div');
      sourceBridge.id = 'teacher-media-source-bridge-1018';
      sourceBridge.hidden = true;
      sourceBridge.setAttribute('aria-hidden', 'true');
      sourceBridge.innerHTML = '<select id="teacher-media-source-1018" disabled tabindex="-1"><option value="">正在載入可用教材…</option></select><p id="teacher-media-next-step-1018" aria-live="polite"></p>';
      studio.appendChild(sourceBridge);
      const sourcePolicy = document.createElement('p');
      sourcePolicy.id = 'teacher-media-source-policy-1029';
      sourcePolicy.className = 'text-xs font-bold text-slate-500';
      sourcePolicy.textContent = '先選擇要製作的內容；來源資料改在各功能內選擇，不需要先做全域教材選取。';
      studio.appendChild(sourcePolicy);
      installTabs(studio);
      installPowerPointShortcut();
      shell.insertAdjacentElement('afterend', studio);
    } else {
      installTabs(studio);
      installPowerPointShortcut();
    }

    attachPanels(studio);
    // teacher-ai-media-controls-1023.js is the single owner of the visible
    // source picker once it exists. Re-copying the legacy hidden select during
    // this hydrate loop made the visible selection jump back to "讀取中".
    if (!window.TeacherAIMediaControls1023) syncSourceOptions();
    bindSharedSource();
    showMode(activeMode);
    if ($('teacher-script-material-1014')) {
      if (window.TeacherAIMediaControls1023) updateRecommendation();
      else syncSharedSource();
    }
    return true;
  }

  function handleSourceOptions(event) {
    sourceMaterials = Array.isArray(event.detail?.materials) ? event.detail.materials : [];
    install();
    const shared = $('teacher-media-source-1018');
    if (event.detail?.canonical) {
      // Canonical controls already painted both source selects. Re-copying the
      // legacy select here can reset an in-flight teacher selection and create
      // a fetch/change loop.
      if (event.detail?.selectedId && shared && [...shared.options].some(option => option.value === event.detail.selectedId)) {
        shared.value = event.detail.selectedId;
      }
      updateRecommendation();
      return;
    }
    syncSourceOptions();
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
    if(status)status.textContent='已帶入核准影片畫面；選擇旁白聲音後即可建立教學影片。';
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
    showMode: (mode, focus = false) => { install(); showMode(mode, focus); },
    activeMode: () => activeMode,
    refreshPresentationChoices: (materialId, options = {}) => refreshPresentationChoices(materialId, options),
  });
  refreshLifecycle();
})();
