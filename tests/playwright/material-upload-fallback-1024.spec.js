const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
const secureHarnessUrl = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173/';
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('a small course upload falls back to the authorized queue only after R2 network failure', async ({ page }) => {
  // Web Crypto is intentionally required by the production upload client for
  // authenticated file fingerprints/resume safety.  Playwright's about:blank
  // document is not a trustworthy origin, so run this regression on the
  // deterministic localhost harness (localhost is a secure context) before
  // replacing the document body with the minimal fixture.
  await page.goto(secureHarnessUrl);
  await expect.poll(() => page.evaluate(() => Boolean(window.isSecureContext && window.crypto?.subtle))).toBe(true);
  await page.setContent('<main></main>');
  await page.evaluate(() => {
    window.uploadCalls = [];
    window.fetch = async (url, options = {}) => {
      const target = String(url);
      window.uploadCalls.push({ target, method: options.method || 'GET', form: options.body instanceof FormData });
      if (target === '/api/material-upload/init') {
        return new Response(JSON.stringify({
          mode: 'single', uploadId: 'direct-1', jobId: 'direct-job', materialId: 'direct-material',
          url: 'https://r2.example/upload', singlePutMaxBytes: 1024 * 1024
        }), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }
      if (target === 'https://r2.example/upload') throw new TypeError('Failed to fetch');
      if (target === '/api/material-upload/direct-1/abort') return new Response('{}', { status: 200 });
      if (target === '/api/material-jobs/upload') {
        return new Response(JSON.stringify({ accepted: true, status: 'queued', jobId: 'fallback-job' }), {
          status: 202, headers: { 'Content-Type': 'application/json' }
        });
      }
      throw new Error(`unexpected request: ${target}`);
    };
  });
  await page.addScriptTag({ path: asset('material-upload-client.js') });

  const result = await page.evaluate(async () => {
    const form = new FormData();
    form.append('file', new File(['lesson'], 'lesson.pptx', { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }));
    form.append('title', 'Lesson');
    return window.MaterialUploadClient.enqueue(form, { fileName: 'lesson.pptx', fallbackToSameOriginQueue: true });
  });

  expect(result).toMatchObject({ accepted: true, status: 'queued', jobId: 'fallback-job' });
  await expect.poll(() => page.evaluate(() => window.uploadCalls)).toEqual(expect.arrayContaining([
    expect.objectContaining({ target: '/api/material-upload/init', method: 'POST' }),
    expect.objectContaining({ target: 'https://r2.example/upload', method: 'PUT' }),
    expect.objectContaining({ target: '/api/material-jobs/upload', method: 'POST', form: true })
  ]));
});

test('a small upload completes directly when R2 PUT succeeds but ETag is hidden by CORS', async ({ page }) => {
  await page.goto(secureHarnessUrl);
  await expect.poll(() => page.evaluate(() => Boolean(window.isSecureContext && window.crypto?.subtle))).toBe(true);
  await page.setContent('<main></main>');
  await page.evaluate(() => {
    window.uploadCalls = [];
    window.completeBody = null;
    window.fetch = async (url, options = {}) => {
      const target = String(url);
      window.uploadCalls.push({ target, method: options.method || 'GET', form: options.body instanceof FormData });
      if (target === '/api/material-upload/init') {
        return new Response(JSON.stringify({
          mode: 'single', uploadId: 'direct-etag', jobId: 'direct-job-etag', materialId: 'direct-material-etag',
          url: 'https://r2.example/upload-no-etag', singlePutMaxBytes: 1024 * 1024
        }), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }
      if (target === 'https://r2.example/upload-no-etag') return new Response('', { status: 200 });
      if (target === '/api/material-upload/direct-etag/complete') {
        window.completeBody = JSON.parse(String(options.body || '{}'));
        return new Response(JSON.stringify({ accepted: true, status: 'queued', jobId: 'direct-job-etag' }), {
          status: 202, headers: { 'Content-Type': 'application/json' }
        });
      }
      if (target === '/api/material-upload/direct-etag/abort') return new Response('{}', { status: 200 });
      if (target === '/api/material-jobs/upload') {
        throw new Error('same-origin compatibility upload must not run when R2 PUT itself succeeded');
      }
      throw new Error(`unexpected request: ${target}`);
    };
  });
  await page.addScriptTag({ path: asset('material-upload-client.js') });

  const result = await page.evaluate(async () => {
    const form = new FormData();
    form.append('file', new File(['lesson'], 'lesson.pdf', { type: 'application/pdf' }));
    form.append('title', 'Lesson');
    return window.MaterialUploadClient.enqueue(form, { fileName: 'lesson.pdf', fallbackToSameOriginQueue: true });
  });

  expect(result).toMatchObject({ accepted: true, status: 'queued', jobId: 'direct-job-etag' });
  const calls = await page.evaluate(() => window.uploadCalls);
  expect(calls).toEqual(expect.arrayContaining([
    expect.objectContaining({ target: '/api/material-upload/init', method: 'POST' }),
    expect.objectContaining({ target: 'https://r2.example/upload-no-etag', method: 'PUT' }),
    expect.objectContaining({ target: '/api/material-upload/direct-etag/complete', method: 'POST' })
  ]));
  expect(calls).not.toEqual(expect.arrayContaining([
    expect.objectContaining({ target: '/api/material-jobs/upload' })
  ]));
  const completed = await page.evaluate(() => window.completeBody);
  expect(completed.parts).toHaveLength(1);
  expect(completed.parts[0].etag).toBe('');
  expect(completed.parts[0].sha256).toMatch(/^[a-f0-9]{64}$/);
});


test('teacher material upload waits for the Worker result before saying it is safe to leave', async ({ page }) => {
  await page.goto(secureHarnessUrl);
  await page.setContent(
    '<main>'+
      '<input id="admin-pptx-upload-input" type="file">'+
      '<input id="admin-material-title" value="等待正式完成">'+
      '<input id="admin-material-desc" value="P3 upload acceptance">'+
      '<select id="admin-material-group"><option value="grpBio" selected>生化</option></select>'+
      '<input id="admin-material-category" value="">'+
      '<select id="admin-material-area"><option value="pgy" selected>PGY</option></select>'+
      '<select id="admin-material-course"><option value="course-1" selected>Course</option></select>'+
      '<select id="admin-material-type"><option value="standard" selected>standard</option></select>'+
      '<input id="admin-atlas-category"><input id="admin-atlas-magnification">'+
      '<input id="admin-atlas-interpretation"><input id="admin-atlas-clinical">'+
      '<input id="admin-atlas-differential"><input id="admin-atlas-normality"><input id="admin-atlas-tags">'+
      '<button id="admin-upload-btn">上傳</button>'+
      '<div id="admin-upload-status"></div>'+
    '</main>'
  );
  await page.evaluate(() => {
    window.escapeHtml = value => String(value ?? '');
    window.currentTrainingArea = 'pgy';
    window.renderJobsCalls = 0;
    window.renderMaterialJobs = async () => { window.renderJobsCalls += 1; };
    window.MaterialUploadClient = {
      enqueue: async (_form, options = {}) => {
        options.onProgress?.({ percent: 100, loaded: 6, total: 6 });
        return { accepted: true, status: 'queued', jobId: 'job-wait-1', materialId: 'material-1' };
      },
      directUpload: async () => ({})
    };
    window.materialJobResolver = null;
    window.materialJobDeferred = new Promise(resolve => { window.materialJobResolver = resolve; });
    window.fetch = async url => {
      const target = String(url);
      if (target === '/api/material-jobs?limit=20') {
        return new Response(JSON.stringify({
          workers: [{ workerId: 'hospital-worker', status: 'online', protocolCompatible: true, protocolVersion: 2, minimumProtocolVersion: 2 }],
          averageCompletedDurationSeconds: 30
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (target === '/api/material-jobs/job-wait-1') {
        const payload = await window.materialJobDeferred;
        return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      throw new Error('unexpected request: '+target);
    };
  });
  await page.addScriptTag({ path: asset('admin-material-upload.js') });
  await page.setInputFiles('#admin-pptx-upload-input', {
    name: 'lesson.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('lesson')
  });

  await page.evaluate(() => {
    window.adminUploadPromise = window.adminUploadMaterials();
  });
  await expect(page.locator('#admin-upload-btn')).toBeDisabled();
  await expect(page.locator('#admin-upload-status')).toContainText('請等到全部教材顯示「已完成」再離開');

  await page.evaluate(() => {
    window.materialJobResolver({
      id: 'job-wait-1',
      status: 'completed',
      title: 'lesson.pdf',
      createdAt: new Date().toISOString(),
      completedAt: new Date().toISOString()
    });
  });
  await page.evaluate(() => window.adminUploadPromise);

  await expect(page.locator('#admin-upload-status')).toContainText('已正式完成並寫入教材清單');
  await expect(page.locator('#admin-upload-status')).toContainText('現在可以安全離開或返回課程');
  await expect(page.locator('#admin-upload-btn')).toBeEnabled();
  expect(await page.evaluate(() => window.renderJobsCalls)).toBeGreaterThan(0);
});
