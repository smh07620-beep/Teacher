/* Teacher 10/14 media MVP: browser recording -> existing Browser/R2 material upload lane.
 * No media bytes are POSTed through the Render Web process.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const hasTeachingRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!hasTeachingRole || !has('material.manage')) return;

  let recorder = null;
  let recordingMode = '';
  let recorderMime = '';
  let recorderExtension = '';
  let chunks = [];
  let activeStreams = [];
  let recordedFile = null;
  let recordedUrl = '';
  let recordingStartedAt = 0;
  let timerId = null;
  let workspaceVisibilityObserver = null;

  const audioCandidates = [
    ['audio/ogg;codecs=opus', '.ogg'],
    ['audio/mp4', '.m4a'],
    ['audio/webm;codecs=opus', '.webm'],
    ['audio/webm', '.webm'],
  ];
  const videoCandidates = [
    ['video/webm;codecs=vp8,opus', '.webm'],
    ['video/webm', '.webm'],
    ['video/mp4', '.mp4'],
  ];

  function supportedRecorderType(candidates) {
    if (!window.MediaRecorder) return ['', ''];
    for (const [mime, extension] of candidates) {
      if (!MediaRecorder.isTypeSupported || MediaRecorder.isTypeSupported(mime)) return [mime, extension];
    }
    return ['', ''];
  }

  function safeBaseName(value) {
    return String(value || '教學媒體')
      .normalize('NFC')
      .replace(/[\\/:*?"<>|\r\n]+/g, '-')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 80) || '教學媒體';
  }

  function status(message, tone = 'normal') {
    const node = document.getElementById('teacher-recorder-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function formatElapsed(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  function startTimer() {
    recordingStartedAt = Date.now();
    const node = document.getElementById('teacher-recorder-timer-1014');
    clearInterval(timerId);
    const paint = () => { if (node) node.textContent = formatElapsed(Date.now() - recordingStartedAt); };
    paint();
    timerId = setInterval(paint, 500);
  }

  function stopTimer() {
    clearInterval(timerId);
    timerId = null;
  }

  function stopStreams() {
    activeStreams.forEach(stream => stream?.getTracks?.().forEach(track => track.stop()));
    activeStreams = [];
  }

  function stopCaptureForWorkspaceExit() {
    stopTimer();
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop(); }
      catch (_) { /* Stream teardown below is still authoritative. */ }
    }
    stopStreams();
  }

  function setRecordingButtons(active) {
    ['teacher-record-audio-1014','teacher-record-video-1014','teacher-record-screen-1014'].forEach(id => {
      const button = document.getElementById(id);
      if (button) button.disabled = active;
    });
    const stop = document.getElementById('teacher-record-stop-1014');
    if (stop) stop.disabled = !active;
    const upload = document.getElementById('teacher-record-upload-1014');
    if (upload) upload.disabled = active || !recordedFile;
  }

  function clearPreview() {
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    recordedUrl = '';
    recordedFile = null;
    const audio = document.getElementById('teacher-record-audio-preview-1014');
    const video = document.getElementById('teacher-record-video-preview-1014');
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.classList.add('hidden');
    }
    if (video) {
      video.pause();
      video.srcObject = null;
      video.removeAttribute('src');
      video.classList.add('hidden');
      video.muted = false;
    }
    const upload = document.getElementById('teacher-record-upload-1014');
    if (upload) upload.disabled = true;
  }

  function extensionForMime(mime, fallback) {
    const value = String(mime || '').toLowerCase();
    if (value.includes('ogg')) return '.ogg';
    if (value.includes('audio/mp4')) return '.m4a';
    if (value.includes('video/mp4')) return '.mp4';
    if (value.includes('webm')) return '.webm';
    return fallback || '.webm';
  }

  function showRecordedPreview(blob) {
    recordedUrl = URL.createObjectURL(blob);
    const audio = document.getElementById('teacher-record-audio-preview-1014');
    const video = document.getElementById('teacher-record-video-preview-1014');
    if (recordingMode === 'audio') {
      if (video) video.classList.add('hidden');
      if (audio) {
        audio.src = recordedUrl;
        audio.classList.remove('hidden');
      }
    } else if (video) {
      if (audio) audio.classList.add('hidden');
      video.srcObject = null;
      video.muted = false;
      video.src = recordedUrl;
      video.classList.remove('hidden');
    }
  }

  async function acquireStream(mode) {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('此瀏覽器不支援麥克風／攝影機錄製。');
    if (mode === 'audio') {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      activeStreams = [stream];
      return stream;
    }
    if (mode === 'video') {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
      });
      activeStreams = [stream];
      return stream;
    }
    if (mode === 'screen') {
      if (!navigator.mediaDevices.getDisplayMedia) throw new Error('此瀏覽器不支援螢幕錄製。');
      const screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      activeStreams = [screen, mic];
      const combined = new MediaStream([
        ...screen.getVideoTracks(),
        ...mic.getAudioTracks(),
      ]);
      const displayTrack = screen.getVideoTracks()[0];
      if (displayTrack) displayTrack.addEventListener('ended', () => stopRecording());
      return combined;
    }
    throw new Error('不支援的錄製模式。');
  }

  async function startRecording(mode) {
    if (!window.MediaRecorder) {
      status('此瀏覽器不支援 MediaRecorder，請改用最新版 Chrome、Edge 或 Safari。', 'error');
      return;
    }
    if (recorder && recorder.state !== 'inactive') return;
    clearPreview();
    recordingMode = mode;
    chunks = [];
    const candidates = mode === 'audio' ? audioCandidates : videoCandidates;
    [recorderMime, recorderExtension] = supportedRecorderType(candidates);

    try {
      const stream = await acquireStream(mode);
      recorder = recorderMime
        ? new MediaRecorder(stream, { mimeType: recorderMime })
        : new MediaRecorder(stream);
      recorderMime = recorder.mimeType || recorderMime || (mode === 'audio' ? 'audio/webm' : 'video/webm');
      recorderExtension = extensionForMime(recorderMime, recorderExtension);

      recorder.addEventListener('dataavailable', event => {
        if (event.data?.size) chunks.push(event.data);
      });
      recorder.addEventListener('stop', () => {
        stopTimer();
        stopStreams();
        const blob = new Blob(chunks, { type: recorderMime });
        const title = safeBaseName(document.getElementById('teacher-recorder-title-1014')?.value);
        const prefix = mode === 'audio' ? '語音' : (mode === 'screen' ? '螢幕教學' : '錄影');
        const filename = `${title}-${prefix}-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}${recorderExtension}`;
        recordedFile = new File([blob], filename, { type: recorderMime, lastModified: Date.now() });
        showRecordedPreview(blob);
        setRecordingButtons(false);
        status(`錄製完成：${filename}（${(recordedFile.size / 1024 / 1024).toFixed(1)} MB），確認預覽後可上傳。`, 'success');
      }, { once: true });

      const video = document.getElementById('teacher-record-video-preview-1014');
      if (mode !== 'audio' && video) {
        video.srcObject = stream;
        video.muted = true;
        video.classList.remove('hidden');
        void video.play().catch(() => {});
      }

      recorder.start(1000);
      startTimer();
      setRecordingButtons(true);
      status(mode === 'audio' ? '🎙️ 錄音中…' : mode === 'screen' ? '🖥️ 螢幕＋麥克風錄製中…' : '🎥 攝影機＋麥克風錄製中…');
    } catch (error) {
      stopTimer();
      stopStreams();
      recorder = null;
      setRecordingButtons(false);
      status(`無法開始錄製：${error.message}`, 'error');
    }
  }

  function stopRecording() {
    if (!recorder || recorder.state === 'inactive') return;
    try { recorder.stop(); }
    catch (error) {
      stopStreams();
      setRecordingButtons(false);
      status(`停止錄製失敗：${error.message}`, 'error');
    }
  }

  async function syncGroups() {
    const select = document.getElementById('teacher-recorder-group-1014');
    if (!select) return;
    const previous = select.value;
    select.replaceChildren();

    const canonical = document.getElementById('admin-material-group');
    const sourceOptions = canonical?.options?.length ? [...canonical.options] : [];
    if (sourceOptions.length) {
      sourceOptions.forEach(option => {
        const copy = document.createElement('option');
        copy.value = option.value;
        copy.textContent = option.textContent;
        select.appendChild(copy);
      });
    } else {
      const catalog = window.GROUPS || {};
      Object.entries(catalog).forEach(([key, group]) => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = group?.label || group?.name || key;
        select.appendChild(option);
      });
    }
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
    else if (canonical?.value) select.value = canonical.value;
  }

  async function syncCourses() {
    const select = document.getElementById('teacher-recorder-course-1014');
    const area = document.getElementById('teacher-recorder-area-1014')?.value || 'internal';
    const group = document.getElementById('teacher-recorder-group-1014')?.value || '';
    if (!select || !group) return;
    select.innerHTML = '<option value="">未指定課程</option>';
    try {
      const response = await fetch(`/api/courses?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      const courses = await response.json().catch(() => []);
      if (!response.ok) throw new Error(courses.error || '無法讀取課程');
      (Array.isArray(courses) ? courses : []).forEach(course => {
        const option = document.createElement('option');
        option.value = course.id || '';
        option.textContent = course.title || course.id || '未命名課程';
        select.appendChild(option);
      });
    } catch (error) {
      status(`課程清單讀取失敗：${error.message}`, 'error');
    }
  }

  async function uploadRecording() {
    if (!recordedFile) {
      status('請先完成一段錄音或錄影。', 'error');
      return;
    }
    if (!window.MaterialUploadClient?.enqueue) {
      status('教材安全上傳元件尚未載入，請重新整理後再試。', 'error');
      return;
    }
    const title = String(document.getElementById('teacher-recorder-title-1014')?.value || '').trim();
    const desc = String(document.getElementById('teacher-recorder-desc-1014')?.value || '').trim();
    const area = document.getElementById('teacher-recorder-area-1014')?.value || 'internal';
    const group = document.getElementById('teacher-recorder-group-1014')?.value || '';
    const courseId = document.getElementById('teacher-recorder-course-1014')?.value || '';
    if (!title) {
      status('請先填寫教材名稱。', 'error');
      document.getElementById('teacher-recorder-title-1014')?.focus();
      return;
    }
    if (!group) {
      status('請選擇教材組別。', 'error');
      return;
    }

    const form = new FormData();
    form.append('file', recordedFile);
    form.append('title', title);
    form.append('desc', desc);
    form.append('category', '');
    form.append('group', group);
    form.append('area', area);
    form.append('courseId', courseId);
    form.append('materialType', recordingMode === 'audio' ? 'standard' : 'video');
    form.append('progressId', `teacher-recorder-${Date.now()}`);
    ['atlasCategory','atlasMagnification','atlasInterpretation','atlasClinical','atlasDifferential','atlasNormality','atlasTags'].forEach(name => form.append(name, ''));

    const upload = document.getElementById('teacher-record-upload-1014');
    if (upload) upload.disabled = true;
    try {
      const result = await window.MaterialUploadClient.enqueue(form, {
        fileName: recordedFile.name,
        onProgress: event => status(`⬆️ Browser → R2 ${event.percent}%｜${(event.loaded/1024/1024).toFixed(1)} / ${(event.total/1024/1024).toFixed(1)} MB`),
      });
      status(`✅ 已安全送入背景處理佇列${result?.jobId ? `｜${result.jobId}` : ''}。可離開此頁，Worker 會繼續處理。`, 'success');
      window.invalidateAdminMaterialsCache?.();
      void window.renderAdminCourseMaterialHub?.(true);
      void window.renderSlidesGrid?.();
    } catch (error) {
      status(`上傳失敗：${error.message}`, 'error');
      if (upload) upload.disabled = false;
    }
  }

  function install() {
    const media = document.getElementById('teacher-media-production-1014');
    if (!media || document.getElementById('teacher-recorder-1014')) return false;

    const section = document.createElement('section');
    section.id = 'teacher-recorder-1014';
    section.className = 'bg-white border border-teal-200 rounded-2xl p-5 shadow-sm space-y-4';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-teal-700">DIRECT RECORDING</p><h4 class="text-lg font-black text-slate-950">🎙️ 老師直接錄音／錄影</h4><p class="mt-1 text-xs text-slate-500">錄製在瀏覽器完成；確認預覽後才上傳。上傳沿用既有 Browser → R2 → Worker 流程，不讓大型影音經過 Render Web。</p></div><span class="rounded-full bg-emerald-50 px-3 py-1.5 text-[11px] font-bold text-emerald-700">第一階段可用</span></div>
      <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900"><b>隱私提醒：</b>教學錄音／錄影請勿包含病人姓名、病歷號、身分證字號、可辨識影像或其他不必要個資。</div>
      <div class="grid md:grid-cols-2 xl:grid-cols-4 gap-3">
        <label class="text-xs font-bold text-slate-600 xl:col-span-2">教材名稱<input id="teacher-recorder-title-1014" class="learning-input mt-1" maxlength="120" placeholder="例如：血庫抗體鑑定操作說明"></label>
        <label class="text-xs font-bold text-slate-600">訓練區<select id="teacher-recorder-area-1014" class="learning-input mt-1"><option value="internal">院內教育訓練</option><option value="pgy">PGY</option></select></label>
        <label class="text-xs font-bold text-slate-600">組別<select id="teacher-recorder-group-1014" class="learning-input mt-1"></select></label>
        <label class="text-xs font-bold text-slate-600 xl:col-span-2">所屬課程<select id="teacher-recorder-course-1014" class="learning-input mt-1"><option value="">未指定課程</option></select></label>
        <label class="text-xs font-bold text-slate-600 xl:col-span-2">說明<input id="teacher-recorder-desc-1014" class="learning-input mt-1" maxlength="300" placeholder="可填本段影音涵蓋的重點"></label>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button id="teacher-record-audio-1014" type="button" class="rounded-xl bg-cyan-700 px-4 py-2 text-xs font-black text-white">🎙️ 開始錄音</button>
        <button id="teacher-record-video-1014" type="button" class="rounded-xl bg-indigo-700 px-4 py-2 text-xs font-black text-white">🎥 攝影機錄影</button>
        <button id="teacher-record-screen-1014" type="button" class="rounded-xl bg-violet-700 px-4 py-2 text-xs font-black text-white">🖥️ 螢幕＋旁白</button>
        <button id="teacher-record-stop-1014" type="button" disabled class="rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-black text-rose-700 disabled:opacity-40">■ 停止</button>
        <span id="teacher-recorder-timer-1014" class="font-mono text-xs font-bold text-slate-500">00:00</span>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-slate-950 p-3 min-h-[92px] flex items-center justify-center"><audio id="teacher-record-audio-preview-1014" class="hidden w-full" controls></audio><video id="teacher-record-video-preview-1014" class="hidden max-h-[420px] w-full rounded-xl" controls playsinline></video><p id="teacher-recorder-empty-1014" class="text-xs text-slate-400">開始錄製後可在這裡預覽；錄完不滿意可直接重錄，不會自動上傳。</p></div>
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"><div id="teacher-recorder-status-1014" class="text-xs text-slate-600">尚未錄製。</div><div class="flex gap-2"><button id="teacher-record-discard-1014" type="button" class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-600">重新錄製／清除</button><button id="teacher-record-upload-1014" type="button" disabled class="rounded-xl bg-teal-700 px-4 py-2 text-xs font-black text-white disabled:opacity-40">☁️ 上傳成教材</button></div></div>`;
    media.appendChild(section);

    document.getElementById('teacher-record-audio-1014')?.addEventListener('click', () => startRecording('audio'));
    document.getElementById('teacher-record-video-1014')?.addEventListener('click', () => startRecording('video'));
    document.getElementById('teacher-record-screen-1014')?.addEventListener('click', () => startRecording('screen'));
    document.getElementById('teacher-record-stop-1014')?.addEventListener('click', stopRecording);
    document.getElementById('teacher-record-discard-1014')?.addEventListener('click', () => {
      if (recorder && recorder.state !== 'inactive') {
        status('請先停止目前錄製，再清除。', 'error');
        return;
      }
      clearPreview();
      status('已清除，可重新錄製。');
    });
    document.getElementById('teacher-record-upload-1014')?.addEventListener('click', uploadRecording);
    document.getElementById('teacher-recorder-area-1014')?.addEventListener('change', async () => {
      await syncGroups();
      await syncCourses();
    });
    document.getElementById('teacher-recorder-group-1014')?.addEventListener('change', syncCourses);

    if (!navigator.mediaDevices?.getDisplayMedia) {
      const screen = document.getElementById('teacher-record-screen-1014');
      if (screen) {
        screen.disabled = true;
        screen.title = '此瀏覽器不支援螢幕錄製';
        screen.classList.add('opacity-40');
      }
    }
    if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
      ['teacher-record-audio-1014','teacher-record-video-1014'].forEach(id => {
        const button = document.getElementById(id);
        if (button) {
          button.disabled = true;
          button.classList.add('opacity-40');
        }
      });
      status('此瀏覽器不支援直接錄製；仍可回「教材與課程」上傳既有影音檔。', 'error');
    }

    workspaceVisibilityObserver?.disconnect();
    workspaceVisibilityObserver = new MutationObserver(() => {
      if (media.classList.contains('hidden')) stopCaptureForWorkspaceExit();
    });
    workspaceVisibilityObserver.observe(media, { attributes: true, attributeFilter: ['class'] });

    const empty = document.getElementById('teacher-recorder-empty-1014');
    const previewObserver = new MutationObserver(() => {
      const audioVisible = !document.getElementById('teacher-record-audio-preview-1014')?.classList.contains('hidden');
      const videoVisible = !document.getElementById('teacher-record-video-preview-1014')?.classList.contains('hidden');
      empty?.classList.toggle('hidden', audioVisible || videoVisible);
    });
    const audioPreview = document.getElementById('teacher-record-audio-preview-1014');
    const videoPreview = document.getElementById('teacher-record-video-preview-1014');
    if (audioPreview) previewObserver.observe(audioPreview, { attributes: true, attributeFilter: ['class'] });
    if (videoPreview) previewObserver.observe(videoPreview, { attributes: true, attributeFilter: ['class'] });

    void (async () => {
      const canonicalArea = document.getElementById('admin-material-area')?.value || window.currentTrainingArea || 'internal';
      const area = document.getElementById('teacher-recorder-area-1014');
      if (area) area.value = canonicalArea === 'pgy' ? 'pgy' : 'internal';
      await syncGroups();
      await syncCourses();
    })();
    return true;
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.addEventListener('pagehide', stopCaptureForWorkspaceExit);

  window.TeacherMediaRecorder1014 = Object.freeze({
    startAudio: () => startRecording('audio'),
    startVideo: () => startRecording('video'),
    startScreen: () => startRecording('screen'),
    stop: stopRecording,
    cleanup: stopCaptureForWorkspaceExit,
  });
})();
