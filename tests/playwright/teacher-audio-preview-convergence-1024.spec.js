const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('AI narration keeps one accessible preview control across workspace hydration', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"><section id="teacher-media-script-1014"></section></section><select id="teacher-script-material-1014"><option value="doc-1">教材文件</option></select></main>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      hasPermission: permission => permission === 'material.manage'
    });
    window.fetch = async url => {
      if (String(url) === '/api/media-audio/status') return { ok: true, json: async () => ({ enabled: true, defaultVoice: 'zf_xiaoxiao', voices: ['zf_xiaoxiao'], disclosure: 'AI 合成語音' }) };
      if (String(url).startsWith('/api/media-scripts')) return { ok: true, json: async () => [] };
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-media-audio-1014.js') });
  await page.addScriptTag({ path: asset('teacher-assignment-experience-1014.js') });

  const narration = page.locator('#teacher-media-audio-1014');
  await expect(narration.getByRole('button', { name: '▶ 試聽聲音' })).toHaveCount(1);
  await expect(narration.getByRole('button', { name: '🎙️ 產生 AI 語音' })).toHaveCount(1);
  await expect(narration.locator('#teacher-audio-status-1014')).toHaveCount(1);

  await page.locator('main').evaluate(node => node.appendChild(document.createElement('div')));
  await expect(narration.getByRole('button', { name: '▶ 試聽聲音' })).toHaveCount(1);
  await expect(narration.locator('#teacher-audio-status-1014')).toHaveCount(1);
});

test('formal narration job disables the single preview control with one status message', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"><section id="teacher-media-script-1014"></section></section><select id="teacher-script-material-1014"><option value="doc-1">教材文件</option></select></main>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({ roles: new Set(['clinical_teacher']), hasPermission: permission => permission === 'material.manage' });
    window.fetch = async url => {
      if (String(url) === '/api/media-audio/status') return { ok: true, json: async () => ({ enabled: true, defaultVoice: 'zf_xiaoxiao', voices: ['zf_xiaoxiao'], activeJob: { progress: { percent: 40, stage: '產生免費 AI 語音' } } }) };
      if (String(url).startsWith('/api/media-scripts')) return { ok: true, json: async () => [] };
      return { ok: true, json: async () => ({}) };
    };
  });
  await page.addScriptTag({ path: asset('teacher-media-audio-1014.js') });
  await page.addScriptTag({ path: asset('teacher-assignment-experience-1014.js') });
  const narration = page.locator('#teacher-media-audio-1014');
  await expect(narration.getByRole('button', { name: '▶ 試聽聲音' })).toBeDisabled();
  await expect(narration.locator('#teacher-audio-status-1014')).toContainText('正式 AI 語音工作正在排隊或處理中');
  await expect(narration.locator('#teacher-audio-status-1014')).toHaveCount(1);
});
