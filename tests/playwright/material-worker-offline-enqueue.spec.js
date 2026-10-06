const { test, expect } = require('@playwright/test');
const fs = require('fs');

const baseURL = process.env.TEACHER_MATERIAL_FULLSTACK_BASE_URL || 'http://127.0.0.1:4175';
const fixturePassword = process.env.TEACHER_CI_BROWSER_PASSWORD || '';

async function login(page) {
  const next = '/system?area=internal&group=grpBio&admin=1&workspace=course-materials&persona=teacher';
  await page.goto(`${baseURL}/login?next=${encodeURIComponent(next)}`, { waitUntil: 'domcontentloaded' });
  await page.locator('#login-username').fill('gp01teacher');
  await page.locator('#login-password').fill(fixturePassword);
  await Promise.all([
    page.waitForURL(url => !url.pathname.endsWith('/login'), { timeout: 15000, waitUntil: 'commit' }),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
  await page.waitForFunction(() => Boolean(window.MaterialUploadClient?.directUpload), null, { timeout: 30000 });
}

test('GP-06 queues one R2-backed job while the real Worker is offline', async ({ page }) => {
  await login(page);
  const queued = await page.evaluate(async () => {
    const file = new File(
      ['Worker offline recovery full-stack source\n'],
      'worker-offline-recovery.txt',
      { type: 'text/plain', lastModified: 1760000001000 },
    );
    const form = new FormData();
    form.append('file', file);
    form.append('title', 'GP06 Worker 離線恢復教材');
    form.append('desc', '同一 R2 source 在 Worker 回來後繼續處理');
    form.append('group', 'grpBio');
    form.append('area', 'internal');
    form.append('courseId', 'course-full-stack');
    form.append('materialType', 'standard');
    return window.MaterialUploadClient.directUpload(form, { fileName: file.name });
  });
  expect(queued.status).toBe('queued');
  expect(queued.jobId).toBeTruthy();

  const job = await page.evaluate(async jobId => {
    const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    return response.json();
  }, queued.jobId);
  expect(job.id).toBe(queued.jobId);
  expect(job.status).toBe('queued');
  expect(job.stagingBackend).toBe('r2');
  expect(job.stagingKey).toMatch(/^_staging\/material-jobs\/[^/]+\/source\.txt$/);
  expect(job.workerId).toBe('');
  expect(job.materialId).toBeTruthy();

  fs.writeFileSync(
    'material-fullstack-offline-job.json',
    JSON.stringify({
      jobId: job.id,
      materialId: job.materialId,
      stagingKey: job.stagingKey,
    }),
    'utf8',
  );
});
