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

test('GP-05 teacher retries the same failed job without re-uploading', async ({ page }) => {
  const saved = JSON.parse(fs.readFileSync('material-fullstack-failure-job.json', 'utf8'));
  await login(page);
  await page.evaluate(async jobId => {
    if (typeof window.renderMaterialJobs === 'function') await window.renderMaterialJobs(true);
    if (typeof window.retryMaterialJob !== 'function') throw new Error('retryMaterialJob is unavailable');
    await window.retryMaterialJob(jobId);
  }, saved.jobId);

  const retried = await page.evaluate(async jobId => {
    const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    return response.json();
  }, saved.jobId);
  expect(retried.id).toBe(saved.jobId);
  expect(retried.materialId).toBe(saved.materialId);
  expect(retried.status).toBe('queued');
  expect(retried.stagingKey).toBe(saved.stagingKey);
  expect(retried.attempts).toBe(0);
});
