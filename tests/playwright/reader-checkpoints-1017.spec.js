const { test, expect } = require('@playwright/test');

const baseURL = process.env.TEACHER_UI_BASE_URL || 'http://127.0.0.1:4173';
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);
const MATERIAL = {
  id: 'cp-deck', title: '檢核題簡報', filename: 'deck.pptx', pageCount: 5,
  imageFolder: '/uploaded-slides/cp-deck', slideFormat: 'png', viewerMode: 'slides',
  readerMode: 'presentation', active: true, isBuiltin: false, courseId: '', materialType: 'teaching', storageMeta: {},
};
const QUESTION = { id: 'cp1', page: 2, question: '第二頁講的是？', options: ['稀釋', '固定', '染色'], answered: false };

async function openReader(page, viewport, answers) {
  await page.setViewportSize(viewport);
  const errors = [];
  page.on('pageerror', e => errors.push(String(e && e.message || e)));
  await page.route('**/api/slides*', route => route.fulfill({ json: [MATERIAL] }));
  await page.route('**/uploaded-slides/**', route => route.fulfill({ body: PNG, contentType: 'image/png' }));
  await page.route('**/api/materials/cp-deck/checkpoints', route => route.fulfill({ json: { items: [QUESTION] } }));
  await page.route('**/api/slide-checkpoints/cp1/answer', route => route.fulfill({ json: answers.shift() }));
  await page.goto(`${baseURL}/system`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.openMaterial === 'function' && (window.cachedSlidesList || []).length >= 1, null, { timeout: 15000 });
  await page.evaluate(() => window.openMaterial('cp-deck'));
  await expect(page.locator('#slide-viewer-page-info')).toContainText('第 1 / 5 頁');
  return errors;
}

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 800 }]) {
  test(`checkpoint: wrong twice, review, return, never locked (${viewport.width}px)`, async ({ page }) => {
    const base = { id: 'cp1', page: 2, question: QUESTION.question, options: QUESTION.options, answered: true, firstCorrect: false, explanation: '固定細胞形態' };
    const errors = await openReader(page, viewport, [
      { ...base, attempts: 1, canRetry: true, isCorrect: false, chosenIndex: 0 },
      { ...base, attempts: 2, canRetry: false, isCorrect: false, chosenIndex: 2, firstChosenIndex: 0, correctIndex: 1 },
    ]);
    const card = page.locator('#aa-checkpoint-card');
    await page.locator('#slide-next-btn').click();
    await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');
    await expect(card).toHaveCount(0);
    await page.locator('#slide-next-btn').click();
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'A. 稀釋' }).click();
    await expect(card).toContainText('答錯了，先看說明再試一次');
    await expect(card).not.toContainText('（正確）');
    await expect(card.getByRole('button', { name: '繼續往下' })).toBeVisible();

    await card.getByRole('button', { name: '回看第 2 頁' }).click();
    await expect(page.locator('#slide-viewer-page-info')).toContainText('第 2 / 5 頁');
    const bar = page.locator('#aa-checkpoint-return');
    await expect(bar).toBeVisible();
    await page.screenshot({ path: `test-results/checkpoint-review-${viewport.width}.png` });
    await bar.getByRole('button', { name: /回到第 3 頁/ }).click();
    await expect(page.locator('#slide-viewer-page-info')).toContainText('第 3 / 5 頁');

    await expect(card).toBeVisible();
    await card.getByRole('button', { name: '再答一次' }).click();
    await card.getByRole('button', { name: 'C. 染色' }).click();
    await expect(card).toContainText('還是答錯了');
    await expect(card).toContainText('B. 固定（正確）');
    await page.screenshot({ path: `test-results/checkpoint-second-wrong-${viewport.width}.png` });
    const box = await card.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
    await card.getByRole('button', { name: '繼續往下' }).click();
    await expect(card).toHaveCount(0);

    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await expect(page.locator('#slide-viewer-page-info')).toContainText('第 5 / 5 頁');
    await expect(page.locator('#aa-checkpoint-summary')).toContainText('這幾頁建議再看一次');
    expect(errors).toEqual([]);
  });
}

test('desktop reader arrows fade when idle and come back on mouse move', async ({ page }) => {
  await openReader(page, { width: 1280, height: 800 }, []);
  const shell = page.locator('#slide-viewer-shell');
  await page.mouse.move(600, 400);
  await expect(shell).not.toHaveClass(/reader-idle/);
  await expect(shell).toHaveClass(/reader-idle/, { timeout: 6000 });
  await page.mouse.move(610, 420);
  await expect(shell).not.toHaveClass(/reader-idle/);
});
