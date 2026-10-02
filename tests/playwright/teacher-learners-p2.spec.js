const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';

const TEACHER = {
  username: 'teacher-p2',
  name: 'P2 臨床教師',
  empId: 'T2001',
  role: 'clinical_teacher',
  roles: ['clinical_teacher'],
  preferredGroup: 'grpBio',
  permissions: [
    'material.read', 'course.view', 'course.manage', 'material.manage',
    'question.manage', 'exam.manage', 'result.group.read', 'document.export',
    'evaluation.submit', 'evaluation.review', 'evaluation.sign',
    'teacher.assessment.sign', 'student.view_assigned',
  ],
};

test('P2 我的學員 stays inside assessment workspace with server-scoped learners', async ({ page }) => {
  await page.route('**/api/auth/profile', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ authenticated: true, user: TEACHER }),
  }));
  await page.route('**/api/auth/me', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ authenticated: true, user: TEACHER }),
  }));
  await page.route('**/api/pgy-assessment-templates', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([]),
  }));
  await page.route('**/api/training-command-center/teacher-learners', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      scope: { kind: 'assigned', group: 'grpBio' },
      summary: {
        learners: 1,
        assignments: 2,
        completedAssignments: 1,
        awaitingTeacher: 1,
        awaitingLeader: 0,
        awaitingFinalize: 0,
        overdueAssignments: 0,
      },
      learners: [{
        username: 'student-p2',
        name: '測試學員',
        empId: 'S2001',
        group: 'grpBio',
        active: true,
        assignmentCount: 2,
        completedAssignments: 1,
        awaitingTeacher: 1,
        awaitingLeader: 0,
        awaitingFinalize: 0,
        overdueAssignments: 0,
        latestStatus: 'submitted',
        latestStatusLabel: '待教師簽核',
        lastActivityAt: '2026-10-02T00:00:00+00:00',
      }],
      source: 'pgy-assignments',
      interpretation: 'read_only_teacher_trainee_projection',
    }),
  }));

  await page.goto(
    `${baseURL}/system?area=pgy&group=grpBio&admin=1&workspace=assessment&persona=teacher`,
    { waitUntil: 'domcontentloaded' },
  );

  await expect(page.locator('#admin-section-quiz')).not.toHaveClass(/hidden/);
  const panel = page.locator('#teacher-learners-p2');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('我的學員');
  await expect(panel).toContainText('測試學員');
  await expect(panel).toContainText('待教師 1');
  await expect(panel.getByRole('button', { name: '查看考核紀錄' })).toBeVisible();
  const clinical = panel.getByRole('button', { name: '開始臨床技能評核' });
  await expect(clinical).toBeVisible();

  await expect(page.locator('#teacher-nav-course-1014')).toBeVisible();
  await expect(page.locator('#teacher-nav-assessment-1014')).toBeVisible();
  await expect(page.locator('[id^="teacher-nav-"]')).toHaveCount(2);

  await clinical.click();
  await expect(page.locator('#panel-assessment')).not.toHaveClass(/hidden/);
  await expect(page.locator('#admin-modal')).toHaveClass(/hidden/);
  await expect(page.locator('#pgy-assess-name')).toHaveValue('測試學員');
  await expect(page.locator('#pgy-assess-empid')).toHaveValue('S2001');
  await expect(page.locator('#pgy-assess-evaluator')).toHaveValue('P2 臨床教師');
  await expect(page.locator('#pgy-assessment-form-title')).toContainText('DOPS');
  await expect(page.locator('#pgy-assess-status')).toContainText('已選擇 測試學員');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
