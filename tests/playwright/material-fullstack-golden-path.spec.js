const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_MATERIAL_FULLSTACK_BASE_URL || 'http://127.0.0.1:4175';
const fixturePassword = process.env.TEACHER_CI_BROWSER_PASSWORD || '';

async function login(page) {
  expect(fixturePassword).not.toBe('');
  const next = '/system?area=internal&group=grpBio&admin=1&workspace=course-materials&persona=teacher';
  await page.goto(`${baseURL}/login?next=${encodeURIComponent(next)}`, { waitUntil: 'domcontentloaded' });
  await page.locator('#login-username').fill('gp01teacher');
  await page.locator('#login-password').fill(fixturePassword);
  await Promise.all([
    page.waitForURL(url => !url.pathname.endsWith('/login'), { timeout: 15000, waitUntil: 'domcontentloaded' }),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
  await page.waitForFunction(() => Boolean(window.MaterialUploadClient?.directUpload), null, { timeout: 15000 });
}

test('GP-01 full stack Browser -> R2 -> real Worker -> Database -> Browser', async ({ page }) => {
  await login(page);

  const queued = await page.evaluate(async () => {
    const title = 'Full-stack R2 Worker 教材';
    const file = new File(
      ['Teacher full-stack material golden path\n'],
      'full-stack-golden-path.txt',
      { type: 'text/plain', lastModified: 1760000000000 },
    );
    const form = new FormData();
    form.append('file', file);
    form.append('title', title);
    form.append('desc', 'Browser → Web → R2 → material_worker.py → Database → Browser');
    form.append('group', 'grpBio');
    form.append('area', 'internal');
    form.append('courseId', 'course-full-stack');
    form.append('materialType', 'standard');
    return window.MaterialUploadClient.directUpload(form, { fileName: file.name });
  });

  expect(queued.status).toBe('queued');
  expect(queued.jobId).toBeTruthy();

  const published = await expect.poll(async () => {
    return page.evaluate(async () => {
      const response = await fetch('/api/slides?area=internal', {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (!response.ok) return null;
      const data = await response.json();
      const rows = Array.isArray(data) ? data : (data.materials || data.slides || []);
      const item = rows.find(row => row.title === 'Full-stack R2 Worker 教材');
      return item ? {
        id: item.id,
        courseId: item.courseId,
        storageBackend: item.storageBackend,
        storageKey: item.storageKey,
      } : null;
    });
  }, {
    timeout: 60000,
    intervals: [500, 1000, 1500, 2000],
    message: 'real material Worker should publish the queued browser upload',
  }).not.toBeNull();

  const material = await page.evaluate(async () => {
    const response = await fetch('/api/slides?area=internal', { credentials: 'same-origin', cache: 'no-store' });
    const data = await response.json();
    const rows = Array.isArray(data) ? data : (data.materials || data.slides || []);
    return rows.find(row => row.title === 'Full-stack R2 Worker 教材') || null;
  });
  expect(material).toBeTruthy();
  expect(material.courseId).toBe('course-full-stack');
  expect(material.storageBackend).toBe('r2');
  expect(material.storageKey).toMatch(/^materials\/upload-[^/]+\/source\.txt$/);

  await page.evaluate(async () => {
    if (typeof window.renderAdminCourseMaterialHub === 'function') {
      await window.renderAdminCourseMaterialHub(true);
    }
  });
  await expect(page.locator('body')).toContainText('Full-stack R2 Worker 教材', { timeout: 15000 });
});
