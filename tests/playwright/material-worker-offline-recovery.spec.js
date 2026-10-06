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
  await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
}

test('GP-06 same queued job completes after the real Worker returns', async ({ page }) => {
  const saved = JSON.parse(fs.readFileSync('material-fullstack-offline-job.json', 'utf8'));
  await login(page);

  await expect.poll(async () => {
    return page.evaluate(async jobId => {
      const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (!response.ok) return { status: 'http-' + response.status };
      return response.json();
    }, saved.jobId);
  }, {
    timeout: 60000,
    intervals: [500, 1000, 1500, 2000],
    message: 'same queued job should complete when the canonical Worker returns',
  }).toMatchObject({
    id: saved.jobId,
    status: 'completed',
    materialId: saved.materialId,
    stagingKey: '',
  });

  const material = await page.evaluate(async materialId => {
    const response = await fetch('/api/slides?area=internal', {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    const data = await response.json();
    const rows = Array.isArray(data) ? data : (data.materials || data.slides || []);
    return rows.find(row => row.id === materialId) || null;
  }, saved.materialId);
  expect(material).toBeTruthy();
  expect(material.title).toBe('GP06 Worker 離線恢復教材');
  expect(material.storageBackend).toBe('r2');

  await page.evaluate(async () => {
    if (typeof window.renderAdminCourseMaterialHub === 'function') {
      await window.renderAdminCourseMaterialHub(true);
      const hub = document.getElementById('admin-course-material-hub');
      if (hub?._adminCourseMaterialRefresh) await hub._adminCourseMaterialRefresh;
    }
  });
  await expect(page.locator('body')).toContainText('GP06 Worker 離線恢復教材', { timeout: 15000 });
});
