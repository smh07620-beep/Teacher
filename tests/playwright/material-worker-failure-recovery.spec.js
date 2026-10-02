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

test('GP-05 same retried job succeeds once when the healthy Worker returns', async ({ page }) => {
  const saved = JSON.parse(fs.readFileSync('material-fullstack-failure-job.json', 'utf8'));
  await login(page);
  await expect.poll(async () => {
    return page.evaluate(async jobId => {
      const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      return response.ok ? response.json() : { status: 'http-' + response.status };
    }, saved.jobId);
  }, {
    timeout: 60000,
    intervals: [500, 1000, 1500, 2000],
  }).toMatchObject({
    id: saved.jobId,
    status: 'completed',
    materialId: saved.materialId,
    stagingKey: '',
  });

  const rows = await page.evaluate(async () => {
    const response = await fetch('/api/slides?area=internal', {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    const data = await response.json();
    return Array.isArray(data) ? data : (data.materials || data.slides || []);
  });
  const matches = rows.filter(row => row.id === saved.materialId);
  expect(matches).toHaveLength(1);
  expect(matches[0].title).toBe('GP05 Worker 失敗恢復教材');
  expect(matches[0].storageBackend).toBe('r2');

  await page.evaluate(async () => {
    if (typeof window.renderAdminCourseMaterialHub === 'function') {
      await window.renderAdminCourseMaterialHub(true);
    }
  });
  await expect(page.locator('body')).toContainText('GP05 Worker 失敗恢復教材', { timeout: 15000 });
});
