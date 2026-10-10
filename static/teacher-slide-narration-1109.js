/* Teacher slide narration recorder.
 *
 * The only entry point is TeacherSlideNarration1109.open(material), called from the material
 * management lists (編輯課程 → 教材 and the material hub).  It opens the slide material in the
 * normal viewer with the recorder armed; the teacher talks while paging through the slides and
 * presses stop.  Merely viewing a material anywhere else never shows the recorder.  The voice is uploaded through the existing
 * Browser -> R2 -> Worker lane as an audio material (no media bytes touch the Render Web
 * process) and then bound to the slide material together with a page timeline, so learners
 * hear the voice and the viewer turns pages in step (see learner-narration-1100.js).
 *
 * Page turns are detected by polling window.slideViewerState.index, so buttons, thumbnails
 * and the keyboard are all captured, not just clicks on one control.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const hasTeachingRole = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role));
  if (!hasTeachingRole || !has('material.manage')) return;

  const MIN_DURATION_MS = 3000;
  const PAGE_MODES = new Set(['presentation', 'paged_document']);
  const audioCandidates = [
    ['audio/ogg;codecs=opus', '.ogg'],
    ['audio/mp4', '.m4a'],
    ['audio/webm;codecs=opus', '.webm'],
    ['audio/webm', '.webm'],
  ];

  let state = 'idle'; // idle | recording | paused | review | saving | bound
  let armed = false; // true only after open(); the viewer is showing the material to narrate
  let material = null;
  let recorder = null;
  let stream = null;
  let chunks = [];
  let mime = '';
  let extension = '';
  let timeline = [];
  let lastPage = -1;
  let t0 = 0;
  let pausedAt = 0;
  let pausedTotal = 0;
  let durationMs = 0;
  let recordedFile = null;
  let previewUrl = '';
  let wantSubtitle = true; // 儲存後是否順便產生字幕草稿（預設勾選，老師可取消）
  let boundAudioId = '';
  let subtitleQueued = false;
  let pendingBind = null; // { audioId } kept so a failed bind can be retried without re-uploading
  let tickId = 0;
  let armedAt = 0; // when open() armed the recorder
  let viewerSeen = false; // the viewer has actually been seen open since arming
  let preload = { done: 0, total: 0, ready: false, imgs: [], token: 0 };
  let stopping = false;
  let panel = null;
  const ui = {};

  const slideMaterials = () => Array.isArray(window.cachedSlidesList) ? window.cachedSlidesList : [];
  const viewerOpen = () => {
    const modal = document.getElementById('slide-viewer-modal');
    return !!modal && !modal.classList.contains('hidden');
  };
  const viewerState = () => window.slideViewerState || {};

  function eligibleMaterial() {
    if (!viewerOpen()) return null;
    const current = viewerState();
    if (!PAGE_MODES.has(String(current.readerMode || ''))) return null;
    const found = slideMaterials().find(item => item && String(item.id) === String(current.materialId || ''));
    if (!found || found.isBuiltin) return null;
    if (!armed || !material || String(found.id) !== String(material.id)) return null;
    if (!['slides', 'preview_pdf'].includes(String(found.viewerMode || ''))) return null;
    return found;
  }

  function pickRecorderType() {
    if (!window.MediaRecorder) return ['', ''];
    for (const [type, ext] of audioCandidates) {
      if (!MediaRecorder.isTypeSupported || MediaRecorder.isTypeSupported(type)) return [type, ext];
    }
    return ['', '.webm'];
  }

  // learner-narration-1100.js reads this flag: no playback and no automatic page turning
  // while recording, otherwise an existing narration would be recorded into the new one.
  function setRecordingFlag(on) {
    window.__teacherNarrationRecording = !!on;
    if (on) { try { window.LearnerNarration1100?.stop?.(); } catch (_) { /* ignore */ } }
  }

  function elapsedMs() {
    const end = state === 'paused' ? pausedAt : performance.now();
    return Math.max(0, Math.round(end - t0 - pausedTotal));
  }

  function clock(ms) {
    const total = Math.floor(ms / 1000);
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  }

  function button(label, tone, handler) {
    const node = document.createElement('button');
    node.type = 'button';
    node.textContent = label;
    const palette = {
      primary: 'background:#0f766e;color:#fff;border:0',
      danger: 'background:#be123c;color:#fff;border:0',
      plain: 'background:#fff;color:#334155;border:1px solid #cbd5e1',
    }[tone] || 'background:#fff;color:#334155;border:1px solid #cbd5e1';
    node.style.cssText = palette + ';border-radius:10px;padding:7px 12px;font-size:12px;font-weight:800;cursor:pointer';
    node.addEventListener('click', handler);
    return node;
  }

  function buildPanel() {
    if (panel) return;
    panel = document.createElement('section');
    panel.id = 'teacher-narration-rec-1109';
    panel.setAttribute('data-teacher-narration-recorder', '1');
    panel.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483000;width:min(92vw,360px);'
      + 'background:#0f172a;color:#fff;border-radius:16px;padding:12px;box-shadow:0 8px 28px rgba(0,0,0,.4);'
      + 'font-size:13px;display:none';
    ui.title = document.createElement('div');
    ui.title.style.cssText = 'font-weight:900;margin-bottom:6px';
    ui.message = document.createElement('div');
    ui.message.style.cssText = 'font-size:12px;line-height:1.5;color:#cbd5e1;margin-bottom:8px;white-space:pre-line';
    ui.timer = document.createElement('div');
    ui.timer.style.cssText = 'font-family:ui-monospace,monospace;font-size:20px;font-weight:900;margin-bottom:8px';
    ui.audio = document.createElement('audio');
    ui.audio.controls = true;
    ui.audio.style.cssText = 'width:100%;margin-bottom:8px;display:none';
    ui.option = document.createElement('label');
    ui.option.style.cssText = 'display:none;align-items:flex-start;gap:6px;font-size:12px;line-height:1.5;color:#e2e8f0;margin-bottom:8px;cursor:pointer';
    ui.optionBox = document.createElement('input');
    ui.optionBox.type = 'checkbox';
    ui.optionBox.checked = true;
    ui.optionBox.addEventListener('change', () => { wantSubtitle = ui.optionBox.checked; });
    const optionText = document.createElement('span');
    optionText.textContent = '儲存後順便產生字幕草稿（免費，由醫院電腦處理；不會自動公開，核准後學員才看得到）。不需要可取消勾選，之後仍可補做。';
    ui.option.append(ui.optionBox, optionText);
    ui.status = document.createElement('div');
    ui.status.style.cssText = 'font-size:11px;margin-bottom:8px;max-height:140px;overflow:auto;color:#0f172a;background:#fff;border-radius:10px;display:none';
    ui.actions = document.createElement('div');
    ui.actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px';
    panel.append(ui.title, ui.message, ui.timer, ui.audio, ui.option, ui.status, ui.actions);
    document.body.appendChild(panel);
  }

  function setActions(...nodes) {
    ui.actions.replaceChildren(...nodes);
  }

  function say(message, tone) {
    ui.message.textContent = message;
    ui.message.style.color = tone === 'error' ? '#fda4af' : tone === 'success' ? '#86efac' : '#cbd5e1';
  }

  function render() {
    buildPanel();
    const showAudio = state === 'review' || state === 'saving' || state === 'bound';
    ui.audio.style.display = showAudio ? 'block' : 'none';
    if (state !== 'saving') ui.status.style.display = ui.status.dataset.keep === '1' ? 'block' : 'none';
    ui.timer.style.display = state === 'idle' ? 'none' : 'block';
    ui.option.style.display = state === 'review' ? 'flex' : 'none';
    if (ui.optionBox) ui.optionBox.checked = wantSubtitle;
    if (state === 'idle') {
      ui.title.textContent = '🎙️ 老師旁白';
      say('一邊播放投影片一邊講解，系統會記下每一頁的時間，學員開啟教材時會自動跟著翻頁。', 'normal');
      const waiting = !eligibleMaterial();
      const loading = preload.total > 0 && !preload.ready;
      const startBtn = button(waiting ? '教材載入中…' : loading ? `準備投影片 ${preload.done}/${preload.total}…` : '🎙 開始錄製旁白', 'primary', () => void start());
      if (waiting || loading) { startBtn.disabled = true; startBtn.style.opacity = '.55'; }
      const nodes = [startBtn];
      if (loading) nodes.push(button('不等了，直接錄', 'plain', () => void start()));
      nodes.push(button('✕ 不錄了', 'plain', disarm));
      setActions(...nodes);
      if (waiting) say('正在開啟教材，請稍候…', 'normal');
      else if (loading) say('正在先把每一頁載入，錄音時翻頁才不會卡住。', 'normal');
    } else if (state === 'recording') {
      ui.title.textContent = '🔴 錄音中';
      say('請照常翻頁講解（按鈕、縮圖、方向鍵都可以）。講完按「停止」。');
      setActions(button('⏸ 暫停', 'plain', pause), button('■ 停止', 'danger', stop));
    } else if (state === 'paused') {
      ui.title.textContent = '⏸ 已暫停';
      say('暫停期間不會錄音，也不會算進時間。');
      setActions(button('▶ 繼續', 'primary', resume), button('■ 停止', 'danger', stop));
    } else if (state === 'review') {
      ui.title.textContent = '✅ 錄好了，先聽聽看';
      say(`共 ${timeline.length} 次換頁、${clock(durationMs)}。確認沒問題再儲存；不滿意可重錄。`);
      setActions(button('💾 儲存並掛到這份教材', 'primary', () => void save()), button('🗑 重錄', 'plain', discard));
    } else if (state === 'saving') {
      ui.title.textContent = '⏳ 儲存中';
      setActions();
    } else if (state === 'bound') {
      ui.title.textContent = '🎉 旁白已掛上';
      setActions(
        ...(subtitleQueued || !boundAudioId ? [] : [button('📝 產生字幕草稿', 'plain', () => void queueSubtitle(boundAudioId))]),
        button('完成', 'primary', finish),
      );
    }
  }

  function showPanelIfNeeded() {
    buildPanel();
    const busy = state !== 'idle' && state !== 'bound';
    if (viewerOpen()) viewerSeen = true;
    if (armed && state === 'idle') {
      // Only give up when the viewer was open and then closed, or never opened within 12 s.
      if ((viewerSeen && !viewerOpen()) || (!viewerSeen && performance.now() - armedAt > 12000)) { disarm(); return; }
      const ready = !!eligibleMaterial();
      if (ready && preload.token === 0) startPreload();
      if (ui.actions && ui.actions.dataset.ready !== String(ready) + preload.ready + preload.done) {
        ui.actions.dataset.ready = String(ready) + preload.ready + preload.done;
        render();
      }
    }
    panel.style.display = (armed || busy || state === 'bound') ? 'block' : 'none';
  }

  // Load every page image once before recording so page turns are instant while talking.
  function startPreload() {
    const current = viewerState();
    const total = Number(current.pageCount || (current.images || []).length || 0);
    const token = ++preload.token;
    preload = { done: 0, total, ready: total === 0, imgs: [], token };
    if (!total) return;
    const urlFor = i => current.mode === 'pdf' && typeof window.presentationPreviewPageUrl === 'function'
      ? window.presentationPreviewPageUrl(i + 1)
      : (current.images || [])[i];
    let next = 0;
    const worker = async () => {
      while (next < total && preload.token === token) {
        const url = urlFor(next++);
        if (url) {
          for (let attempt = 0; attempt < 3 && preload.token === token; attempt += 1) {
            const ok = await new Promise(resolve => {
              const img = new Image();
              preload.imgs.push(img);
              img.onload = () => resolve(true);
              img.onerror = () => resolve(false);
              img.src = url; // same URL on retry so the browser cache serves the viewer later
              setTimeout(() => resolve(false), 20000);
            });
            if (ok) break;
            await new Promise(r => setTimeout(r, 800 * (attempt + 1))); // transient 502 from the page renderer
          }
        }
        if (preload.token !== token) return;
        preload.done += 1;
        if (preload.done >= total) preload.ready = true;
      }
    };
    void Promise.all([worker(), worker(), worker()]).then(() => { if (preload.token === token) { preload.ready = true; showPanelIfNeeded(); } });
  }

  function releaseStream() {
    if (stream) {
      stream.getTracks().forEach(track => { try { track.stop(); } catch (_) { /* ignore */ } });
      stream = null;
    }
  }

  function clearRecording() {
    clearInterval(tickId);
    tickId = 0;
    stopping = false;
    setRecordingFlag(false);
    releaseStream();
    recorder = null;
    chunks = [];
    timeline = [];
    recordedFile = null;
    durationMs = 0;
    pendingBind = null;
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = ''; }
    ui.audio?.removeAttribute('src');
    if (ui.status) { ui.status.dataset.keep = ''; ui.status.style.display = 'none'; ui.status.textContent = ''; }
  }

  function tick() {
    if (state === 'recording') {
      const index = Number(viewerState().index);
      if (Number.isInteger(index) && index !== lastPage) {
        timeline.push({ page: index, startMs: elapsedMs() });
        lastPage = index;
      }
      ui.timer.textContent = `${clock(elapsedMs())}｜第 ${Math.max(0, lastPage) + 1} 頁`;
      if (!viewerOpen() && !stopping) {
        say('投影片視窗已關閉，錄音已自動停止。', 'error');
        stop();
      }
    } else if (state === 'paused') {
      ui.timer.textContent = `${clock(elapsedMs())}｜已暫停`;
    }
  }

  async function start() {
    const target = eligibleMaterial();
    if (!target) { say('請先開啟一份投影片教材再錄製。', 'error'); return; }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      say('此瀏覽器不支援錄音，請改用最新版 Chrome、Edge 或 Safari。', 'error');
      return;
    }
    if (!window.confirm('隱私提醒：旁白請勿提到病人姓名、病歷號、身分證字號或其他可辨識個資。\n\n按「確定」開始錄音。')) return;
    clearRecording();
    material = target;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (error) {
      say(`無法使用麥克風：${error.message || error}。請確認瀏覽器已允許麥克風權限。`, 'error');
      return;
    }
    [mime, extension] = pickRecorderType();
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch (error) {
      releaseStream();
      say(`無法開始錄音：${error.message || error}`, 'error');
      return;
    }
    chunks = [];
    recorder.addEventListener('dataavailable', event => { if (event.data && event.data.size) chunks.push(event.data); });
    recorder.addEventListener('stop', onRecorderStop);
    pausedTotal = 0;
    lastPage = Number.isInteger(Number(viewerState().index)) ? Number(viewerState().index) : 0;
    timeline = [{ page: lastPage, startMs: 0 }];
    setRecordingFlag(true);
    recorder.start(1000);
    t0 = performance.now();
    state = 'recording';
    tickId = setInterval(tick, 150);
    render();
  }

  function pause() {
    if (state !== 'recording' || !recorder) return;
    try { recorder.pause(); } catch (_) { return; }
    pausedAt = performance.now();
    state = 'paused';
    render();
  }

  function resume() {
    if (state !== 'paused' || !recorder) return;
    try { recorder.resume(); } catch (_) { return; }
    pausedTotal += performance.now() - pausedAt;
    state = 'recording';
    render();
  }

  function stop() {
    if ((state !== 'recording' && state !== 'paused') || !recorder || stopping) return;
    stopping = true;
    // Page the learner would see right now; make sure the final page is in the timeline.
    tick();
    durationMs = elapsedMs();
    clearInterval(tickId);
    tickId = 0;
    try { recorder.stop(); } catch (_) { onRecorderStop(); }
  }

  function onRecorderStop() {
    stopping = false;
    setRecordingFlag(false);
    releaseStream();
    const type = (recorder && recorder.mimeType) || mime || 'audio/webm';
    const blob = new Blob(chunks, { type });
    if (durationMs < MIN_DURATION_MS || blob.size < 1024) {
      state = 'idle';
      clearRecording();
      render();
      say('錄音太短或沒有收到聲音，請再試一次。', 'error');
      return;
    }
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    recordedFile = new File([blob], `narration-${stamp}${extension || '.webm'}`, { type });
    previewUrl = URL.createObjectURL(blob);
    ui.audio.src = previewUrl;
    ui.timer.textContent = clock(durationMs);
    state = 'review';
    render();
  }

  function discard() {
    if (state === 'saving') return;
    state = 'idle';
    clearRecording();
    render();
  }

  function finish() {
    boundAudioId = '';
    subtitleQueued = false;
    state = 'idle';
    clearRecording();
    render();
    showPanelIfNeeded();
  }

  function showStatusNode() {
    ui.status.dataset.keep = '1';
    ui.status.style.display = 'block';
    return ui.status;
  }

  async function bind(audioId) {
    const response = await fetch(`/api/materials/${encodeURIComponent(material.id)}/teacher-narration`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audioMaterialId: audioId, timeline, durationMs }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `掛載失敗（HTTP ${response.status}）`);
    return data;
  }

  async function afterBound(audioId) {
    window.invalidateAdminMaterialsCache?.();
    try { await Promise.resolve(window.renderSlidesGrid?.()); } catch (_) { /* list refresh is best-effort */ }
    state = 'bound';
    render();
    say('旁白已掛到這份教材，學員下次開啟就會聽到並自動翻頁。', 'success');
    boundAudioId = audioId;
    subtitleQueued = false;
    if (wantSubtitle) await queueSubtitle(audioId);
    else say('旁白已掛上。沒有產生字幕；需要時按下方「產生字幕草稿」，或到「教材製作 → AI 字幕」。', 'success');
    render();
  }

  async function queueSubtitle(audioId) {
    say('字幕草稿送出中…');
    try {
      const response = await fetch('/api/media-subtitles/generate', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ materialId: audioId, language: 'zh-TW', label: '繁體中文字幕' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法建立字幕工作');
      subtitleQueued = true;
      say('旁白已掛上，字幕草稿已送出（醫院電腦處理，免費）。完成後請到「教材製作 → AI 字幕」確認文字並核准，學員才看得到。', 'success');
    } catch (error) {
      say(`旁白已掛上，但字幕草稿沒有建立成功：${error.message}\n可按「產生字幕草稿」重試，或之後到「教材製作 → AI 字幕」。`, 'error');
    }
    render();
  }

  async function save() {
    if (state !== 'review' || !recordedFile || !material) return;
    if (!window.MaterialUploadClient?.enqueue || !window.waitForAdminMaterialJobs) {
      say('教材上傳元件尚未載入，請重新整理頁面後再試。', 'error');
      return;
    }
    state = 'saving';
    render();
    const statusNode = showStatusNode();
    window.beginTeacherMaterialUploadGuard?.('旁白錄音正在上傳與處理中，請先不要離開。');
    try {
      let audioId = pendingBind?.audioId || '';
      if (!audioId) {
        const form = new FormData();
        form.append('file', recordedFile);
        form.append('title', `旁白｜${String(material.title || '教材').slice(0, 100)}`);
        form.append('desc', '老師錄製的投影片旁白（掛在原教材上，學員不會看到獨立的一份）');
        form.append('category', '');
        form.append('group', String(material.group || ''));
        form.append('area', String(material.area || 'internal'));
        form.append('courseId', String(material.courseId || ''));
        form.append('materialType', 'standard');
        form.append('progressId', `teacher-narration-${Date.now()}`);
        ['atlasCategory', 'atlasMagnification', 'atlasInterpretation', 'atlasClinical', 'atlasDifferential', 'atlasNormality', 'atlasTags']
          .forEach(name => form.append(name, ''));
        say('⬆️ 上傳中…');
        const result = await window.MaterialUploadClient.enqueue(form, {
          fileName: recordedFile.name,
          onProgress: event => say(`⬆️ 上傳中 ${event.percent}%`),
        });
        if (!result?.jobId) throw new Error('上傳結果缺少背景工作編號。');
        say('⏳ 等待系統處理錄音…');
        const outcome = await window.waitForAdminMaterialJobs([String(result.jobId)], statusNode);
        const job = outcome?.rows?.[0] || {};
        if (!outcome?.allDone) throw new Error(job.error || job.detail || '錄音處理失敗，請稍後再試。');
        audioId = String(job.materialId || '');
        if (!audioId) throw new Error('系統沒有回報錄音的教材編號，請到教材清單確認這份旁白是否已建立。');
        pendingBind = { audioId };
      }
      say('🔗 正在把旁白掛到投影片…');
      await bind(audioId);
      pendingBind = null;
      await afterBound(audioId);
    } catch (error) {
      state = 'review';
      render();
      say(`${error.message || error}\n${pendingBind ? '錄音已上傳，按「儲存」會只重試掛載，不會重傳。' : '可以再按一次「儲存」重試。'}`, 'error');
    } finally {
      window.endTeacherMaterialUploadGuard?.();
    }
  }

  // Leave authoring mode: hide the panel and let the learner player behave normally again.
  function disarm() {
    if (state !== 'idle' && state !== 'bound') return;
    armed = false;
    material = null;
    viewerSeen = false;
    preload = { done: 0, total: 0, ready: false, imgs: [], token: 0 };
    window.__teacherNarrationRecording = false;
    render();
    showPanelIfNeeded();
  }

  async function findMaterial(ref) {
    const id = String((ref && ref.id) || ref || '');
    if (!id || !Array.isArray(window.cachedSlidesList)) return null;
    let found = window.cachedSlidesList.find(item => item && String(item.id) === id);
    if (!found) {
      // The shared list is filled when the learner portal loads; teachers may not have opened it yet.
      // Mutate it in place: the viewer scripts keep their own reference to the same array.
      try {
        const area = encodeURIComponent(String((ref && ref.area) || 'internal'));
        const response = await fetch(`/api/slides?area=${area}`, { credentials: 'same-origin', cache: 'no-store' });
        const rows = response.ok ? await response.json() : [];
        found = (Array.isArray(rows) ? rows : []).find(item => item && String(item.id) === id) || null;
        if (found) window.cachedSlidesList.push(found);
      } catch (_) { found = null; }
    }
    return found;
  }

  // Entry point for the material management lists.  Returns true when the viewer was opened.
  async function open(ref) {
    if (state !== 'idle' && state !== 'bound') {
      window.alert('目前有一段旁白正在錄製或儲存中，請先完成或取消。');
      return false;
    }
    const found = await findMaterial(ref);
    if (!found || found.isBuiltin) { window.alert('找不到這份教材，請重新整理頁面後再試。'); return false; }
    if (!['slides', 'preview_pdf'].includes(String(found.viewerMode || ''))) {
      window.alert('只有投影片、PDF 或 Word 文件這類「會翻頁」的教材可以錄旁白。');
      return false;
    }
    clearRecording();
    state = 'idle';
    material = found;
    armed = true;
    armedAt = performance.now();
    viewerSeen = false;
    preload = { done: 0, total: 0, ready: false, imgs: [], token: 0 };
    window.__teacherNarrationRecording = true; // keep the existing narration quiet while preparing
    render();
    if (typeof window.openMaterial !== 'function') { disarm(); window.alert('教材檢視器尚未載入，請重新整理頁面。'); return false; }
    await window.openMaterial(found.id);
    // openMaterial may resolve before the viewer is on screen; wait for it (up to 8 s).
    for (let waited = 0; waited < 8000 && !viewerOpen(); waited += 100) await new Promise(r => setTimeout(r, 100));
    viewerSeen = viewerOpen();
    // A plain PDF opens in continuous-scroll mode, which has no page turns to record.  For narration
    // we re-open the same file page by page (the viewer already renders Word PDFs this way).
    const opened = viewerState();
    if (viewerOpen() && opened.mode === 'pdf' && opened.readerMode === 'document'
        && typeof window.openSlideViewer === 'function') {
      window.openSlideViewer({
        previewUrl: opened.previewUrl,
        pageCount: opened.pageCount,
        title: opened.title,
        materialId: opened.materialId,
        readerMode: 'paged_document',
      });
    }
    if (!viewerOpen()) { disarm(); window.alert('教材沒有成功開啟，請再按一次「錄旁白」。'); return false; }
    if (!PAGE_MODES.has(String(viewerState().readerMode || ''))) {
      window.alert('這份教材目前是連續捲動的閱讀模式，沒有「翻頁」可以同步，無法錄製旁白。');
      disarm();
      return false;
    }
    showPanelIfNeeded();
    return true;
  }

  function boot() {
    buildPanel();
    render();
    setInterval(showPanelIfNeeded, 700);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.TeacherSlideNarration1109 = Object.freeze({
    open,
    state: () => state,
    isArmed: () => armed,
    eligibleMaterial,
  });
})();
