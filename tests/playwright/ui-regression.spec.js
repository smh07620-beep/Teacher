const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';
const viewports = [
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-430', width: 430, height: 932 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 1000 },
];

async function assertNoHorizontalOverflow(page) {
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
}

async function open(page, path) {
  await page.goto(`${baseURL}${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(250);
}

for (const viewport of viewports) {
  test(`learner portal layouts stay inside ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    await open(page, '/');
    await expect(page.locator('#hero-title')).toBeVisible();
    await expect(page.locator('.v56-primary')).toContainText('繼續我的學習');
    await expect(page.locator('nav.v56-bottom-nav')).toBeAttached();
    await assertNoHorizontalOverflow(page);

    await open(page, '/internal');
    await expect(page.locator('#internal-training-title')).toBeVisible();
    await expect(page.locator('a[href*="area=internal"]').first()).toBeVisible();
    await assertNoHorizontalOverflow(page);

    await open(page, '/pgy');
    await expect(page.getByRole('heading', { name: 'PGY 教育訓練', exact: true })).toBeVisible();
    await expect(page.locator('a[href*="area=pgy"]').first()).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });
}

test('teacher workspace renders Worker status without layout overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open(page, '/system?area=internal&group=grpBio&module=materials');

  await page.waitForFunction(() => Boolean(window.TeacherRBAC681Ready));
  await page.evaluate(async () => {
    await window.TeacherRBAC681Ready;
    const modal = document.getElementById('admin-modal');
    if (modal) modal.classList.remove('hidden');
    if (typeof window.switchAdminWorkspace === 'function') {
      await window.switchAdminWorkspace('worker', true);
    }
  });

  await expect(page.locator('#admin-section-worker')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#admin-section-worker')).toContainText('Worker / Job 狀態');
  await expect(page.locator('#admin-section-worker')).toContainText('A8B5-TeacherWorker');
  await expect(page.locator('#admin-section-worker')).toContainText('FFmpeg ✓');
  await assertNoHorizontalOverflow(page);
});

test('Worker status error state is distinct from an offline Worker', async ({ page }) => {
  await page.route('**/api/material-jobs?**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        jobs: [],
        workers: [],
        workerStatusAvailable: false,
        workerStatusError: '無法讀取本機 Worker 狀態，請稍後再試或檢查伺服器記錄。',
        pendingJobs: 0,
        processingJobs: 0,
        retryJobs: 0,
        failedJobs: 0,
        recentTerminalJobs: 0,
        recentFailureRate: 0,
        averageCompletedDurationSeconds: 0,
        staging: { backend: 'r2', available: true, shared: true },
      }),
    });
  });
  await page.setViewportSize({ width: 430, height: 932 });
  await open(page, '/system?area=internal&group=grpBio&module=materials');
  await page.waitForFunction(() => Boolean(window.TeacherRBAC681Ready));
  await page.evaluate(async () => {
    await window.TeacherRBAC681Ready;
    const modal = document.getElementById('admin-modal');
    if (modal) modal.classList.remove('hidden');
    if (typeof window.switchAdminWorkspace === 'function') {
      await window.switchAdminWorkspace('worker', true);
    }
  });
  const error = page.locator('[data-worker-status-error]');
  await expect(error).toBeVisible({ timeout: 10000 });
  await expect(error).toContainText('此訊息不代表 Worker 已離線');
  await assertNoHorizontalOverflow(page);
});
