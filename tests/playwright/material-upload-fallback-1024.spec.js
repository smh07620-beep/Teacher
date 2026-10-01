const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('a small course upload falls back to the authorized queue only after R2 network failure', async ({ page }) => {
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
