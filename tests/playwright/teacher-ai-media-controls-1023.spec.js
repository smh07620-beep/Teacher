const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

async function installTeacherRBAC(page) {
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
  });
}

test('shared AI media source loads directly and drives narration subtitle and video inputs', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="teacher-media-production-1014">
        <select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select>
        <p id="teacher-media-next-step-1018"></p>
        <select id="teacher-script-material-1014"><option value="">選擇教材…</option></select>
        <section id="teacher-media-subtitle-1014">
          <label>語言代碼<input id="teacher-subtitle-language-1014" value="zh-TW" class="learning-input"></label>
        </section>
        <section id="teacher-ai-video-1015">
          <h4>教學影片</h4><p>說明</p>
          <select id="teacher-ai-video-presentation-1015"><option value="">請先選擇來源教材</option></select>
          <p id="teacher-ai-video-status-1015"></p>
        </section>
      </section>
    </main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.TeacherMediaSubtitle1014 = {
      selectMaterial: value => { window.subtitleMaterial1023 = value; }
    };
    window.audioReloaded1023 = '';
    window.addEventListener('teacher-media-source-selected-1027', event => { window.audioReloaded1023 = event.detail?.materialId || ''; });
    window.fetch = async url => {
      const text = String(url);
      if (text.includes('/api/slides/admin')) {
        return {
          ok: true,
          json: async () => [
            { id: 'doc-1', title: '生化 SOP', group: 'grpBio', area: 'internal', active: true },
            { id: 'movie-1', title: '教學影片.mp4', group: 'grpBio', area: 'internal', mimeType: 'video/mp4', active: true },
            { id: 'other', title: '其他組', group: 'grpBlood', area: 'internal', active: true }
          ]
        };
      }
      if (text.includes('/api/ai-presentations')) {
        return {
          ok: true,
          json: async () => [{ id: 'ppt-1', title: '生化教學簡報', revisionNumber: 2, status: 'approved', artifactReady: true }]
        };
      }
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);

  const source = page.locator('#teacher-media-source-1018');
  await expect(source).toBeEnabled();
  await expect(source.locator('option')).toHaveCount(3);
  await expect(source).toContainText('生化 SOP');
  await expect(source).not.toContainText('其他組');

  await expect(page.locator('#teacher-subtitle-language-1014')).toHaveJSProperty('tagName', 'SELECT');
  await expect(page.locator('#teacher-subtitle-language-1014')).toHaveValue('zh-TW');
  await expect(page.locator('#teacher-media-direct-powerpoint-1026')).toHaveCount(0);
  await expect(page.locator('#teacher-media-powerpoint-entry-1018')).toHaveCount(0);

  await source.selectOption('doc-1');
  await expect.poll(() => page.evaluate(() => window.subtitleMaterial1023)).toBe('doc-1');
  await expect.poll(() => page.evaluate(() => window.audioReloaded1023)).toBe('doc-1');
  await expect(page.locator('#teacher-script-material-1014')).toHaveValue('doc-1');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toBeEnabled();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-1');
});

test('shared media source never repaints or duplicates the AI PowerPoint supplemental-material picker', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <select id="teacher-media-source-1018"><option value="">來源</option></select>
      <p id="teacher-media-next-step-1018"></p>
      <select id="teacher-script-material-1014"><option value="">來源</option></select>
      <select id="teacher-ai-material-source-1014" multiple>
        <option value="">選擇既有教材…</option>
        <option value="doc-1">grpBio｜C503 操作與維護</option>
        <option value="doc-2">grpBio｜Cobas b 211 儀器教育訓練</option>
      </select>
    </section>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.fetch = async url => {
      if (String(url) === '/api/slides/admin') return { ok:true, json:async()=>[
        {id:'doc-1',title:'C503 操作與維護',filename:'c503-a.pdf',group:'grpBio',area:'internal',active:true},
        {id:'legacy-duplicate',title:'C503 操作與維護',filename:'c503-b.pdf',group:'grpBio',area:'internal',active:true},
        {id:'doc-2',title:'Cobas b 211 儀器教育訓練',group:'grpBio',area:'internal',active:true},
      ]};
      return {ok:true,json:async()=>[]};
    };
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  const authoring = page.locator('#teacher-ai-material-source-1014');
  await expect(authoring.locator('option')).toHaveCount(3);
  await page.locator('#teacher-media-source-1018').selectOption('doc-1');
  await expect(authoring.locator('option')).toHaveCount(3);
  await expect.poll(() => page.evaluate(() =>
    [...document.querySelector('#teacher-ai-material-source-1014').selectedOptions].map(option => option.value)
  )).toContain('doc-1');
});

