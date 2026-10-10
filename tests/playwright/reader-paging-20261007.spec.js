const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';

// 1x1 transparent PNG, enough for the browser to treat the page image as loaded.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

// Regex, not a glob: a retry appends ?r=<token>, and globs match the whole URL.
const PAGE_IMAGE = /\/material-preview\/[^/]+\/page\/\d+\.png(\?.*)?$/;

const MATERIALS = [
  {
    id: 'rd-images', title: '影像模式簡報', filename: 'deck.pptx', pageCount: 5,
    imageFolder: '/uploaded-slides/rd-images', slideFormat: 'png', viewerMode: 'slides',
    readerMode: 'presentation', active: true, isBuiltin: false, courseId: '', materialType: 'teaching', storageMeta: {},
  },
  {
    id: 'rd-pdf', title: '單一PDF簡報', filename: 'deck2.pptx', pageCount: 5,
    viewerMode: 'preview_pdf', previewUrl: '/material-preview/rd-pdf',
    readerMode: 'presentation', active: true, isBuiltin: false, courseId: '', materialType: 'teaching',
    storageMeta: { previewMode: 'single_pdf' },
  },
];

async function openReader(page, materialId, viewport) {
  await page.setViewportSize(viewport);
  await page.route('**/api/slides*', route => route.fulfill({ json: MATERIALS }));
  await page.route('**/uploaded-slides/**', route => route.fulfill({ body: PNG, contentType: 'image/png' }));
  await page.route(PAGE_IMAGE, route => route.fulfill({ body: PNG, contentType: 'image/png' }));
  await page.goto(`${baseURL}/system`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.openMaterial === 'function' && (window.cachedSlidesList || []).length >= 2, null, { timeout: 15000 });
  await page.evaluate(id => window.openMaterial(id), materialId);
  await expect(page.locator('#slide-viewer-modal')).toBeVisible();
  await expect(page.locator('#slide-viewer-page-info')).toContainText('第 1 / 5 頁');
}

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 800 }]) {
  for (const materialId of ['rd-images', 'rd-pdf']) {
    test(`reader pages forward/back by button and keyboard (${materialId} @ ${viewport.width}px)`, async ({ page }) => {
      await openReader(page, materialId, viewport);

      await page.locator('#slide-next-btn').click();
      await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');

      await page.keyboard.press('ArrowRight');
      await expect(page.locator('#slide-viewer-page-info')).toContainText('第 3 / 5 頁');

      await page.locator('#slide-prev-btn').click();
      await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');

      await page.keyboard.press('ArrowLeft');
      await expect(page.locator('#slide-viewer-page-info')).toContainText('第 1 / 5 頁');
      await expect(page.locator('#slide-prev-btn')).toBeDisabled();
    });
  }
}

test('a failed page image shows a visible retry that recovers without losing the page', async ({ page }) => {
  let failPages = true;
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.route('**/api/slides*', route => route.fulfill({ json: MATERIALS }));
  await page.route('**/uploaded-slides/**', route => route.fulfill({ body: PNG, contentType: 'image/png' }));
  await page.route(PAGE_IMAGE, route => {
    const url = route.request().url();
    // Page 1 always loads; page 2 fails until the test flips the switch.
    if (failPages && /\/page\/2\.png/.test(url)) return route.fulfill({ status: 409, body: 'no' });
    return route.fulfill({ body: PNG, contentType: 'image/png' });
  });
  await page.goto(`${baseURL}/system`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.openMaterial === 'function' && (window.cachedSlidesList || []).length >= 2, null, { timeout: 15000 });
  await page.evaluate(() => window.openMaterial('rd-pdf'));
  await expect(page.locator('#slide-viewer-page-info')).toContainText('第 1 / 5 頁');
  await expect(page.locator('#slide-page-error')).toBeHidden();

  await page.locator('#slide-next-btn').click();
  // The reader quietly auto-retries a failed page (0.7 s + 1.6 s + 3.2 s) before showing the error.
  await expect(page.locator('#slide-page-error')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#slide-page-error')).toContainText('重新載入此頁');
  // The reader still knows which page the learner is on.
  await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');

  failPages = false;
  await page.locator('#slide-page-error button').click();
  await expect(page.locator('#slide-page-error')).toBeHidden();
  await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');
});
