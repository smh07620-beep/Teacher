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
  await page.getByRole('button', { name: /從教材製作媒體/ }).click();
  expect(await page.evaluate(() => window.mediaOpened)).toBe(true);
  await page.getByRole('button', { name: '批次管理課程' }).click();
  await expect(page.locator('#teacher-batch-assignment-dialog-1014')).toHaveAttribute('open', '');
  await expect(page.locator('[data-batch-course]')).toHaveCount(1541);
  expect(warnings).toEqual([]);
});

test('course hub reconciles a fresh material fetch that loses render ownership', async ({ page }) => {
  await page.setContent(`
    <select id="wizard-area"><option value="internal" selected>院內</option></select>
    <select id="wizard-group"><option value="grpBio" selected>生化</option></select>
    <div id="admin-course-material-hub"></div>
  `);
  await page.evaluate(() => {
    window.currentTrainingArea = 'internal';
    window.currentGroupKey = 'grpBio';
    window.GROUPS = { grpBio: { label: '生化' } };
    window.adminCoursesCache = new Map([['internal:grpBio', { data: [{ id: 'course-1', title: '課程 1', active: true }], at: Date.now() }]]);
    window.adminMaterialsCache = { data: [], at: Date.now() };
    window.ADMIN_COURSE_CACHE_MS = 60000;
    window.ADMIN_CACHE_MS = 60000;
    window.adminScopeKey = (area, group) => `${area}:${group}`;
    window.escapeHtml = value => String(value ?? '');
    window.teachingOrderedMaterials = (_course, materials) => materials;
    window.examBankCount = () => 0;
    window.examAudienceLabel = () => '';
    window.examDrawLabel = () => '';
    window.TeacherRBAC681Ready = Promise.resolve({ hasPermission: name => name === 'material.manage' });
    window.fetchAdminMaterials = async force => {
      if (!force) return window.adminMaterialsCache.data;
      await new Promise(resolve => setTimeout(resolve, 80));
      const rows = [{ id: 'mat-new', title: '剛完成的 Worker 教材', area: 'internal', group: 'grpBio', courseId: 'course-1', active: true }];
      window.adminMaterialsCache = { data: rows, at: Date.now() };
      return rows;
    };
    window.fetch = async () => ({ ok: true, json: async () => [] });
  });
  await page.addScriptTag({ path: asset('admin-course-material.js') });
  await page.evaluate(() => {
    window.renderAdminCourseMaterialHub(true);
    window.renderAdminCourseMaterialHub(false);
  });
  await expect(page.locator('#admin-course-material-hub')).toContainText('剛完成的 Worker 教材', { timeout: 3000 });
});

test('AI media studio keeps one source and one accessible active mode', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"><section id="teacher-media-studio-shell-1018"></section><section id="teacher-media-audio-1014"><h4>語音</h4><p class="mt-1">語音說明</p></section><section id="teacher-media-subtitle-1014"><h4>字幕</h4></section><section id="teacher-ai-video-1015"><h4>影片</h4><p class="mt-1">影片說明</p><label>PowerPoint<input id="teacher-ai-video-presentation-1015"></label><span id="teacher-ai-video-provider-1015"></span><span id="teacher-ai-video-renderer-1015"></span></section><section id="teacher-media-script-1014"><label>來源教材<select id="teacher-script-material-1014"><option value="doc-1">教材文件</option><option value="movie-1">教學影片.mp4</option></select></label></section></section></main>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']), user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
    window.fetch = async url => ({ ok: true, json: async () => {
      if (String(url).includes('/api/ai-presentations')) return [];
      return [];
    }});
    window.TeacherMediaSubtitle1014 = { selectMaterial: value => { window.subtitleSource = value; } };
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-studio-1018.js') });
  await expect(page.locator('#teacher-ai-media-studio-1018')).toHaveCount(1);
  const tabs = page.getByRole('tab');
  await expect(tabs).toHaveCount(3);
  await tabs.nth(0).press('ArrowRight');
  await expect(page.locator('#teacher-media-tab-subtitle-1018')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#teacher-media-panel-narration-1018')).toHaveAttribute('hidden', '');
  await page.locator('#teacher-media-source-1018').selectOption('movie-1');
  await expect.poll(() => page.evaluate(() => window.subtitleSource)).toBe('movie-1');
  await expect(page.locator('[role="tab"][aria-controls]')).toHaveCount(3);
});
