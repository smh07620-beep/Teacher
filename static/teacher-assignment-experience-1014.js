/* Teacher 10/14 usability convergence: voice previews, scoped assignment pickers,
 * batch assignment, and on-demand guidance. Existing server RBAC remains authoritative.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const canAssign = has('learning.assign');
  const canManageMaterial = has('material.manage');
  if (!canAssign && !canManageMaterial) return;

  const audienceCache = new Map();
  const previewCache = new Map();
  let previewAudio = null;
  let applying = false;
  let scheduled = false;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  function voiceLabel(value) {
    return window.TeacherVoiceCatalog1026?.label?.(value) || '中文語音';
  }

  async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '服務暫時無法回應');
      return data;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('AI 語音服務回應逾時，已停止這次讀取。');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function fetchAudienceOptions(area, group) {
    const key = `${area || 'internal'}::${group || ''}`;
    if (audienceCache.has(key)) return audienceCache.get(key);
    const promise = fetch(`/api/learning-assignments/audience-options?area=${encodeURIComponent(area || '')}&group=${encodeURIComponent(group || '')}`, {
      credentials: 'same-origin', cache: 'no-store'
    }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取指派對象');
      return data;
    }).catch(error => {
      audienceCache.delete(key);
      throw error;
    });
    audienceCache.set(key, promise);
    return promise;
  }

  function personOptionLabel(person) {
    const name = String(person?.name || person?.username || '').trim();
    const emp = String(person?.empId || '').trim();
    return `${name}${emp ? `｜${emp}` : ''}`;
  }

  function replaceAudienceInput(dialog) {
    let input = dialog.querySelector('#learning-assignment-audience-key');
    if (!input || input.tagName === 'SELECT') return input;
    const select = document.createElement('select');
    select.id = input.id;
    select.className = input.className;
    select.autocomplete = 'off';
    select.setAttribute('aria-label', '指派對象');
    input.replaceWith(select);

    const wrap = dialog.querySelector('#learning-assignment-audience-key-wrap');
    if (wrap && !wrap.querySelector('#learning-assignment-person-search-1014')) {
      const search = document.createElement('input');
      search.id = 'learning-assignment-person-search-1014';
      search.type = 'search';
      search.className = 'hidden mt-2';
      search.placeholder = '搜尋姓名、工號或帳號';
      search.autocomplete = 'off';
      wrap.insertBefore(search, select);
      search.addEventListener('input', () => populateAudienceKey(dialog));
    }
    return select;
  }

  function syncAllowedAudienceTypes(dialog, options) {
    const type = dialog.querySelector('#learning-assignment-audience-type');
    if (!type) return;
    const allowed = new Set(Array.isArray(options?.allowedAssigneeTypes) ? options.allowedAssigneeTypes : ['group']);
    const labels = {group: '目前組別', user: '指定人員', all: '全體人員'};
    const previous = allowed.has(type.value) ? type.value : (allowed.has('group') ? 'group' : [...allowed][0]);
    type.replaceChildren(...[...allowed].map(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = labels[value] || value;
      return option;
    }));
    if (previous) type.value = previous;
  }

  function populateAudienceKey(dialog) {
    const select = dialog.querySelector('#learning-assignment-audience-key');
    const type = dialog.querySelector('#learning-assignment-audience-type')?.value || 'group';
    const label = dialog.querySelector('#learning-assignment-audience-key-label');
    const search = dialog.querySelector('#learning-assignment-person-search-1014');
    const options = dialog._teacherAudienceOptions || {};
    const state = dialog._assignmentState || {};
    if (!select || select.tagName !== 'SELECT') return;

    if (type === 'all') {
      if (label) label.textContent = '全體人員';
      if (search) search.classList.add('hidden');
      select.disabled = true;
      select.replaceChildren(new Option('全體人員', ''));
      return;
    }

    select.disabled = false;
    if (type === 'group') {
      if (label) label.textContent = '組別';
      if (search) search.classList.add('hidden');
      const groups = Array.isArray(options.groups) ? options.groups : [];
      // The course's original group is the valid target for this course. Keep it first
      // and do not offer choices that the server would reject or learners could not resolve.
      const current = String(options.group || state.group || '').trim();
      const valid = groups.filter(item => !current || String(item.key) === current);
      select.replaceChildren(...(valid.length ? valid : groups).map(item => new Option(item.label || item.key, item.key)));
      if ([...select.options].some(item => item.value === current)) select.value = current;
      return;
    }

    if (label) label.textContent = '指定人員';
    if (search) search.classList.remove('hidden');
    const query = String(search?.value || '').trim().toLowerCase();
    const people = (Array.isArray(options.people) ? options.people : []).filter(person => {
      if (!query) return true;
      return [person.name, person.empId, person.username].some(value => String(value || '').toLowerCase().includes(query));
    });
    const previous = select.value;
    if (!people.length) {
      select.replaceChildren(new Option(query ? '找不到符合的人員' : '此組目前沒有可指派人員', ''));
      return;
    }
    select.replaceChildren(new Option('請選擇人員', ''), ...people.map(person => new Option(personOptionLabel(person), person.username)));
    if ([...select.options].some(item => item.value === previous)) select.value = previous;
  }

  async function refreshAssignmentDialog(dialog) {
    if (!canAssign || !dialog?.open) return;
    replaceAudienceInput(dialog);
    const state = dialog._assignmentState || {};
    const area = String(state.area || 'internal');
    const group = String(state.group || '');
    const status = dialog.querySelector('#learning-assignment-status');
    try {
      const options = await fetchAudienceOptions(area, group);
      if (!dialog.open) return;
      dialog._teacherAudienceOptions = options;
      syncAllowedAudienceTypes(dialog, options);
      populateAudienceKey(dialog);
    } catch (error) {
      if (status) status.textContent = `❌ 指派對象讀取失敗：${error.message}`;
    }
  }

  function upgradeAssignmentDialog(dialog) {
    if (!dialog || dialog.dataset.teacherPicker1014 === '1') return;
    dialog.dataset.teacherPicker1014 = '1';
    replaceAudienceInput(dialog);
    dialog.querySelector('#learning-assignment-audience-type')?.addEventListener('change', () => {
      queueMicrotask(() => populateAudienceKey(dialog));
    });
    const observer = new MutationObserver(() => {
      if (dialog.open) void refreshAssignmentDialog(dialog);
    });
    observer.observe(dialog, {attributes: true, attributeFilter: ['open']});
    if (dialog.open) void refreshAssignmentDialog(dialog);
  }

  function courseRowsFromHub() {
    const box = document.getElementById('admin-course-material-hub');
    if (!box) return [];
    const scopedCourses = box._learningAssignmentState?.courses;
    if (Array.isArray(scopedCourses)) return scopedCourses.map(course => ({
      id: String(course.id || '').trim(),
      title: String(course.title || '未命名課程').trim()
    })).filter(course => course.id);
    return Array.from(box.querySelectorAll('.admin-course-list > details')).map(details => {
      const assign = details.querySelector('[data-learning-assign-course]');
      const id = String(assign?.dataset.learningAssignCourse || '').trim();
      const titleNode = details.querySelector(':scope > summary .font-black');
      const title = String(titleNode?.textContent || '未命名課程').replace(/^📘\s*/, '').trim();
      return id ? {id, title} : null;
    }).filter(Boolean);
  }

  function ensureBatchDialog() {
    let dialog = document.getElementById('teacher-batch-assignment-dialog-1014');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'teacher-batch-assignment-dialog-1014';
    dialog.className = 'v561-profile-dialog';
    dialog.innerHTML = `
      <form id="teacher-batch-assignment-form-1014" class="v561-profile-card">
        <div class="v561-profile-head"><div><strong>批次管理課程</strong><span>一次設定多門課程的學習指派</span></div><button type="button" data-batch-close aria-label="關閉">×</button></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div class="flex items-center justify-between gap-2"><b class="text-sm text-slate-800">選擇課程</b><button type="button" id="teacher-batch-select-all-1014" class="text-xs font-bold text-teal-700">全選／取消全選</button></div>
          <div id="teacher-batch-course-list-1014" class="mt-2 max-h-48 overflow-auto space-y-1"></div>
        </div>
        <label><span>指派對象</span><select id="teacher-batch-audience-type-1014"></select></label>
        <label id="teacher-batch-audience-wrap-1014"><span id="teacher-batch-audience-label-1014">組別</span><input id="teacher-batch-person-search-1014" type="search" class="hidden" placeholder="搜尋姓名、工號或帳號"><select id="teacher-batch-audience-key-1014"></select></label>
        <label><span>課程性質</span><select id="teacher-batch-requirement-1014"><option value="required">必修</option><option value="elective">選修</option></select></label>
        <label><span>完成期限</span><input id="teacher-batch-due-1014" type="date"></label>
        <p id="teacher-batch-status-1014" class="v561-profile-status">可一次建立多門課程指派；已存在的相同指派會自動略過。</p>
        <div class="v561-profile-actions"><button type="button" data-batch-close class="secondary">取消</button><button type="submit">套用到已選課程</button></div>
      </form>`;
    document.body.appendChild(dialog);

    const close = () => { try { dialog.close(); } catch (_) { dialog.removeAttribute('open'); } };
    dialog.querySelectorAll('[data-batch-close]').forEach(button => button.addEventListener('click', close));
    dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
    dialog.querySelector('#teacher-batch-select-all-1014')?.addEventListener('click', () => {
      const boxes = Array.from(dialog.querySelectorAll('[data-batch-course]'));
      const shouldCheck = boxes.some(box => !box.checked);
      boxes.forEach(box => { box.checked = shouldCheck; });
    });
    dialog.querySelector('#teacher-batch-audience-type-1014')?.addEventListener('change', () => populateBatchAudience(dialog));
    dialog.querySelector('#teacher-batch-person-search-1014')?.addEventListener('input', () => populateBatchAudience(dialog));
    dialog.querySelector('#teacher-batch-assignment-form-1014')?.addEventListener('submit', event => void submitBatch(event, dialog));
    return dialog;
  }

  function populateBatchAudience(dialog) {
    const options = dialog._teacherAudienceOptions || {};
    const type = dialog.querySelector('#teacher-batch-audience-type-1014')?.value || 'group';
    const select = dialog.querySelector('#teacher-batch-audience-key-1014');
    const search = dialog.querySelector('#teacher-batch-person-search-1014');
    const label = dialog.querySelector('#teacher-batch-audience-label-1014');
    if (!select) return;
    if (type === 'all') {
      if (label) label.textContent = '全體人員';
      search?.classList.add('hidden');
      select.disabled = true;
      select.replaceChildren(new Option('全體人員', ''));
      return;
    }
    select.disabled = false;
    if (type === 'group') {
      if (label) label.textContent = '組別';
      search?.classList.add('hidden');
      const current = String(options.group || '').trim();
      const groups = (Array.isArray(options.groups) ? options.groups : []).filter(item => !current || String(item.key) === current);
      select.replaceChildren(...groups.map(item => new Option(item.label || item.key, item.key)));
      if ([...select.options].some(item => item.value === current)) select.value = current;
      return;
    }
    if (label) label.textContent = '指定人員';
    search?.classList.remove('hidden');
    const query = String(search?.value || '').trim().toLowerCase();
    const people = (Array.isArray(options.people) ? options.people : []).filter(person => !query || [person.name, person.empId, person.username].some(value => String(value || '').toLowerCase().includes(query)));
    select.replaceChildren(new Option(people.length ? '請選擇人員' : '找不到符合的人員', ''), ...people.map(person => new Option(personOptionLabel(person), person.username)));
  }

  async function openBatchDialog() {
    if (!canAssign) return;
    const dialog = ensureBatchDialog();
    const hub = document.getElementById('admin-course-material-hub');
    let courses = courseRowsFromHub();
    const status = dialog.querySelector('#teacher-batch-status-1014');
    // Switching training area repaints the hub asynchronously.  Do not turn a
    // click made during that repaint into a silent no-op; wait once for the
    // current scoped refresh and keep the dialog responsive either way.
    if (!courses.length && hub?._adminCourseMaterialRefresh) {
      if (status) status.textContent = '正在載入此訓練區的課程…';
      if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
      else dialog.setAttribute('open', '');
      await Promise.resolve(hub._adminCourseMaterialRefresh);
      courses = courseRowsFromHub();
    }
    if (!courses.length) {
      if (status) status.textContent = '此訓練區目前沒有可批次管理的課程。';
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const area = document.getElementById('wizard-area')?.value || params.get('area') || 'internal';
    const group = document.getElementById('wizard-group')?.value || params.get('group') || 'grpBio';
    const list = dialog.querySelector('#teacher-batch-course-list-1014');
    list.innerHTML = courses.map(course => `<label class="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white"><input type="checkbox" data-batch-course value="${escapeHtml(course.id)}" checked><span class="text-sm text-slate-700">${escapeHtml(course.title)}</span></label>`).join('');
    if (status) status.textContent = '讀取可指派對象…';
    try {
      const options = await fetchAudienceOptions(area, group);
      dialog._teacherAudienceOptions = options;
      const type = dialog.querySelector('#teacher-batch-audience-type-1014');
      const allowed = Array.isArray(options.allowedAssigneeTypes) ? options.allowedAssigneeTypes : ['group'];
      const labels = {group:'目前組別', user:'指定人員', all:'全體人員'};
      type.replaceChildren(...allowed.map(value => new Option(labels[value] || value, value)));
      populateBatchAudience(dialog);
      if (status) status.textContent = `已選 ${courses.length} 門課程，可取消不需處理的課程。`;
    } catch (error) {
      if (status) status.textContent = `❌ ${error.message}`;
    }
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  async function submitBatch(event, dialog) {
    event.preventDefault();
    const selected = Array.from(dialog.querySelectorAll('[data-batch-course]:checked')).map(box => box.value).filter(Boolean);
    const status = dialog.querySelector('#teacher-batch-status-1014');
    if (!selected.length) {
      if (status) status.textContent = '請至少選擇一門課程。';
      return;
    }
    const type = dialog.querySelector('#teacher-batch-audience-type-1014')?.value || 'group';
    const key = type === 'all' ? '' : String(dialog.querySelector('#teacher-batch-audience-key-1014')?.value || '').trim();
    if (type !== 'all' && !key) {
      if (status) status.textContent = type === 'user' ? '請選擇指定人員。' : '請選擇組別。';
      return;
    }
    const required = dialog.querySelector('#teacher-batch-requirement-1014')?.value !== 'elective';
    const dueAt = dialog.querySelector('#teacher-batch-due-1014')?.value || '';
    const submit = dialog.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    let created = 0, skipped = 0, failed = 0;
    for (let index = 0; index < selected.length; index += 1) {
      if (status) status.textContent = `處理中 ${index + 1}/${selected.length}…`;
      try {
        const response = await fetch('/api/learning-assignments', {
          method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({courseId:selected[index], assigneeType:type, assigneeKey:key, required, dueAt}),
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 409 && data.code === 'ASSIGNMENT_EXISTS') { skipped += 1; continue; }
        if (!response.ok) throw new Error(data.error || '建立指派失敗');
        created += 1;
      } catch (_) {
        failed += 1;
      }
    }
    if (submit) submit.disabled = false;
    if (status) status.textContent = `完成：新增 ${created}、已存在略過 ${skipped}${failed ? `、失敗 ${failed}` : ''}。`;
    audienceCache.clear();
    await window.renderAdminCourseMaterialHub?.(true);
    if (!failed) setTimeout(() => { try { dialog.close(); } catch (_) {} }, 900);
  }

  function ensureBatchEntry() {
    if (!canAssign) return;
    const entry = document.getElementById('teacher-course-media-entry-1014');
    const box = document.getElementById('admin-course-material-hub');
    if (!box || document.getElementById('teacher-batch-manage-1014')) return;
    const button = document.createElement('button');
    button.id = 'teacher-batch-manage-1014';
    button.type = 'button';
    button.className = 'shrink-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-black text-slate-600 hover:bg-slate-50';
    button.textContent = '批次指派';
    button.addEventListener('click', event => { event.preventDefault(); void openBatchDialog(); });
    if (entry) {
      let actions = entry.querySelector('[data-teacher-course-actions-1014]');
      if (!actions) {
        actions = document.createElement('div');
        actions.dataset.teacherCourseActions1014 = '1';
        actions.className = 'flex flex-wrap gap-2';
        const mediaButton = entry.querySelector('button');
        if (mediaButton) actions.appendChild(mediaButton);
        entry.appendChild(actions);
      }
      actions.appendChild(button);
    } else {
      const dashboard = box.querySelector('.admin-course-dashboard');
      if (!dashboard) return;
      const row = document.createElement('div');
      row.className = 'mb-2 flex justify-end';
      row.appendChild(button);
      box.insertBefore(row, dashboard);
    }
  }

  async function playVoicePreview(voice, button, status, audio) {
    if (!voice) return;
    const cached = previewCache.get(voice);
    if (cached) {
      audio.src = cached;
      audio.classList.remove('hidden');
      button.textContent = '▶ 播放試聽';
      try {
        await audio.play();
        if (status) status.textContent = `${voiceLabel(voice)}｜正在播放`;
      } catch (_) {
        if (status) status.textContent = `${voiceLabel(voice)}｜試聽已準備，可直接播放`;
      }
      return;
    }

    const original = button.textContent;
    let prepared = false;
    let backgroundPending = false;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = '產生中…';
    if (status) status.textContent = '正在準備短版試聽…';

    try {
      const first = await fetchJsonWithTimeout('/api/media-audio/preview', {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({voice})
      }, 12000);
      const jobId = first.jobId || '';
      let completed = first.status === 'completed' ? first : null;
      if (!completed && !jobId) throw new Error('沒有取得試聽工作 ID');

      const deadline = Date.now() + 45000;
      let transientTimeouts = 0;
      while (!completed && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 700));
        try {
          const data = await fetchJsonWithTimeout(
            `/api/media-audio/jobs/${encodeURIComponent(jobId)}`,
            {credentials:'same-origin', cache:'no-store'},
            8000
          );
          transientTimeouts = 0;
          if (data.status === 'failed') throw new Error(data.error || '語音試聽產生失敗');
          if (data.status === 'completed') { completed = data; break; }
          if (status) status.textContent = '正在準備短版試聽…';
        } catch (error) {
          if (!String(error?.message || '').includes('回應逾時')) throw error;
          transientTimeouts += 1;
          if (transientTimeouts >= 3) {
            backgroundPending = true;
            break;
          }
          if (status) status.textContent = '連線較慢，仍在準備試聽…';
        }
      }

      const url = completed?.result?.previewUrl || '';
      if (!url) {
        backgroundPending = true;
        if (status) status.textContent = '第一次載入較久，試聽會在背景完成；稍後再按一次即可。';
        return;
      }

      previewCache.set(voice, url);
      audio.pause?.();
      audio.src = url;
      audio.classList.remove('hidden');
      audio.load?.();
      prepared = true;
      button.textContent = '▶ 播放試聽';
      try {
        await audio.play();
        if (status) status.textContent = `${voiceLabel(voice)}｜正在播放`;
      } catch (_) {
        if (status) status.textContent = `${voiceLabel(voice)}｜試聽已準備，可直接播放`;
      }
    } catch (error) {
      const timedOut = String(error?.message || '').includes('回應逾時');
      if (status) status.textContent = timedOut
        ? '連線較慢，試聽仍會在背景完成；稍後再按一次即可。'
        : `❌ ${error.message}`;
      backgroundPending = timedOut;
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      if (!prepared) button.textContent = backgroundPending ? '▶ 再試一次' : original;
    }
  }

  function ensureVoicePreview() {
    if (!canManageMaterial || document.getElementById('teacher-audio-preview-1014')) return;
    const select = document.getElementById('teacher-audio-voice-1014');
    if (!select) return;
    const sharedStatus = document.getElementById('teacher-audio-status-1014');
    const host = document.createElement('div');
    host.id = 'teacher-audio-preview-1014';
    host.className = 'mt-2 flex flex-wrap items-center gap-2';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-black text-emerald-700';
    button.textContent = '▶ 試聽聲音';
    const audio = document.createElement('audio');
    audio.controls = true;
    audio.preload = 'none';
    audio.className = 'hidden h-9 max-w-full';
    host.append(button, audio);
    audio.addEventListener('error', () => {
      if (sharedStatus) sharedStatus.textContent = '❌ 語音檔無法播放；請確認 R2 回應為 audio/wav，且 CSP 允許該 HTTPS 網址。';
    });
    select.insertAdjacentElement('afterend', host);
    const setFormalBusy = event => {
      const busy = Boolean(event?.detail?.busy);
      button.disabled = busy;
      if (busy && sharedStatus) sharedStatus.textContent = '正式 AI 語音工作正在排隊或處理中；完成後即可再次試聽。';
    };
    window.addEventListener('teacher-media-audio-formal-busy-1014', setFormalBusy);
    setFormalBusy({detail:{busy:document.getElementById('teacher-media-audio-1014')?.dataset.formalJobBusy === 'true'}});
    button.addEventListener('click', () => {
      if (document.getElementById('teacher-media-audio-1014')?.dataset.formalJobBusy === 'true') return;
      if (previewAudio && previewAudio !== audio) previewAudio.pause?.();
      previewAudio = audio;
      void playVoicePreview(select.value, button, sharedStatus, audio);
    });
  }

  function collapsePaperGuidance() {
    const paper = document.getElementById('teacher-paper-documents');
    if (!paper || paper.querySelector('#teacher-paper-guidance-1014')) return;
    const children = Array.from(paper.children);
    const header = children[0];
    const template = paper.querySelector('#teacher-paper-template-manager-1014');
    const movable = children.filter(node => node !== header && node !== template);
    if (!movable.length) return;
    const details = document.createElement('details');
    details.id = 'teacher-paper-guidance-1014';
    details.className = 'rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3';
    const summary = document.createElement('summary');
    summary.className = 'flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-black text-slate-700';
    summary.innerHTML = '<span>📄 紙本留存說明與檢核</span><span class="text-xs font-bold text-teal-700" data-paper-guidance-toggle>展開檢核</span>';
    const body = document.createElement('div');
    body.className = 'mt-4 space-y-5';
    const hint = document.createElement('p');
    hint.className = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-600';
    hint.textContent = '列印／匯出前確認文件版本、簽核、日期與留存要求。';
    body.appendChild(hint);
    movable.forEach(node => body.appendChild(node));
    details.append(summary, body);
    details.addEventListener('toggle', () => {
      const toggle = details.querySelector('[data-paper-guidance-toggle]');
      if (toggle) toggle.textContent = details.open ? '收合' : '展開檢核';
    });
    if (template?.parentElement === paper) template.insertAdjacentElement('afterend', details);
    else header?.insertAdjacentElement('afterend', details);
  }

  function collapseWorkspaceSummary() {
    const summary = document.getElementById('admin-workspace-summary');
    if (!summary || document.getElementById('teacher-workspace-help-1014')) return;
    const text = String(summary.textContent || '').trim();
    if (!text) return;
    summary.classList.add('hidden');
    const details = document.createElement('details');
    details.id = 'teacher-workspace-help-1014';
    details.className = 'mt-2 text-xs text-slate-500';
    details.innerHTML = `<summary class="cursor-pointer font-bold text-slate-600">？ 工作區說明</summary><p class="mt-2 leading-5">${escapeHtml(text)}</p>`;
    summary.insertAdjacentElement('afterend', details);
    const observer = new MutationObserver(() => {
      const next = String(summary.textContent || '').trim();
      const target = details.querySelector('p');
      if (target && next) target.textContent = next;
    });
    observer.observe(summary, {childList:true, subtree:true, characterData:true});
  }

  function trimInlineHelp() {
    document.querySelector('#teacher-course-media-entry-1014 p')?.classList.add('hidden');
    document.querySelector('#teacher-review-shortcut-1014 p')?.classList.add('hidden');
  }

  function converge() {
    if (applying) return;
    applying = true;
    try {
      upgradeAssignmentDialog(document.getElementById('learning-assignment-dialog'));
      ensureBatchEntry();
      ensureVoicePreview();
      collapsePaperGuidance();
      collapseWorkspaceSummary();
      trimInlineHelp();
    } finally {
      applying = false;
      scheduled = false;
    }
  }

  function scheduleConverge() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(converge);
  }

  const CONVERGENCE_SURFACE_SELECTOR=[
    '#learning-assignment-dialog',
    '#admin-course-material-hub',
    '#teacher-course-media-entry-1014',
    '#teacher-media-audio-1014',
    '#teacher-paper-documents',
    '#admin-workspace-summary'
  ].join(',');

  function mutationNeedsConverge(record) {
    const target = record?.target instanceof Element ? record.target : record?.target?.parentElement;
    if (target?.closest?.(CONVERGENCE_SURFACE_SELECTOR)) return true;
    return [...(record?.addedNodes || [])].some(node => {
      if (!(node instanceof Element)) return false;
      return node.matches?.(CONVERGENCE_SURFACE_SELECTOR) || Boolean(node.querySelector?.(CONVERGENCE_SURFACE_SELECTOR));
    });
  }

  const observer = new MutationObserver(records => {
    if (records.some(mutationNeedsConverge)) scheduleConverge();
  });
  observer.observe(document.body, {childList:true, subtree:true});
  window.AdminWorkspaceShell?.addAfterWorkspace?.(scheduleConverge);
  [0, 300, 1000, 2500].forEach(delay => setTimeout(scheduleConverge, delay));
})();
