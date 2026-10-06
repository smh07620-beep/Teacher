const { test, expect } = require('@playwright/test');
const baseURL = process.env.TEACHER_AI_MEDIA_FULLSTACK_BASE_URL || 'http://127.0.0.1:4176';
const password = process.env.TEACHER_CI_BROWSER_PASSWORD || '';
async function api(page, path, body, method = 'POST') { return page.evaluate(async ({path, body, method}) => { const r = await fetch(path, {method, credentials:'same-origin', headers:body?{'Content-Type':'application/json'}:{}, body:body?JSON.stringify(body):undefined}); return {status:r.status, body:await r.json()}; }, {path,body,method}); }
test('AI questions use real route, durable job, Worker and question-bank import', async ({ page }) => {
  await page.goto(`${baseURL}/login?next=${encodeURIComponent('/system?area=internal&group=grpBio&admin=1')}`);
  await page.locator('#login-username').fill('e2eteacher'); await page.locator('#login-password').fill(password);
  await page.locator('#login-form button[type="submit"]').click(); await page.waitForURL(url => !url.pathname.endsWith('/login'));
  const category = await api(page, '/api/quiz-categories', {title:'E2E AI 考題',group:'grpBio',area:'internal',drawCount:1}); expect(category.status).toBe(200);
  const job = await api(page, '/api/ai-questions/generate', {quizCategoryId:category.body.id,materialIds:['e2e-source'],count:1,questionType:'choice',difficulty:'standard',strategy:'auto'}); expect(job.status).toBe(202);
  await expect.poll(async () => (await api(page, `/api/ai-questions/jobs/${job.body.jobId}`, null, 'GET')).body.status, {timeout:30000}).toBe('completed');
  const state = await api(page, `/api/ai-questions/jobs/${job.body.jobId}`, null, 'GET'); expect(state.body.result.questions).toHaveLength(1);
  const imported = await api(page, '/api/ai-questions/import', {quizCategoryId:category.body.id,questions:state.body.result.questions}); expect(imported.body.imported).toBe(1);
  const visible = await api(page, `/api/quiz-questions?category=${category.body.id}`, null, 'GET'); expect(visible.body[0]).toMatchObject({questionType:'choice',active:true});
});