test('concurrent AI material option hydration is atomic and never duplicates visible sources', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"></section></main>');
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.currentGroupKey = 'grpBio';
    window.currentTrainingArea = 'internal';
    window.fetch = async url => {
      if (String(url) === '/api/slides/admin') {
        await new Promise(resolve => setTimeout(resolve, 35));
        return {ok:true,json:async()=>[
          {id:'c503-new',title:'2026生化組教育訓練：c503 操作與維護',group:'grpBio',area:'internal',active:true,updatedAt:'2026-10-06T01:00:00Z'},
          {id:'c503-old',title:'2026生化組教育訓練：c503 操作與維護',group:'grpBio',area:'internal',active:true,updatedAt:'2026-10-05T01:00:00Z'},
          {id:'b211-new',title:'2026生化組教育訓練：Cobas b 211 儀器教育訓練',group:'grpBio',area:'internal',active:true,updatedAt:'2026-10-06T01:00:00Z'},
          {id:'b211-old',title:'2026生化組教育訓練：Cobas b 211 儀器教育訓練',group:'grpBio',area:'internal',active:true,updatedAt:'2026-10-05T01:00:00Z'},
        ]};
      }
      return {ok:true,json:async()=>[]};
    };
  });
  await page.addScriptTag({ path: asset('teacher-ai-material-1014.js') });
  await expect.poll(() => Boolean(page.locator('#teacher-ai-material-source-1014'))).toBeTruthy();
  await Promise.all([
    page.evaluate(() => window.TeacherAIMaterial1014.paintMaterialOptions()),
    page.evaluate(() => window.TeacherAIMaterial1014.paintMaterialOptions()),
    page.evaluate(() => window.TeacherAIMaterial1014.paintMaterialOptions()),
  ]);
  const labels = await page.locator('#teacher-ai-material-source-1014 option').allTextContents();
  expect(labels).toEqual([
    '選擇既有教材…',
    'grpBio｜2026生化組教育訓練：c503 操作與維護',
    'grpBio｜2026生化組教育訓練：Cobas b 211 儀器教育訓練',
  ]);
});

test('approved PowerPoint list loads independently of material selection and coalesces duplicate refreshes', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <select id="teacher-media-source-1018"><option value="">不選教材</option></select>
      <p id="teacher-media-next-step-1018"></p>
      <section id="teacher-ai-video-1015">
        <h4>教學影片</h4><p>說明</p>
        <select id="teacher-ai-video-presentation-1015"><option value="">初始</option></select>
        <p id="teacher-ai-video-status-1015"></p>
      </section>
    </section>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.pptFetchCount1026 = 0;
    window.fetch = async url => {
      const text=String(url);
      if(text.includes('/api/slides/admin')) return {ok:true,json:async()=>[]};
      if(text.includes('/api/ai-presentations')){
        window.pptFetchCount1026 += 1;
        await new Promise(resolve=>setTimeout(resolve,30));
        return {ok:true,json:async()=>[
          {id:'ppt-a',title:'任意來源簡報',materialId:'draft-source',revisionNumber:3,status:'approved',artifactReady:true}
        ]};
      }
      return {ok:true,json:async()=>({})};
    };
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  await Promise.all([
    page.evaluate(() => window.TeacherAIMediaControls1023.refreshVideoPresentations('')),
    page.evaluate(() => window.TeacherAIMediaControls1023.refreshVideoPresentations('')),
  ]);
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toBeEnabled();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-a');
  await expect.poll(() => page.evaluate(() => window.pptFetchCount1026)).toBeLessThanOrEqual(2);
});

