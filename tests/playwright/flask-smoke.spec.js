const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_FLASK_BASE_URL || 'http://127.0.0.1:4174';


test('real Flask factory keeps auth session, CSP and system surface working', async ({ page }) => {
  const landing = await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  expect(landing.status()).toBe(200);

  const login = await page.evaluate(async () => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'ci-admin', password: 'ci-playwright-password' }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(login.status).toBe(200);
  expect(login.body.ok).toBeTruthy();
  expect(login.body.user.username).toBe('ci-admin');

  const me = await page.evaluate(async () => {
    const response = await fetch('/api/auth/me');
    return { status: response.status, body: await response.json() };
  });
  expect(me.status).toBe(200);
  expect(me.body.authenticated).toBeTruthy();
  expect(me.body.user.username).toBe('ci-admin');

  const system = await page.goto(`${baseURL}/system`, { waitUntil: 'domcontentloaded' });
  expect(system.status()).toBe(200);
  const csp = system.headers()['content-security-policy'] || '';
  expect(csp).toContain("script-src-attr 'none'");
  expect(csp).toContain("object-src 'none'");
  await expect(page.locator('#admin-modal')).toBeAttached();

  const workerStatus = await page.evaluate(async () => {
    const response = await fetch('/api/material-jobs?limit=20');
    return { status: response.status, body: await response.json() };
  });
  expect(workerStatus.status).toBe(200);
  expect(workerStatus.body).toHaveProperty('workerStatusAvailable');
  expect(Array.isArray(workerStatus.body.workers)).toBeTruthy();
});
