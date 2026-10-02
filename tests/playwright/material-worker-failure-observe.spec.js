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
    page.waitForURL(url => !url.pathname.endsWith('/login'), { timeout: 15000 }),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
}

test('GP-05 real Worker failure is visible and retains the R2 source', async ({ page }) => {
  const saved = JSON.parse(fs.readFileSync('material-fullstack-failure-job.json', 'utf8'));
  await login(page);
  const failed = await expect.poll(async () => {
    return page.evaluate(async jobId => {
      const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      return response.ok ? response.json() : { status: 'http-' + response.status };
    }, saved.jobId);
  }, {
    timeout: 45000,
    intervals: [500, 1000, 1500, 2000],
  }).toMatchObject({
    id: saved.jobId,
    status: 'failed',
    materialId: saved.materialId,
    stagingBackend: 'r2',
    stagingKey: saved.stagingKey,
  });

  const current = await page.evaluate(async jobId => {
    const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    return response.json();
  }, saved.jobId);
  expect(current.error || current.detail).toBeTruthy();

  await page.evaluate(async () => {
    if (typeof window.renderMaterialJobs === 'function') await window.renderMaterialJobs(true);
  });
  const jobs = page.locator('#admin-material-jobs-list');
  await expect(jobs).toContainText('需要處理', { timeout: 15000 });
  await expect(jobs).toContainText('原始檔仍安全保留', { timeout: 15000 });
  await expect(jobs).toContainText('直接重新處理', { timeout: 15000 });
});