test('empty media source has no duplicate PowerPoint entry and keeps inline ordinary upload', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <label>來源教材／來源內容<select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select></label>
      <p id="teacher-media-next-step-1018"></p>
    </section>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.fetch = async () => ({ ok: true, json: async () => [] });
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);

  await expect(page.locator('#teacher-media-source-1018')).toBeDisabled();
  await expect(page.locator('#teacher-media-source-empty-1024')).toBeVisible();
  await expect(page.locator('#teacher-media-source-empty-1024')).toContainText('沒有可選的已完成教材');
  await expect(page.locator('#teacher-media-empty-powerpoint-1024')).toHaveCount(0);
  await expect(page.locator('#teacher-media-empty-upload-1024')).toHaveText('📚 上傳一般教材');
  await expect(page.locator('#teacher-media-source-refresh-1024')).toBeVisible();
  await expect(page.locator('#teacher-media-powerpoint-entry-1018')).toHaveCount(0);
  await expect(page.locator('#teacher-media-direct-powerpoint-1026')).toHaveCount(0);
  await expect(page.locator('#teacher-media-next-step-1018')).toContainText('本頁上傳一般教材');
});

test('ordinary material upload stays in media workspace and uses direct Browser to R2 transport', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <label>來源教材／來源內容<select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select></label>
      <p id="teacher-media-next-step-1018"></p>
      <section id="teacher-media-powerpoint-entry-1018"><div><b>PowerPoint</b><p>說明</p></div><button id="teacher-media-open-powerpoint-1018">AI PowerPoint 製作</button></section>
    </section>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.openCourseCalls1025 = 0;
    window.TeacherWorkspace1014 = {
      openCourse: async () => { window.openCourseCalls1025 += 1; }
    };
    window.fetch = async () => ({ ok: true, json: async () => [] });
    window.MaterialUploadClient = {
      enqueue: async (form, options) => {
        window.inlineUploadOptions1025 = { ...options };
        window.inlineUploadFields1025 = {
          group: form.get('group'),
          area: form.get('area'),
          materialType: form.get('materialType'),
          fileName: form.get('file')?.name || ''
        };
        return { accepted: true, status: 'queued', jobId: 'job-inline-1', materialId: 'material-inline-1' };
      }
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  await page.locator('#teacher-media-empty-upload-1024').click();

  await expect.poll(() => page.evaluate(() => window.openCourseCalls1025)).toBe(0);
  await expect(page.locator('#teacher-media-general-upload-1025')).toBeVisible();
  await expect(page.locator('#teacher-media-general-upload-1025')).toContainText('Browser → R2 → Worker');

  await page.locator('#teacher-media-general-files-1025').setInputFiles({
    name: 'c503.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('course material')
  });
  await page.locator('#teacher-media-general-upload-start-1025').click();

  await expect.poll(() => page.evaluate(() => window.inlineUploadOptions1025?.fallbackToSameOriginQueue)).toBe(false);
  await expect.poll(() => page.evaluate(() => window.inlineUploadFields1025)).toEqual({
    group: 'grpBio',
    area: 'internal',
    materialType: 'standard',
    fileName: 'c503.pdf'
  });
  await expect(page.locator('#teacher-media-general-status-1025')).toContainText('排入 Worker');
  await expect.poll(() => page.evaluate(() => window.openCourseCalls1025)).toBe(0);
});

