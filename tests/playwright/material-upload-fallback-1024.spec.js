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
