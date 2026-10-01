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

test('teacher persona full-page workspace never collapses to a blank surface', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const pageErrors = [];
  const domTraces = [];
  page.on('pageerror', error => pageErrors.push(String(error?.message || error)));
  page.on('console', message => {
    const text = message.text();
    if (text.includes('ADMIN_WIPE_TRACE')) domTraces.push(text);
  });
  await page.addInitScript(() => {
    const relevant = node => {
      if (!node || node.nodeType !== 1) return false;
      if (node.id === 'admin-modal' || node.classList?.contains('admin-workspace-shell')) return true;
      try { return Boolean(node.querySelector?.('#admin-workspace-header')); } catch (_) { return false; }
    };
    const trace = (operation, node) => {
      if (!relevant(node)) return;
      console.log(`ADMIN_WIPE_TRACE ${operation} ${new Error().stack || ''}`);
    };

    const nativeReplaceChildren = Element.prototype.replaceChildren;
    Element.prototype.replaceChildren = function(...nodes) {
      trace('replaceChildren', this);
      return nativeReplaceChildren.apply(this, nodes);
    };

    const nativeRemove = Element.prototype.remove;
    Element.prototype.remove = function() {
      trace('remove', this);
      return nativeRemove.call(this);
    };

    const nativeReplaceWith = Element.prototype.replaceWith;
    Element.prototype.replaceWith = function(...nodes) {
      trace('replaceWith', this);
      return nativeReplaceWith.apply(this, nodes);
    };

    const nativeRemoveChild = Node.prototype.removeChild;
    Node.prototype.removeChild = function(child) {
      if (relevant(this) || relevant(child)) trace('removeChild', relevant(this) ? this : child);
      return nativeRemoveChild.call(this, child);
    };

    const inner = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
    if (inner?.get && inner?.set) {
      Object.defineProperty(Element.prototype, 'innerHTML', {
        configurable: inner.configurable,
        enumerable: inner.enumerable,
        get: inner.get,
        set(value) {
          trace('innerHTML', this);
          return inner.set.call(this, value);
        },
      });
    }

    const text = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
    if (text?.get && text?.set) {
      Object.defineProperty(Node.prototype, 'textContent', {
        configurable: text.configurable,
        enumerable: text.enumerable,
        get: text.get,
        set(value) {
          trace('textContent', this);
          return text.set.call(this, value);
        },
      });
    }
  });

  await open(page, '/system?area=internal&group=grpBio&module=materials&from=home&admin=1&workspace=course-materials&persona=teacher');
  await page.waitForFunction(() => Boolean(window.TeacherRBAC681Ready));
  await page.evaluate(() => window.TeacherRBAC681Ready);
  await page.waitForTimeout(500);

  const debug = await page.evaluate(() => {
    const modal = document.getElementById('admin-modal');
    const shell = document.querySelector('.admin-workspace-shell');
    return {
      modalTag: modal?.tagName || null,
      modalClasses: modal?.className || null,
      modalChildren: modal ? [...modal.children].map(node => ({ tag: node.tagName, id: node.id, cls: node.className })) : [],
      shellChildren: shell ? [...shell.children].map(node => ({ tag: node.tagName, id: node.id, cls: node.className })) : [],
      bodyClasses: document.body.className,
      knownIds: ['admin-workspace-header','admin-workspace-title','admin-workspace-content','admin-workspace-footer'].map(id => [id, Boolean(document.getElementById(id))]),
    };
  });
  debug.pageErrors = pageErrors;
  debug.domTraces = domTraces;
  console.log('TEACHER_WORKSPACE_DEBUG', JSON.stringify(debug));

  await expect(page.locator('#admin-modal')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#admin-workspace-header')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#admin-workspace-title')).toContainText('教師工作區');
  await expect(page.locator('#admin-workspace-content')).toBeVisible();
  await expect(page.locator('.v580-admin-groups')).toBeVisible();

  const geometry = await page.locator('.admin-workspace-shell').evaluate(node => {
    const rect = node.getBoundingClientRect();
    return { width: rect.width, height: rect.height, text: (node.innerText || '').trim() };
  });
  expect(geometry.width, JSON.stringify(geometry)).toBeGreaterThan(600);
  expect(geometry.height, JSON.stringify(geometry)).toBeGreaterThan(500);
  expect(geometry.text.length, JSON.stringify(geometry)).toBeGreaterThan(20);
  expect(pageErrors).toEqual([]);
});

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