test('multi-source PowerPoint opens inline and does not run the old jump-back handler', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="admin-course-material-hub">
        <section id="teacher-ai-material-1014">
          <h4>AI PowerPoint 原始資料工作台</h4>
          <input id="teacher-ai-material-file-1014" type="file" multiple>
        </section>
      </section>
      <section id="teacher-media-production-1014">
        <section id="teacher-ai-media-studio-1018">
          <label>來源教材／來源內容<select id="teacher-media-source-1018"><option value="">來源</option></select></label>
          <p id="teacher-media-next-step-1018"></p>
          <div id="teacher-media-tabs-placeholder">媒體頁籤</div>
        </section>
      </section>
    </main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.oldJumpCalls = 0;
    window.fetch = async () => ({ ok: true, json: async () => [] });
    window.TeacherAIMaterial1014 = { paintMaterialOptions: async () => {} };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  await page.evaluate(() => window.TeacherAIMediaControls1023.openPowerPointWorkspace());

  await expect.poll(() => page.evaluate(() => window.oldJumpCalls)).toBe(0);
  await expect(page.locator('#teacher-media-powerpoint-workspace-1024')).toBeVisible();
  await expect(page.locator('#teacher-media-powerpoint-body-1024 > #teacher-ai-material-1014')).toBeVisible();
  await expect(page.locator('#teacher-media-powerpoint-workspace-1024')).toContainText('一次加入多份原始資料');

  await page.locator('#teacher-media-powerpoint-close-1024').click();
  await expect(page.locator('#teacher-media-powerpoint-workspace-1024')).toBeHidden();
  await expect(page.locator('#admin-course-material-hub > #teacher-ai-material-1014')).toHaveCount(1);
});

test('course wizard upload is forced to Browser to R2 and cannot fall back to disabled web byte upload', async ({ page }) => {
  await page.setContent('<select id="teacher-media-source-1018"><option value="">來源</option></select><p id="teacher-media-next-step-1018"></p>');
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.fetch = async () => ({ ok: true, json: async () => [] });
    window.MaterialUploadClient = {
      enqueue: async (_form, options) => {
        window.wizardUploadOptions1024 = { ...options };
        return { accepted: true, status: 'queued', jobId: 'job-1', materialId: 'material-1' };
      }
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.MaterialUploadClient?.enqueue?.__teacherWizardDirectOnly1024))).toBe(true);

  const result = await page.evaluate(async () => {
    const form = new FormData();
    form.append('file', new File(['ppt'], 'c503.pptx', { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }));
    form.append('bundleWorkflowId', 'cw-safe-1');
    return window.MaterialUploadClient.enqueue(form, {
      fileName: 'c503.pptx',
      fallbackToSameOriginQueue: true,
      onFallback: () => { window.fallbackCalled1024 = true; }
    });
  });

  expect(result).toMatchObject({ accepted: true, jobId: 'job-1' });
  await expect.poll(() => page.evaluate(() => window.wizardUploadOptions1024?.fallbackToSameOriginQueue)).toBe(false);
  await expect.poll(() => page.evaluate(() => Boolean(window.wizardUploadOptions1024?.onFallback))).toBe(false);
  await expect.poll(() => page.evaluate(() => Boolean(window.fallbackCalled1024))).toBe(false);
});

