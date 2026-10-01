const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('AI media studio hydrates when legacy panels arrive after the shell', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="teacher-media-production-1014">
        <section id="teacher-media-studio-shell-1018">
          <h4>AI 媒體製作室</h4>
        </section>
      </section>
    </main>
  `);
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      user: { preferredGroup: 'grpBio' },
      hasPermission: permission => permission === 'material.manage'
    });
    window.fetch = async url => ({
      ok: true,
      json: async () => String(url).includes('/api/ai-presentations') ? [] : []
    });
    window.TeacherMediaSubtitle1014 = {
      selectMaterial: value => { window.subtitleMaterial = value; }
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-studio-1018.js') });

  await expect(page.locator('#teacher-ai-media-studio-1018')).toHaveCount(1);
  await expect(page.getByRole('tab')).toHaveCount(3);
  await expect(page.locator('#teacher-media-waiting-audio-1018')).toHaveCount(1);

  await page.evaluate(() => {
    const media = document.getElementById('teacher-media-production-1014');
    media.insertAdjacentHTML('beforeend', `
      <section id="teacher-media-audio-1014"><h4>語音</h4><p class="mt-1">語音說明</p></section>
      <section id="teacher-media-subtitle-1014"><h4>字幕</h4></section>
      <section id="teacher-ai-video-1015"><h4>影片</h4><p class="mt-1">影片說明</p><label>PowerPoint<input id="teacher-ai-video-presentation-1015"></label><span id="teacher-ai-video-provider-1015"></span><span id="teacher-ai-video-renderer-1015"></span></section>
      <section id="teacher-media-script-1014"><label>來源教材<select id="teacher-script-material-1014"><option value="">選擇教材…</option><option value="doc-1">教材文件</option><option value="movie-1">教學影片.mp4</option></select></label></section>
    `);
    window.dispatchEvent(new CustomEvent('teacher-media-source-options-1014', {
      detail: {
        materials: [
          { id: 'doc-1', title: '教材文件', mimeType: 'application/pdf' },
          { id: 'movie-1', title: '教學影片.mp4', mimeType: 'video/mp4' }
        ],
        selectedId: 'doc-1'
      }
    }));
  });

  await expect(page.locator('#teacher-media-audio-1014').locator('..')).toHaveAttribute('id', 'teacher-media-panel-narration-1018');
  await expect(page.locator('#teacher-media-subtitle-1014').locator('..')).toHaveAttribute('id', 'teacher-media-panel-subtitle-1018');
  await expect(page.locator('#teacher-ai-video-1015').locator('..')).toHaveAttribute('id', 'teacher-media-panel-video-1018');
  await expect(page.locator('#teacher-media-waiting-audio-1018')).toHaveCount(0);
  await expect(page.locator('#teacher-media-source-1018')).toBeEnabled();
  await expect(page.locator('#teacher-media-source-1018')).toHaveValue('doc-1');

  await page.locator('#teacher-media-source-1018').selectOption('movie-1');
  await expect.poll(() => page.evaluate(() => window.subtitleMaterial)).toBe('movie-1');

  await page.evaluate(() => window.TeacherAIMediaStudio1018.refresh());
  await expect(page.locator('#teacher-ai-media-studio-1018')).toHaveCount(1);
  await expect(page.getByRole('tab')).toHaveCount(3);
});
