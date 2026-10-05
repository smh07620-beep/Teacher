const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('AI teaching video lets the teacher preview the selected narration voice', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"></section></main>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({ roles: new Set(['clinical_teacher']) });
    window.playCalls = 0;
    window.HTMLMediaElement.prototype.play = () => { window.playCalls += 1; return Promise.resolve(); };
    window.calls = [];
    window.fetch = async (url, options = {}) => {
      window.calls.push({ url: String(url), method: options.method || 'GET' });
      if (String(url) === '/api/ai-videos/status') return { ok: true, json: async () => ({ storage: { available: true }, capabilities: { 'video.create': true } }) };
      if (String(url) === '/api/media-audio/preview') return { ok: true, json: async () => ({ jobId: 'voice-preview-1' }) };
      if (String(url).includes('/api/media-audio/jobs/voice-preview-1')) return { ok: true, json: async () => ({ status: 'completed', result: { previewUrl: '/preview/voice.wav' } }) };
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-video-1015.js') });
  await expect(page.getByRole('button', { name: '▶ 試聽聲音' })).toBeVisible();
  await page.locator('#teacher-ai-video-voice-1015').selectOption('zm_yunxi');
  await page.getByRole('button', { name: '▶ 試聽聲音' }).click();
  await expect(page.locator('#teacher-ai-video-voice-player-1015')).toHaveAttribute('src', '/preview/voice.wav');
  await expect(page.locator('#teacher-ai-video-voice-player-1015')).toBeVisible();
  await expect(page.getByRole('button', { name: '▶ 播放試聽' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.playCalls)).toBe(0);
  await page.getByRole('button', { name: '▶ 播放試聽' }).click();
  await expect.poll(() => page.evaluate(() => window.playCalls)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.calls)).toContainEqual({ url: '/api/media-audio/preview', method: 'POST' });
});

test('AI teaching video plays an already cached WAV without starting a poll loop', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"></section></main>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({ roles: new Set(['clinical_teacher']) });
    window.HTMLMediaElement.prototype.load = () => {};
    window.HTMLMediaElement.prototype.play = () => Promise.resolve();
    window.previewPolls = 0;
    window.fetch = async (url, options = {}) => {
      if (String(url) === '/api/ai-videos/status') return { ok: true, json: async () => ({ storage: { available: true }, capabilities: { 'video.create': true } }) };
      if (String(url) === '/api/media-audio/preview') return { ok: true, json: async () => ({ status: 'completed', result: { previewUrl: 'https://r2.example/voice.wav', mimeType: 'audio/wav' } }) };
      if (String(url).includes('/api/media-audio/jobs/')) window.previewPolls += 1;
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-video-1015.js') });
  await page.getByRole('button', { name: '▶ 試聽聲音' }).click();
  await expect(page.locator('#teacher-ai-video-voice-player-1015')).toHaveAttribute('src', 'https://r2.example/voice.wav');
  await expect.poll(() => page.evaluate(() => window.previewPolls)).toBe(0);
  await expect(page.locator('#teacher-ai-video-status-1015')).toContainText('試聽已準備完成');
});
