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
        <section id="teacher-media-powerpoint-entry-1018"><div><b>PowerPoint</b><p>舊說明</p></div><button id="teacher-media-open-powerpoint-1018">AI PowerPoint 製作</button></section>
      </section>
    </main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.TeacherMediaSubtitle1014 = {
      selectMaterial: value => { window.subtitleMaterial1023 = value; }
    };
    window.TeacherMediaAudio1014 = {
      loadApprovedScripts: async () => { window.audioReloaded1023 = true; }
    };
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
  await expect(page.locator('#teacher-media-open-powerpoint-1018')).toHaveText('🖥️ 多資料 AI PowerPoint');
  await expect(page.locator('#teacher-media-powerpoint-entry-1018')).toContainText('本頁唯一的 AI PowerPoint 入口');

  await source.selectOption('doc-1');
  await expect.poll(() => page.evaluate(() => window.subtitleMaterial1023)).toBe('doc-1');
  await expect.poll(() => page.evaluate(() => window.audioReloaded1023)).toBe(true);
  await expect(page.locator('#teacher-script-material-1014')).toHaveValue('doc-1');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toBeEnabled();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-1');
});

test('empty media source has one PowerPoint entry and an inline ordinary material upload action', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <label>來源教材／來源內容<select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select></label>
      <p id="teacher-media-next-step-1018"></p>
      <section id="teacher-media-powerpoint-entry-1018"><div><b>PowerPoint</b><p>舊說明</p></div><button id="teacher-media-open-powerpoint-1018">AI PowerPoint 製作</button></section>
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
  await expect(page.locator('#teacher-media-open-powerpoint-1018')).toHaveCount(1);
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
          <section id="teacher-media-powerpoint-entry-1018">
            <div><b>PowerPoint</b><p>舊說明</p></div>
            <button id="teacher-media-open-powerpoint-1018" type="button">AI PowerPoint 製作</button>
          </section>
          <div id="teacher-media-tabs-placeholder">媒體頁籤</div>
        </section>
      </section>
    </main>
  `);
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.oldJumpCalls = 0;
    document.getElementById('teacher-media-open-powerpoint-1018').addEventListener('click', () => {
      window.oldJumpCalls += 1;
    });
    window.fetch = async () => ({ ok: true, json: async () => [] });
    window.TeacherAIMaterial1014 = { paintMaterialOptions: async () => {} };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect.poll(() => page.evaluate(() => Boolean(window.TeacherAIMediaControls1023))).toBe(true);
  await page.locator('#teacher-media-open-powerpoint-1018').click();

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