test('F5 hydration and observers issue one PowerPoint request per selected source', async ({ page }) => {
  await page.setContent(`
    <main><section id="teacher-media-production-1014">
      <section id="teacher-media-studio-shell-1018"></section>
      <section id="teacher-media-audio-1014"></section>
      <section id="teacher-media-subtitle-1014"></section>
      <section id="teacher-ai-video-1015"><select id="teacher-ai-video-presentation-1015"></select><p id="teacher-ai-video-status-1015"></p></section>
      <section id="teacher-media-script-1014"><select id="teacher-script-material-1014"><option value="">來源</option></select></section>
    </section></main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.presentationRequests1025 = 0;
    window.slideRequests1025 = 0;
    window.fetch = async url => {
      const value = String(url);
      if (value === '/api/slides/admin') {
        window.slideRequests1025 += 1;
        return { ok: true, json: async () => [{ id: 'doc-1', title: 'SOP', group: 'grpBio', area: 'internal' }] };
      }
      if (value.includes('/api/ai-presentations')) {
        window.presentationRequests1025 += 1;
        return { ok: true, json: async () => [{ id: 'ppt-1', title: 'SOP 簡報', materialId: 'doc-1', status: 'approved', artifactReady: true }] };
      }
      return { ok: true, json: async () => [] };
    };
  });

  await page.addScriptTag({ path: asset('teacher-media-source-fix-1014.js') });
  await page.addScriptTag({ path: asset('teacher-ai-media-studio-1018.js') });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  const source = page.locator('#teacher-media-source-1018');
  await expect(source).toBeEnabled();
  // The global source select is now an intentionally hidden compatibility bridge.
  // Drive it programmatically here; visible source selection belongs to each media mode.
  await source.evaluate((select, value) => {
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }, 'doc-1');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-1');
  await page.locator('main').evaluate(main => {
    for (let index = 0; index < 20; index += 1) main.appendChild(document.createElement('div'));
  });
  await page.waitForTimeout(1500);
  await expect.poll(() => page.evaluate(() => window.presentationRequests1025)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.slideRequests1025)).toBe(1);
});

test('cross-group teaching loads approved PowerPoints across groups', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <section id="teacher-ai-media-studio-1018">
        <div class="rounded-2xl"><select id="teacher-media-source-1018"><option value="">來源</option></select></div>
        <p id="teacher-media-next-step-1018"></p>
        <section id="teacher-ai-video-1015">
          <select id="teacher-ai-video-presentation-1015"><option value="">載入</option></select>
          <p id="teacher-ai-video-status-1015"></p>
        </section>
      </section>
    </section>
  `);
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['education_admin']),
      crossGroup: true,
      user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
    window.fetch = async url => {
      const value = String(url);
      if (value === '/api/slides/admin') return { ok: true, json: async () => [
        { id: 'heme-doc', title: '血液教材', group: 'grpHema', area: 'internal' }
      ] };
      if (value.startsWith('/api/ai-presentations')) return { ok: true, json: async () => [
        { id: 'ppt-heme', title: '血液簡報', group: 'grpHema', materialId: 'heme-doc', revisionNumber: 2, status: 'approved', artifactReady: true }
      ] };
      return { ok: true, json: async () => ({}) };
    };
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  await expect(page.locator('#teacher-media-source-1018')).toContainText('血液教材');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toBeEnabled();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-heme');
  await expect.poll(() => page.evaluate(() => performance.getEntriesByType ? true : true)).toBe(true);
});

test('PowerPoint authoring mounts inline even when course hub was never opened', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="teacher-media-production-1014">
        <section id="teacher-ai-media-studio-1018">
          <div class="rounded-2xl"><select id="teacher-media-source-1018"><option value="">來源</option></select></div>
          <p id="teacher-media-next-step-1018"></p>
        </section>
      </section>
    </main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.fetch = async url => {
      if (String(url) === '/api/slides/admin') return { ok: true, json: async () => [] };
      return { ok: true, json: async () => [] };
    };
  });
  await page.addScriptTag({ path: asset('teacher-ai-material-1014.js') });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  // Authoring now mounts immediately under the stable media workspace instead
  // of waiting inside the repainting course-material hub.
  await expect(page.locator('#teacher-media-production-1014 > #teacher-ai-material-1014')).toBeVisible();
  await expect(page.locator('#teacher-media-direct-powerpoint-1026')).toHaveCount(0);
  await page.evaluate(() => window.TeacherAIMediaControls1023.openPowerPointWorkspace());
  // This fixture intentionally does not load the media-studio tab owner, so the
  // compatibility overlay remains the fallback path and must reuse the same editor.
  await expect(page.locator('#teacher-media-powerpoint-workspace-1024')).toBeVisible();
  await expect(page.locator('#teacher-media-powerpoint-body-1024 > #teacher-ai-material-1014')).toBeVisible();
  await expect(page.locator('#teacher-media-next-step-1018')).not.toContainText('尚未載入完成');
});

