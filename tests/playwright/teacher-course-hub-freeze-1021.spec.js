const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('large internal course scope stays interactive without summary warnings', async ({ page }) => {
  const warnings = [];
  page.on('console', message => {
    if (message.type() === 'warning' && message.text().includes('Interactive element inside')) warnings.push(message.text());
  });
  await page.setContent(`
    <select id="wizard-area"><option value="pgy">PGY</option><option value="internal">院內</option></select>
    <select id="wizard-group"></select>
    <div id="admin-course-material-hub"></div>
  `);
  await page.evaluate(() => {
    window.currentTrainingArea = 'pgy';
    window.currentGroupKey = 'grpBio';
    window.GROUPS = { grpBio: { label: '生化' } };
    window.adminCoursesCache = new Map();
    window.adminMaterialsCache = { data: [], at: Date.now() };
    window.ADMIN_COURSE_CACHE_MS = 0;
    window.ADMIN_CACHE_MS = 0;
    window.adminScopeKey = (area, group) => `${area}:${group}`;
    window.escapeHtml = value => String(value ?? '');
    window.teachingOrderedMaterials = (_course, materials) => materials;
    window.examBankCount = () => 0;
    window.examAudienceLabel = () => '';
    window.examDrawLabel = () => '';
    window.fetchAdminMaterials = async () => [];
    window.TeacherRBAC681Ready = Promise.resolve({ hasPermission: name => ['learning.assign', 'material.manage'].includes(name) });
    window.TeacherWorkspace1014 = { openMedia: () => { window.mediaOpened = true; } };
    window.fetch = async url => {
      if (String(url).startsWith('/api/courses/admin')) {
        const area = new URL(String(url), 'http://localhost').searchParams.get('area');
        return { ok: true, json: async () => Array.from({ length: 1541 }, (_, index) => ({ id: `${area}-${index}`, title: `課程 ${index}`, active: true })) };
      }
      if (String(url).startsWith('/api/learning-assignments/audience-options')) {
        return { ok: true, json: async () => ({ group: 'grpBio', groups: [{ key: 'grpBio', label: '生化' }], allowedAssigneeTypes: ['group'] }) };
      }
      return { ok: true, json: async () => [] };
    };
  });
  for (const name of ['admin-course-material.js', 'admin-question-bank.js', 'teacher-interface-convergence-1014.js', 'teacher-assignment-experience-1014.js']) {
    await page.addScriptTag({ path: asset(name) });
  }
  await page.evaluate(() => window.populateAdminGroupSelects());
  await page.evaluate(async () => {
    await window.renderAdminCourseMaterialHub(true);
    await document.getElementById('admin-course-material-hub')._adminCourseMaterialRefresh;
  });
  await expect(page.locator('.admin-course-list > details')).toHaveCount(30);
  await expect(page.locator('.admin-course-list > details').first().locator('[data-teacher-manage-course-1014]')).toHaveCount(1);
  await expect(page.locator('.admin-course-list > details summary button')).toHaveCount(0);
  const initialNodeCount = await page.locator('#admin-course-material-hub *').count();
  await page.locator('#wizard-area').selectOption('internal');
  await expect.poll(() => page.locator('.admin-course-list > details').first().textContent()).toContain('課程 0');
  await expect(page.locator('.admin-course-list > details').first().locator('[data-learning-assign-course]')).toHaveAttribute('data-learning-assign-course', 'internal-0');
  await page.getByRole('button', { name: /顯示更多課程/ }).click();
  await expect(page.locator('.admin-course-list > details')).toHaveCount(60);
  expect(await page.locator('.admin-course-list > details').evaluateAll(cards => cards.every(card => card.querySelectorAll('[data-teacher-manage-course-1014]').length === 1))).toBe(true);
  for (const area of ['pgy', 'internal', 'pgy', 'internal']) {
    await page.locator('#wizard-area').selectOption(area);
    await expect(page.locator('.admin-course-list > details').first().locator('[data-teacher-manage-course-1014]')).toHaveCount(1);
  }
  await page.evaluate(async () => {
    await document.getElementById('admin-course-material-hub')._adminCourseMaterialRefresh;
    await document.getElementById('admin-course-material-hub')._adminCourseMaterialRefresh;
  });
  const afterRerenderNodeCount = await page.locator('#admin-course-material-hub *').count();
  expect(afterRerenderNodeCount).toBeLessThan(initialNodeCount * 3);
  await page.getByRole('button', { name: '製作語音／錄影' }).click();
  expect(await page.evaluate(() => window.mediaOpened)).toBe(true);
  await page.getByRole('button', { name: '批次管理課程' }).click();
  await expect(page.locator('#teacher-batch-assignment-dialog-1014')).toHaveAttribute('open', '');
  await expect(page.locator('[data-batch-course]')).toHaveCount(1541);
  expect(warnings).toEqual([]);
});
