const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('shared AI media source loads directly and drives narration subtitle and video inputs', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="teacher-media-production-1014">
        <select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select>
        <p id="teacher-media-next-step-1018"></p>
        <select id="teacher-script-material-1014"><option value="">選擇教材…</option></select>
        <section id="teacher-media-subtitle-1014">
          <label>語言代碼<input id="teacher-subtitle-language-1014" value="zh-TW" class="learning-input"></label>
        </section>
        <section id="teacher-ai-video-1015">
          <h4>教學影片</h4><p>說明</p>
          <select id="teacher-ai-video-presentation-1015"><option value="">請先選擇來源教材</option></select>
          <p id="teacher-ai-video-status-1015"></p>
        </section>
        <section id="teacher-media-powerpoint-entry-1018"><div><b>PowerPoint</b><p>舊說明</p></div><button id="teacher-media-open-powerpoint-1018">AI PowerPoint 製作</button></section>
      </section>
    </main>
  `);
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
    window.TeacherMediaSubtitle1014 = {
      selectMaterial: value => { window.subtitleMaterial1023 = value; }
    };
    window.TeacherMediaAudio1014 = {
      loadApprovedScripts: async () => { window.audioReloaded1023 = true; }
    };
    window.fetch = async url => {
      const text = String(url);
      if (text.includes('/api/slides/admin')) {
        return {
          ok: true,
          json: async () => [
            { id: 'doc-1', title: '生化 SOP', group: 'grpBio', area: 'internal', active: true },
            { id: 'movie-1', title: '教學影片.mp4', group: 'grpBio', area: 'internal', mimeType: 'video/mp4', active: true },
            { id: 'other', title: '其他組', group: 'grpBlood', area: 'internal', active: true }
          ]
        };
      }
      if (text.includes('/api/ai-presentations')) {
        return {
          ok: true,
          json: async () => [{ id: 'ppt-1', title: '生化教學簡報', revisionNumber: 2, status: 'approved', artifactReady: true }]
        };
      }
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });

  const source = page.locator('#teacher-media-source-1018');
  await expect(source).toBeEnabled();
  await expect(source.locator('option')).toHaveCount(3);
  await expect(source).toContainText('生化 SOP');
  await expect(source).not.toContainText('其他組');

  await expect(page.locator('#teacher-subtitle-language-1014')).toHaveJSProperty('tagName', 'SELECT');
  await expect(page.locator('#teacher-subtitle-language-1014')).toHaveValue('zh-TW');
  await expect(page.locator('#teacher-media-open-powerpoint-1018')).toHaveText('🖥️ 多資料 AI PowerPoint');
  await expect(page.locator('#teacher-media-powerpoint-entry-1018')).toContainText('一次加入多份 PDF、Word、PPT');

  await source.selectOption('doc-1');
  await expect.poll(() => page.evaluate(() => window.subtitleMaterial1023)).toBe('doc-1');
  await expect.poll(() => page.evaluate(() => window.audioReloaded1023)).toBe(true);
  await expect(page.locator('#teacher-script-material-1014')).toHaveValue('doc-1');
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toBeEnabled();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toHaveValue('ppt-1');
});

test('shared AI media source shows a useful empty state instead of hanging on loading', async ({ page }) => {
  await page.setContent('<select id="teacher-media-source-1018" disabled><option>正在載入可用教材…</option></select><p id="teacher-media-next-step-1018"></p>');
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
    window.fetch = async () => ({ ok: true, json: async () => [] });
  });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });
  await expect(page.locator('#teacher-media-source-1018')).toBeDisabled();
  await expect(page.locator('#teacher-media-source-1018')).toContainText('目前沒有可用教材');
  await expect(page.locator('#teacher-media-next-step-1018')).toContainText('請先上傳教材或建立 AI PowerPoint 來源');
});