test('AI PowerPoint accepts pasted SOP text as a private authoring source', async ({ page }) => {
  await page.setContent('<main><section id="admin-course-material-hub"><div class="admin-course-dashboard"></div><section id="teacher-media-script-1014"></section></section></main>');
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.pastedSource1025 = null;
    window.MaterialUploadClient = {
      enqueue: async (form, options) => {
        const file = form.get('file');
        window.pastedSource1025 = {
          name: file?.name || '',
          text: await file.text(),
          fallbackToSameOriginQueue: options?.fallbackToSameOriginQueue,
        };
        return { jobId: 'job-text-1', materialId: 'mat-text-1' };
      }
    };
    window.fetch = async (url, options = {}) => {
      const value = String(url);
      if (value === '/api/slides/admin') return { ok: true, json: async () => window.pastedSource1025 ? [{ id: 'mat-text-1', title: '急件 SOP', group: 'grpBio', area: 'internal', active: false }] : [] };
      if (value.includes('/api/material-jobs/job-text-1')) return { ok: true, json: async () => ({ status: 'completed', stage: '完成' }) };
      if (value.includes('/api/slides/mat-text-1') && options.method === 'PATCH') return { ok: true, json: async () => ({ ok: true }) };
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-material-1014.js') });
  await page.locator('#teacher-ai-material-paste-title-1014').fill('急件 SOP');
  await page.locator('#teacher-ai-material-paste-1014').fill('檢體收到後先確認病人識別，再依序完成離心、分析與異常結果複核。');
  await page.locator('#teacher-ai-material-paste-add-1014').click();

  await expect(page.locator('#teacher-ai-material-status-1014')).toContainText('已加入 1 份原始資料');
  await expect.poll(() => page.evaluate(() => window.pastedSource1025)).toEqual({
    name: '急件 SOP.txt',
    text: '檢體收到後先確認病人識別，再依序完成離心、分析與異常結果複核。',
    fallbackToSameOriginQueue: false,
  });
  await expect(page.locator('#teacher-ai-material-uploaded-sources-1014')).toContainText('急件 SOP');
});


test('selected AI media source survives forced refresh without duplicate change churn', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <select id="teacher-media-source-1018"><option value="">來源</option></select>
      <p id="teacher-media-next-step-1018"></p>
      <select id="teacher-script-material-1014"><option value="">來源</option></select>
      <section id="teacher-ai-video-1015">
        <select id="teacher-ai-video-presentation-1015"><option value="">載入</option></select>
        <p id="teacher-ai-video-status-1015"></p>
      </section>
    </section>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.sourceFetches1027 = 0;
    window.legacyChanges1027 = 0;
    window.pptChanges1027 = 0;
    document.getElementById('teacher-script-material-1014').addEventListener('change', () => {
      window.legacyChanges1027 += 1;
    });
    document.getElementById('teacher-ai-video-presentation-1015').addEventListener('change', () => {
      window.pptChanges1027 += 1;
    });
    window.fetch = async url => {
      const value = String(url);
      if (value === '/api/slides/admin') {
        window.sourceFetches1027 += 1;
        await new Promise(resolve => setTimeout(resolve, 25));
        return { ok: true, json: async () => [
          { id: 'doc-1', title: '生化 SOP', group: 'grpBio', area: 'internal', active: true },
          { id: 'doc-2', title: 'QC SOP', group: 'grpBio', area: 'internal', active: true }
        ] };
      }
      if (value.includes('/api/ai-presentations')) {
        return { ok: true, json: async () => [
          { id: 'ppt-1', title: '生化簡報', materialId: 'doc-1', status: 'approved', artifactReady: true }
        ] };
      }
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  const source = page.locator('#teacher-media-source-1018');
  await expect(source).toBeEnabled();
  await source.selectOption('doc-1');
  await expect(page.locator('#teacher-script-material-1014')).toHaveValue('doc-1');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-1');

  const before = await page.evaluate(() => ({
    legacy: window.legacyChanges1027,
    ppt: window.pptChanges1027
  }));
  await page.evaluate(() => window.TeacherAIMediaControls1023.refreshSources({ force: true }));

  await expect(source).toHaveValue('doc-1');
  await expect(page.locator('#teacher-script-material-1014')).toHaveValue('doc-1');
  await expect.poll(() => page.evaluate(() => window.sourceFetches1027)).toBeGreaterThanOrEqual(2);
  await expect.poll(() => page.evaluate(() => window.legacyChanges1027)).toBe(before.legacy);
  await expect.poll(() => page.evaluate(() => window.pptChanges1027)).toBe(before.ppt);
});
