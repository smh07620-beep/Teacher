const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';

async function assertNoHorizontalOverflow(page) {
  // Navigation URL assertions can resolve while Chromium is between documents.
  // Wait for the destination body before reading layout metrics so this gate
  // measures real overflow rather than a transient null document body.
  await page.locator('body').waitFor({ state: 'attached' });
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
}

async function assertMobileBottomNav(page) {
  const nav = page.locator('nav.v56-bottom-nav');
  await expect(nav).toBeVisible();
  const geometry = await nav.evaluate(node => {
    const rect = node.getBoundingClientRect();
    return { left: rect.left, right: rect.right, width: rect.width, viewport: window.innerWidth };
  });
  expect(geometry.left, JSON.stringify(geometry)).toBeGreaterThanOrEqual(-1);
  expect(geometry.right, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.width, JSON.stringify(geometry)).toBeGreaterThan(200);
}

function learnerAuth() {
  return {
    authenticated: true,
    user: {
      username: 'mobile-student',
      name: '手機學員',
      empId: 'M001',
      role: 'student',
      roles: ['student'],
      preferredGroup: 'grpBio',
      permissions: ['material.read', 'course.view', 'exam.take', 'progress.self.read'],
    },
  };
}

test('mobile learner Golden Path stays aligned from todo to course, exam and completed progress', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  let phase = 'course';
  const command = () => {
    if (phase === 'course') {
      return {
        counts: { learner: 1, total: 1 },
        items: [{
          id: 'course-bio', resourceId: 'course-bio', courseId: 'course-bio',
          persona: 'learner', domain: 'learning', kind: 'course', status: 'assigned', statusLabel: '待完成課程',
          title: '生化必修課程', area: 'internal', group: 'grpBio', dueAt: '2026-10-08T00:00:00+08:00',
          overdue: false, detail: '教材 0/1 · 尚待考核', target: 'materials', actionLabel: '繼續學習',
        }],
      };
    }
    if (phase === 'exam') {
      return {
        counts: { learner: 1, total: 1 },
        items: [{
          id: 'exam-bio', resourceId: 'exam-bio', courseId: 'course-bio',
          persona: 'learner', domain: 'assessment', kind: 'exam', status: 'pending', statusLabel: '待完成考核',
          title: '生化課後考核', area: 'internal', group: 'grpBio', dueAt: '2026-10-08T00:00:00+08:00',
          overdue: false, detail: '教材已完成，請完成考核', target: 'exam', actionLabel: '前往考核',
        }],
      };
    }
    return { counts: { learner: 0, total: 0 }, items: [] };
  };
  const progress = () => ({
    audience: 'online', pgyLearner: false,
    online: {
      percent: phase === 'course' ? 0 : phase === 'exam' ? 50 : 100,
      materialsCompleted: phase === 'course' ? 0 : 1,
      materialsTotal: 1,
      examsPassed: phase === 'done' ? 1 : 0,
      examsTotal: 1,
      activeCourses: phase === 'done' ? 0 : 1,
      scopeSource: 'assignments',
    },
    pgy: null,
  });

  await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(learnerAuth()) }));
  await page.route('**/api/auth/profile', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(learnerAuth()) }));
  await page.route('**/api/training-command-center/progress', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(progress()) }));
  await page.route('**/api/training-command-center', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(command()) }));
  await page.route('**/api/dashboard/me?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ name: '手機學員', empId: 'M001', activeCourses: 1, materialsPending: 1, examsPending: 1, progressPercent: 0 }),
  }));

  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#v571-pending-exams')).toHaveAttribute('data-learner-todo-source', 'training-command-center');
  await expect(page.locator('#v681-home-todo-count')).toHaveText('1');
  await expect(page.getByText('生化必修課程', { exact: true })).toBeVisible();
  await expect(page.locator('#v561-progress-percent')).toHaveText('0');
  await assertMobileBottomNav(page);
  await assertNoHorizontalOverflow(page);

  const courseLink = page.locator('#v571-pending-exams a').first();
  await expect(courseLink).toHaveAttribute('href', /module=materials/);
  await expect(courseLink).toHaveAttribute('href', /courseId=course-bio/);
  await courseLink.click();
  await expect(page).toHaveURL(/\/system\?.*module=materials/);
  await expect(page).toHaveURL(/courseId=course-bio/);
  await assertNoHorizontalOverflow(page);

  phase = 'exam';
  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#v681-home-todo-count')).toHaveText('1');
  await expect(page.getByText('生化課後考核', { exact: true })).toBeVisible();
  await expect(page.locator('#v561-progress-percent')).toHaveText('50');
  const examLink = page.locator('#v571-pending-exams a').first();
  await expect(examLink).toHaveAttribute('href', /module=exam/);
  await expect(examLink).toHaveAttribute('href', /examId=exam-bio/);
  await examLink.click();
  await expect(page).toHaveURL(/\/system\?.*module=exam/);
  await expect(page).toHaveURL(/examId=exam-bio/);
  await assertNoHorizontalOverflow(page);

  phase = 'done';
  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#v681-home-todo-count')).toHaveText('0');
  await expect(page.locator('#v571-pending-exams')).toContainText('目前沒有待辦');
  await expect(page.locator('#v561-progress-percent')).toHaveText('100');
  await expect(page.locator('#v561-progress-bar')).toHaveCSS('width', /.+/);
  await expect(page.locator('html')).toHaveAttribute('data-progress-source', 'training-command-center');
  await assertMobileBottomNav(page);
  await assertNoHorizontalOverflow(page);
});

test('mobile 430 task cards and bottom navigation never escape the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.route('**/api/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(learnerAuth()) }));
  await page.route('**/api/training-command-center/progress', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ audience: 'online', pgyLearner: false, online: { percent: 40, materialsCompleted: 2, materialsTotal: 5, examsPassed: 0, examsTotal: 1, activeCourses: 2 }, pgy: null }),
  }));
  await page.route('**/api/training-command-center', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ counts: { learner: 2, total: 2 }, items: [
      { id: 'long-course', resourceId: 'long-course', courseId: 'long-course', persona: 'learner', kind: 'course', title: '這是一門用來驗證手機版不應該水平溢出的很長很長課程名稱', area: 'internal', group: 'grpBio', detail: '課程內容與截止資訊必須在手機卡片內正常換行', target: 'materials' },
      { id: 'long-exam', resourceId: 'long-exam', persona: 'learner', kind: 'exam', title: '手機版長標題課後考核', area: 'internal', group: 'grpBio', detail: '完成後進度應回到同一個 canonical source', target: 'exam' },
    ] }),
  }));
  await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#v571-pending-exams a')).toHaveCount(2);
  await assertMobileBottomNav(page);
  await assertNoHorizontalOverflow(page);
  for (const row of await page.locator('#v571-pending-exams a').all()) {
    const box = await row.boundingBox();
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(432);
  }
});