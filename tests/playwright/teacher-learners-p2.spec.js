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
  await page.route('**/api/training-command-center/teacher-competency', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      scope: { kind: 'assigned', group: 'grpBio' },
      assessmentTypes: [
        { key: 'dops', label: 'DOPS' },
        { key: 'mini_cex', label: 'MINI-CEX' },
      ],
      summary: {
        learners: 1,
        assignments: 2,
        assignmentsCompleted: 1,
        assignmentsOverdue: 0,
        assignmentCompletionPercent: 50,
        assessments: 2,
        averageAssessmentScore: 4.2,
      },
      learners: [{
        username: 'student-p2',
        name: '測試學員',
        empId: 'S2001',
        group: 'grpBio',
        progress: {
          assignmentsTotal: 2,
          assignmentsCompleted: 1,
          assignmentsOverdue: 0,
          percent: 50,
        },
        assessmentSummary: {
          count: 2,
          averageScore: 4.2,
          coverageTypes: 2,
          coverageTotal: 10,
        },
        competencies: {
          dops: { count: 1, averageScore: 4, latestScore: 4, latestDate: '2026-10-01' },
          mini_cex: { count: 1, averageScore: 4.4, latestScore: 4.4, latestDate: '2026-10-02' },
        },
      }],
      source: 'formal-pgy-assessments',
      interpretation: 'formal_assessment_tracking_without_mastery_score',
    }),
  }));
  await page.route('**/api/training-command-center/teacher-analytics', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      scope: { kind: 'assigned', group: 'grpBio' },
      summary: { learners: 1, materialCompletionRate: 75, averageExamScore: 88, examPendingReview: 1, pgyCompletionRate: 50, averagePgyAssessmentScore: 4.2 },
      learners: [{ username: 'student-p2', name: '測試學員', empId: 'S2001', group: 'grpBio',
        materials: { tracked: 4, completed: 3, averageProgress: 75 },
        exams: { averageScore: 88, pendingReview: 1, passed: 2, reviewedAttempts: 2 },
        pgy: { assignments: 2, completedAssignments: 1, completionRate: 50, assessments: 2, assessmentAverage: 4.2 } }],
      timeline: [{ month: '2026-10', materials: 3, exams: 2, pgy: 1, assessments: 2 }],
      source: 'scoped-learning-exam-pgy-records',
      interpretation: 'descriptive_teacher_analytics_without_mastery_score',
    }),
  }));
  await page.route('**/api/pgy-assessments', async route => {
    if (route.request().method() !== 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    const payload = route.request().postDataJSON();
    expect(payload.empId).toBe('S2001');
    expect(payload.assessmentType).toBe('dops');
    expect(payload.details.ratings).toHaveLength(6);
    expect(payload.details.ratings.every(item => item.rating === 4)).toBeTruthy();
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, id: 'p2-assessment-1' }) });
  });
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

  for (let index = 0; index < 6; index += 1) {
    await page.locator(`input[name="pgy-rating-${index}"][value="4"]`).check();
  }
  await page.locator('#pgy-assess-submit').click();
  await expect(page.locator('#pgy-assess-status')).toContainText('已完成全部 6 項評核並儲存');
  await expect(page.locator('#teacher-p2-return-after-assessment')).toBeVisible();
  await page.locator('#teacher-p2-return-after-assessment').click();
  await page.waitForURL(url => url.searchParams.get('workspace') === 'assessment' && url.searchParams.get('persona') === 'teacher');

  const refreshedPanel = page.locator('#teacher-learners-p2');
  await expect(refreshedPanel).toBeVisible();
  await refreshedPanel.getByRole('button', { name: '能力追蹤' }).click();
  const competencyPanel = page.locator('#teacher-competency-detail-p2');
  await expect(competencyPanel).toBeVisible();
  await expect(competencyPanel).toContainText('能力追蹤 · 測試學員');
  await expect(competencyPanel).toContainText('DOPS');
  await expect(competencyPanel).toContainText('MINI-CEX');
  await expect(competencyPanel).toContainText('不合併成 AI 能力總分');
  await expect(competencyPanel).toContainText('4.2');

  await refreshedPanel.getByRole('button', { name: '教學分析' }).click();
  const analyticsPanel = page.locator('#teacher-teaching-analytics-p2');
  await expect(analyticsPanel).toBeVisible();
  await expect(analyticsPanel).toContainText('教學分析');
  await expect(analyticsPanel).toContainText('測試學員');
  await expect(analyticsPanel).toContainText('正式評量平均');
  await expect(analyticsPanel).toContainText('不產生 AI 能力總分或預測');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
