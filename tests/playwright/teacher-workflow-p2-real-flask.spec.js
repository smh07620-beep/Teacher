const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_FLASK_BASE_URL || 'http://127.0.0.1:4174';
const fixturePassword = process.env.TEACHER_CI_BROWSER_PASSWORD || '';

async function login(page, username, next) {
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

test('P2 teacher workflow persists clinical assessment then refreshes competency and teaching analytics', async ({ page }) => {
  const teacherUrl = '/system?area=pgy&group=grpBio&admin=1&workspace=assessment&persona=teacher';
  await login(page, 'p2teacher', teacherUrl);

  const roster = page.locator('#teacher-learners-p2');
  await expect(roster).toBeVisible({ timeout: 15000 });
  await expect(roster).toContainText('P2 測試學員');
  await expect(page.locator('[id^="teacher-nav-"]')).toHaveCount(2);

  await roster.getByRole('button', { name: '開始臨床技能評核' }).click();
  await page.waitForURL(url => url.searchParams.get('from') === 'teacher-learners' && !url.searchParams.has('admin'), { timeout: 15000 });
  await expect(page.locator('#pgy-assess-name')).toHaveValue('P2 測試學員');
  await expect(page.locator('#pgy-assess-empid')).toHaveValue('P2S001');
  await expect(page.locator('#pgy-assess-evaluator')).toHaveValue('P2 臨床教師');
  await expect(page.locator('#pgy-assessment-form-title')).toContainText('DOPS');

  for (let index = 0; index < 6; index += 1) {
    await page.locator(`input[name="pgy-rating-${index}"][value="4"]`).check();
  }
  await page.locator('#pgy-assess-comments').fill('P2 E2E 完成臨床技能觀察');
  await page.locator('#pgy-assess-submit').click();
  await expect(page.locator('#pgy-assess-status')).toContainText('已完成全部 6 項評核並儲存', { timeout: 15000 });

  const returnButton = page.locator('#teacher-p2-return-after-assessment');
  await expect(returnButton).toBeVisible();
  await returnButton.click();
  await page.waitForURL(url => url.searchParams.get('admin') === '1' && url.searchParams.get('workspace') === 'assessment' && url.searchParams.get('persona') === 'teacher', { timeout: 15000 });

  const refreshedRoster = page.locator('#teacher-learners-p2');
  await expect(refreshedRoster).toBeVisible({ timeout: 15000 });
  await expect(refreshedRoster).toContainText('P2 測試學員');

  await refreshedRoster.getByRole('button', { name: '能力追蹤' }).click();
  const competency = page.locator('#teacher-competency-detail-p2');
  await expect(competency).toBeVisible();
  await expect(competency).toContainText('DOPS');
  await expect(competency).toContainText('4.0 / 5');
  await expect(competency).toContainText('不合併成 AI 能力總分');

  await refreshedRoster.getByRole('button', { name: '教學分析' }).click();
  const analytics = page.locator('#teacher-teaching-analytics-p2');
  await expect(analytics).toBeVisible();
  await expect(analytics).toContainText('教學分析');
  await expect(analytics).toContainText('P2 測試學員');
  await expect(analytics).toContainText('正式評量平均');
  await expect(analytics).toContainText('4.0');
  await expect(analytics).toContainText('不產生 AI 能力總分或預測');

  const recordsResponse = await page.request.get(`${baseURL}/api/pgy-assessments?emp_id=P2S001`);
  expect(recordsResponse.status()).toBe(200);
  const records = await recordsResponse.json();
  const saved = records.find(item => item.empId === 'P2S001' && item.assessmentType === 'dops');
  expect(saved).toBeTruthy();
  expect(saved.evaluatorName).toBe('P2 臨床教師');
  expect(saved.name).toBe('P2 測試學員');
  expect(saved.details.ratings).toHaveLength(6);
  expect(saved.details.ratings.every(item => item.rating === 4)).toBeTruthy();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
