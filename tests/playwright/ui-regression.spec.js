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

test('dual-role header stays stable and Worker navigation leaves teacher persona cleanly', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open(page, '/system?area=internal&group=grpBio&module=materials&admin=1&workspace=course-materials&persona=teacher');
  await page.waitForFunction(() => Boolean(window.TeacherRBAC681Ready));
  await page.evaluate(() => window.TeacherRBAC681Ready);
  await expect(page.locator('#admin-modal')).toBeVisible({ timeout: 10000 });

  const switcher = page.locator('#teacher-persona-switch-1014');
  await expect(switcher).toBeVisible();
  await expect(switcher.getByRole('button', { name: /系統管理/ })).toHaveCount(1);
  await expect(switcher.getByRole('button', { name: /教師工作區/ })).toHaveCount(1);

  await page.evaluate(async () => {
    await window.switchAdminWorkspace?.('assessment', true);
  });
  await expect(page.locator('#admin-section-quiz')).toBeVisible({ timeout: 10000 });
  await expect(switcher.getByRole('button', { name: /系統管理/ })).toHaveCount(1);

  await Promise.all([
    page.waitForURL(url => url.searchParams.get('workspace') === 'worker' && url.searchParams.get('persona') === 'system', { timeout: 15000 }),
    page.evaluate(() => window.switchAdminWorkspace?.('worker', true)),
  ]);

  await expect(page.locator('#admin-section-worker')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#admin-section-quiz')).toBeHidden();
  await expect(page.locator('#admin-workspace-title')).toContainText('Worker');
  await expect(page.locator('#teacher-persona-switch-1014').getByRole('button', { name: /系統管理/ })).toHaveCount(1);
  await assertNoHorizontalOverflow(page);
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

test('system admin sees canonical Worker offline notification in system workspace', async ({ page }) => {
  await page.route('**/api/training-command-center/notifications', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: 'training-command-center',
        counts: { total: 1, overdue: 0, emailEligible: 1 },
        items: [{
          key: 'notify:worker_offline:test',
          persona: 'system',
          kind: 'worker_offline',
          domain: 'operations',
          title: '教材 Worker 已離線',
          detail: 'A8B5-TeacherWorker 已超過 10 分鐘未回報心跳。',
          badge: 'Worker 離線',
          status: 'offline:2026-10-02T00:00:00+00:00',
          overdue: false,
          dueAt: '',
          area: 'internal',
          group: '',
          resourceId: 'A8B5-TeacherWorker',
          courseId: '',
          href: '/system?admin=1&workspace=worker&persona=system&from=notification-center',
          channels: ['in_app', 'email'],
          emailPolicy: 'once',
        }],
      }),
    });
  });
  await page.route('**/api/notification-states?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ states: {} }) });
  });

  await page.setViewportSize({ width: 430, height: 932 });
  await open(page, '/system?admin=1&workspace=worker&persona=system');

  const center = page.locator('#notification-center-71');
  await expect(center).toBeVisible({ timeout: 10000 });
  await expect(center).toHaveAttribute('data-notification-context', 'system');
  await expect(center).toContainText('教材 Worker 已離線');
  await expect(center).toContainText('Worker 離線');
  await expect(center.locator('a[href*="workspace=worker"][href*="persona=system"]')).toContainText('查看 Worker 狀態');
  const parentId = await center.evaluate(node => node.parentElement?.id || '');
  expect(parentId).toBe('admin-workspace-content');

  await center.locator('summary').click();
  await expect(center).toHaveClass(/notification-center-modal-open/);
  const overlay = await center.evaluate(node => {
    const rect = node.getBoundingClientRect();
    return {
      parentIsBody: node.parentElement === document.body,
      top: rect.top,
      left: rect.left,
      right: rect.right,
      bottom: rect.bottom,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  expect(overlay.parentIsBody, JSON.stringify(overlay)).toBe(true);
  expect(overlay.left, JSON.stringify(overlay)).toBeGreaterThanOrEqual(0);
  expect(overlay.right, JSON.stringify(overlay)).toBeLessThanOrEqual(overlay.viewportWidth + 1);
  expect(overlay.top, JSON.stringify(overlay)).toBeGreaterThanOrEqual(0);
  expect(overlay.bottom, JSON.stringify(overlay)).toBeLessThanOrEqual(overlay.viewportHeight + 1);

  await page.keyboard.press('Escape');
  await expect(center).not.toHaveClass(/notification-center-modal-open/);
  const restoredParentId = await center.evaluate(node => node.parentElement?.id || '');
  expect(restoredParentId).toBe('admin-workspace-content');
  await assertNoHorizontalOverflow(page);
});

test('Worker notification action cannot land on assessment or AI authoring', async ({ page }) => {
  await page.route('**/api/training-command-center/notifications', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: 'training-command-center',
        counts: { total: 1, overdue: 0, emailEligible: 1 },
        items: [{
          key: 'notify:worker_offline:routing',
          persona: 'system',
          kind: 'worker_offline',
          domain: 'operations',
          title: '教材 Worker 已離線',
          detail: 'Worker heartbeat 已超過門檻。',
          badge: 'Worker 離線',
          status: 'offline:test',
          overdue: false,
          href: '/system?admin=1&workspace=worker&persona=system&from=notification-center',
          channels: ['in_app'],
          emailPolicy: 'none',
        }],
      }),
    });
  });
  await page.route('**/api/notification-states?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ states: {} }) });
  });

  await page.setViewportSize({ width: 430, height: 932 });
  await open(page, '/system?admin=1&workspace=people&persona=system');
  const center = page.locator('#notification-center-71');
  await expect(center).toBeVisible({ timeout: 10000 });
  await center.locator('summary').click();
  const workerLink = center.locator('a[href*="workspace=worker"][href*="persona=system"]');
  await expect(workerLink).toBeVisible();

  await Promise.all([
    page.waitForURL(url => url.searchParams.get('workspace') === 'worker' && url.searchParams.get('persona') === 'system', { timeout: 15000 }),
    workerLink.click(),
  ]);

  await expect(page.locator('#admin-section-worker')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#admin-section-quiz')).toBeHidden();
  await expect(page.locator('#admin-workspace-title')).toContainText('Worker');
  await expect(page.locator('#teacher-content-studio-71')).toBeHidden();

  const navIds = await page.locator('.v580-admin-groups .admin-nav-btn').evaluateAll(nodes => nodes.map(node => node.id));
  expect(new Set(navIds).size).toBe(navIds.length);
  await expect(page.locator('.v580-admin-groups [data-admin-nav-group="operations"]')).toHaveCount(1);
  await expect(page.locator('.v580-admin-groups #admin-nav-worker')).toHaveCount(1);

  await page.evaluate(() => {
    const original = window.switchAdminWorkspace;
    window.__workspaceDispatchCount = 0;
    window.switchAdminWorkspace = async function (...args) {
      window.__workspaceDispatchCount += 1;
      return original.apply(this, args);
    };
  });

  await page.locator('#admin-nav-system').click();
  await expect.poll(() => page.evaluate(() => window.__workspaceDispatchCount)).toBe(1);
  await expect(page).toHaveURL(/workspace=system/);

  await page.evaluate(() => { window.__workspaceDispatchCount = 0; });
  await page.locator('#admin-nav-worker').click();
  await expect.poll(() => page.evaluate(() => window.__workspaceDispatchCount)).toBe(1);
  await expect(page).toHaveURL(/workspace=worker/);
  await expect(page.locator('.v580-admin-groups .admin-nav-btn[aria-current="page"]')).toHaveCount(1);
  await expect(page.locator('#admin-nav-worker')).toHaveAttribute('aria-current', 'page');
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

test('course overview keeps stable ownership and learner feature finalizers', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('smh_learner_name', '測試學員');
    localStorage.setItem('smh_learner_empid', 'T9001');
  });

  await page.route('**/api/slides?**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        id: 'mat-browser-owner',
        title: 'Ownership 測試教材',
        filename: 'ownership.pdf',
        desc: '確認 teaching presenter 保留 canonical learner features',
        area: 'internal',
        group: 'grpBio',
        courseId: 'course-browser-owner',
        viewerMode: 'slides',
        materialType: 'standard',
        pageCount: 3,
        active: true,
      }]),
    });
  });

  await page.route('**/api/courses?**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        id: 'course-browser-owner',
        title: 'Ownership 測試課程',
        desc: 'Course overview ownership regression',
        area: 'internal',
        group: 'grpBio',
        active: true,
        materialOrder: ['mat-browser-owner'],
        learningObjectives: '保留收藏功能\n保留回饋與完訓證明',
        estimatedMinutes: 20,
      }]),
    });
  });

  await page.route('**/api/quiz-categories?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });

  await page.route('**/api/my-progress?**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ materialsCompleted: {}, courses: [], records: [] }),
    });
  });

  await page.route('**/api/saved-learning-items', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          itemType: 'course',
          itemId: 'course-browser-owner',
          title: 'Ownership 測試課程',
          area: 'internal',
          group: 'grpBio',
        }],
      }),
    });
  });

  await page.route('**/api/learning-calendar?**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        events: [{
          id: 'calendar-browser-owner',
          kind: 'course_due',
          title: 'Ownership 測試課程',
          date: '2026-10-10',
          at: '2026-10-10T09:00:00+08:00',
          courseId: 'course-browser-owner',
          target: 'course',
          overdue: false,
        }],
      }),
    });
  });

  await page.route('**/api/completion-certificates', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          id: 'CERT-OWNER-1',
          courseId: 'course-browser-owner',
          courseTitle: 'Ownership 測試課程',
          area: 'internal',
          group: 'grpBio',
          currentStatus: 'current',
        }],
      }),
    });
  });

  await page.setViewportSize({ width: 430, height: 932 });
  await open(page, '/system?area=internal&group=grpBio&module=materials');

  await page.waitForFunction(() =>
    typeof window.renderSlidesGrid === 'function' &&
    typeof window.renderCourseOverview === 'function' &&
    Boolean(window.LearnerCourseOverview?.renderBase) &&
    Boolean(window.TeachingCourseOverview66?.render)
  );

  const stableRenderer = await page.evaluate(async () => {
    const before = window.renderCourseOverview;
    await window.renderSlidesGrid();
    window.renderCourseOverview();
    return before === window.renderCourseOverview;
  });
  expect(stableRenderer).toBe(true);

  await expect(page.locator('#course-overview-grid .course-learning-card')).toHaveCount(1);
  await expect(page.locator('#course-overview-grid')).toContainText('Ownership 測試課程');
  await expect(page.locator('#course-overview-grid')).toContainText('課程回饋與收藏');
  await expect(page.locator('#course-overview-grid [data-save-learning-item="material"]')).toHaveCount(1);

  await expect(page.locator('#saved-learning-items')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#saved-learning-items')).toContainText('Ownership 測試課程');
  await expect(page.locator('#learning-calendar')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#learning-calendar')).toContainText('Ownership 測試課程');
  await expect(page.locator('#completion-certificates')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('#completion-certificates')).toContainText('CERT-OWNER-1');
  await assertNoHorizontalOverflow(page);
});

