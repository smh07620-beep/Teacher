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

  // Regress the exact teacher-facing action that previously only navigated to
  // the job list without invoking the retry endpoint.
  const retryButton = page.locator(
    `#teacher-action-queue-1024 [data-teacher-action-kind="material_failure"][data-teacher-action-id="${saved.jobId}"]`
  );
  await expect(retryButton).toBeVisible({ timeout: 15000 });
  await expect(retryButton).toHaveText('直接重新處理');
  await retryButton.click();

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
