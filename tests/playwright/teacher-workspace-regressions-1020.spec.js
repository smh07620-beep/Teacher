const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';

test('exam settings return button always routes to the assessment manager', async ({ page }) => {
  await page.goto(`${baseURL}/system?admin=1&workspace=assessment`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.switchAdminWorkspace === 'function');
  await page.evaluate(async () => {
    document.getElementById('admin-modal')?.classList.remove('hidden');
    await window.switchAdminWorkspace('assessment', true);
    await window.switchAdminSection('exam-settings', true);
  });
  await page.getByRole('button', { name: '返回考卷管理' }).click();
  await expect(page.locator('#admin-section-quiz')).toBeVisible();
});

test('the workspace recovery does not capture-block the media entry', async ({ page }) => {
  await page.setContent('<button id="teacher-course-media-entry-1014-button">製作語音／錄影</button>');
  const result = await page.evaluate(() => {
    let canonical = 0;
    let recovery = 0;
    window.TeacherWorkspace1014 = { openMedia() { canonical += 1; } };
    document.addEventListener('click', event => {
      const button = event.target.closest?.('#teacher-course-media-entry-1014-button');
      if (!button) return;
      if (typeof window.TeacherWorkspace1014?.openMedia === 'function') return;
      recovery += 1;
      event.stopImmediatePropagation();
    }, true);
    document.getElementById('teacher-course-media-entry-1014-button').addEventListener('click', () => window.TeacherWorkspace1014.openMedia());
    document.getElementById('teacher-course-media-entry-1014-button').click();
    return { canonical, recovery };
  });
  expect(result).toEqual({ canonical: 1, recovery: 0 });
});
