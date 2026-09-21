const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_FLASK_BASE_URL || 'http://127.0.0.1:4174';

async function bodyAndHeaders(request, path) {
  const response = await request.get(`${baseURL}${path}`);
  return {
    response,
    body: await response.text(),
    headers: response.headers(),
  };
}

test('canonical Flask composition serves health, readiness and anonymous auth', async ({ request }) => {
  const health = await request.get(`${baseURL}/health`);
  expect(health.status()).toBe(200);
  const healthBody = await health.json();
  expect(healthBody.ok).toBeTruthy();
  expect(healthBody.database.ok).toBeTruthy();
  expect(healthBody.migrations.ok).toBeTruthy();

  const ready = await request.get(`${baseURL}/ready`);
  expect(ready.status()).toBe(200);

  const auth = await request.get(`${baseURL}/api/auth/me`);
  expect(auth.status()).toBe(200);
  expect(await auth.json()).toEqual({ authenticated: false, user: null });
});

test('real portal response has enforced CSP and runtime asset injection', async ({ request }) => {
  const { response, body, headers } = await bodyAndHeaders(request, '/');
  expect(response.status()).toBe(200);
  expect(headers['content-security-policy']).toContain("script-src-attr 'none'");
  expect(headers['content-security-policy']).not.toContain("script-src 'self' 'unsafe-inline'");
  expect(body).toContain('/home-profile-title-71.js?v=playwright-real-flask');
  expect(body).toContain('/portal-navigation-73.js?v=playwright-real-flask');
});

test('real system response includes canonical admin assets under CSP', async ({ request }) => {
  const { response, body, headers } = await bodyAndHeaders(request, '/system');
  expect(response.status()).toBe(200);
  expect(headers['content-security-policy']).toContain("script-src-attr 'none'");
  expect(body).toContain('/worker-status-70.js?v=playwright-real-flask');
  expect(body).toContain('/admin-workspace.js?v=playwright-real-flask');
  expect(body).toContain('/system-csp-actions.js?v=playwright-real-flask');
});

test('real learner portal does not horizontally overflow on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const response = await page.goto(`${baseURL}/`, { waitUntil: 'domcontentloaded' });
  expect(response.status()).toBe(200);
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.viewport + 2);
});
