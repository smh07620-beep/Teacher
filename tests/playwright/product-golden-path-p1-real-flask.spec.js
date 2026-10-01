const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_FLASK_BASE_URL || 'http://127.0.0.1:4174';
const fixturePassword = process.env.TEACHER_CI_BROWSER_PASSWORD || '';

async function login(page, username, next = '/system?area=internal&group=grpBio') {
  expect(fixturePassword, 'CI must provide the ephemeral real-Flask browser fixture password').not.toBe('');
  await page.goto(`${baseURL}/login?next=${encodeURIComponent(next)}`, { waitUntil: 'domcontentloaded' });
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(fixturePassword);
  await Promise.all([
    page.waitForURL(url => !url.pathname.endsWith('/login'), { timeout: 15000 }),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
  await page.waitForLoadState('domcontentloaded');
}

async function logout(page) {
  await page.evaluate(async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  });
  await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded' });
}

test('GP-07 dual-role account switches learner and teacher personas without system leakage', async ({ page }) => {
  await login(page, 'gp07dual');

  const meResponse = await page.request.get(`${baseURL}/api/auth/profile`);
  expect(meResponse.status()).toBe(200);
  const me = await meResponse.json();
  expect(me.authenticated).toBeTruthy();
  expect(me.user.roles).toEqual(expect.arrayContaining(['student', 'clinical_teacher']));
  expect(me.user.preferredGroup).toBe('grpBio');

  const switcher = page.locator('#teacher-persona-switch-1014');
  await expect(switcher).toBeVisible({ timeout: 15000 });
  await expect(switcher.getByRole('button', { name: /我的學習/ })).toBeVisible();
  await expect(switcher.getByRole('button', { name: /教師工作區/ })).toBeVisible();
  await expect(switcher.getByRole('button', { name: /系統管理/ })).toHaveCount(0);

  await switcher.getByRole('button', { name: /教師工作區/ }).click();
  await page.waitForURL(url => url.searchParams.get('persona') === 'teacher', { timeout: 15000 });
  await expect(page.locator('#teacher-nav-course-1014')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#teacher-nav-assessment-1014')).toBeVisible();
  await expect(page.locator('#admin-nav-worker')).toBeHidden();
  await expect(page.locator('#admin-nav-people')).toBeHidden();

  const teacherSwitcher = page.locator('#teacher-persona-switch-1014');
  await expect(teacherSwitcher.getByRole('button', { name: /我的學習/ })).toBeVisible();
  await teacherSwitcher.getByRole('button', { name: /我的學習/ }).click();
  await page.waitForURL(url => !url.searchParams.has('admin') && !url.searchParams.has('persona'), { timeout: 15000 });
  await expect(page.locator('#teacher-persona-switch-1014')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#admin-section-worker')).toBeHidden();
});

test('GP-08 system administrator provisions scoped teacher who gets only canonical permissions', async ({ page }) => {
  await login(page, 'gp08admin', '/system?admin=1&workspace=people&persona=system');
  await page.waitForURL(url => url.searchParams.get('workspace') === 'people', { timeout: 15000 });
  await expect(page.locator('#admin-user-create-panel')).toBeAttached({ timeout: 15000 });

  const panel = page.locator('#admin-user-create-panel');
  await panel.evaluate(node => {
    if ('open' in node) node.open = true;
    node.classList.remove('hidden');
  });
  await page.locator('#admin-user-username').fill('gp08target');
  await page.locator('#admin-user-password').fill(fixturePassword);
  await page.locator('#admin-user-name').fill('GP08 臨床教師');
  await page.locator('#admin-user-empid').fill('GP0801');
  await page.locator('#admin-user-role').selectOption('clinical_teacher');
  await page.locator('#admin-user-area').selectOption('internal');
  await page.locator('#admin-user-group').selectOption('grpBio');

  await page.evaluate(async () => {
    if (typeof window.createAdminUserAccount !== 'function') {
      throw new Error('canonical account creation UI function is unavailable');
    }
    await window.createAdminUserAccount();
  });
  await expect(page.locator('#admin-user-status')).toContainText(/建立|新增|完成|成功/, { timeout: 15000 });
  await expect(page.locator('#admin-user-accounts-body')).toContainText('gp08target', { timeout: 15000 });

  await logout(page);
  await login(page, 'gp08target');

  const targetResponse = await page.request.get(`${baseURL}/api/auth/profile`);
  expect(targetResponse.status()).toBe(200);
  const target = await targetResponse.json();
  expect(target.user.role).toBe('clinical_teacher');
  expect(target.user.roles).toContain('clinical_teacher');
  expect(target.user.preferredArea).toBe('internal');
  expect(target.user.preferredGroup).toBe('grpBio');

  await expect(page.locator('#teacher-persona-switch-1014')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#teacher-persona-switch-1014').getByRole('button', { name: /教師工作區/ })).toBeVisible();
  await expect(page.locator('#teacher-persona-switch-1014').getByRole('button', { name: /系統管理/ })).toHaveCount(0);

  const forbidden = await page.evaluate(async () => {
    const response = await fetch('/api/users', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: 'gp08forbidden',
        password: 'not-used',
        name: 'Should Not Exist',
        empId: 'NOPE',
        role: 'system_admin',
      }),
    });
    return { status: response.status, body: await response.json().catch(() => ({})) };
  });
  expect(forbidden.status).toBe(403);
  expect(forbidden.body.error).toContain('權限不足');
});
