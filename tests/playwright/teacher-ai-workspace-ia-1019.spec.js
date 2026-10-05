const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('AI PowerPoint stays in the authoring workspace while media studio only consumes approved revisions', async ({ page }) => {
  await page.setContent(`
    <main>
      <section id="admin-course-material-hub">
        <section id="teacher-ai-material-1014">
          <input id="teacher-ai-material-file-1014" type="file">
          <section id="teacher-ai-material-presentation-stage-1014">
            <section id="teacher-ai-presentation-1016"><h4>AI PowerPoint 製作室</h4></section>
          </section>
        </section>
      </section>
      <section id="teacher-media-production-1014">
        <section id="teacher-media-studio-shell-1018"></section>
        <section id="teacher-media-audio-1014"><h4>語音</h4><p class="mt-1">語音說明</p></section>
        <section id="teacher-media-subtitle-1014"><h4>字幕</h4></section>
        <section id="teacher-ai-video-1015">
          <h4>影片</h4><p class="mt-1">影片說明</p>
          <label>PowerPoint<input id="teacher-ai-video-presentation-1015"></label>
          <span id="teacher-ai-video-provider-1015"></span>
          <span id="teacher-ai-video-renderer-1015"></span>
        </section>
        <section id="teacher-media-script-1014">
          <label>來源教材<select id="teacher-script-material-1014"><option value="doc-1">教材文件</option></select></label>
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
    window.TeacherMediaSubtitle1014 = { selectMaterial: value => { window.subtitleSource = value; } };
    window.TeacherWorkspace1014 = { openCourse: async () => { window.legacyCourseJumped = true; } };
    window.fetch = async url => ({ ok: true, json: async () => String(url).includes('/api/ai-presentations') ? [] : [] });
  });

  await page.addScriptTag({ path: asset('teacher-ai-media-studio-1018.js') });
  await page.addScriptTag({ path: asset('teacher-ai-media-controls-1023.js') });

  await expect(page.locator('#teacher-ai-media-studio-1018')).toHaveCount(1);
  await expect(page.getByRole('tab')).toHaveCount(3);
  await expect(page.locator('#teacher-ai-material-presentation-stage-1014 > #teacher-ai-presentation-1016')).toHaveCount(1);
  await expect(page.locator('#teacher-media-advanced-1018 #teacher-ai-presentation-1016')).toHaveCount(0);
  await expect(page.locator('#teacher-media-advanced-1018 > summary')).toHaveText('媒體版本、品質與進階資訊');

  const shortcut = page.getByRole('button', { name: '🖥️ AI PowerPoint 製作' });
  await expect(shortcut).toBeVisible();
  await shortcut.click();
  await expect(page.locator('#teacher-media-powerpoint-workspace-1024')).toBeVisible();
  await expect(page.locator('#teacher-media-powerpoint-body-1024 > #teacher-ai-material-1014')).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean(window.legacyCourseJumped))).toBe(false);
});

test('legacy MVP readiness summary is removed instead of duplicating the media studio', async ({ page }) => {
  await page.setContent(`
    <section id="teacher-media-production-1014">
      <section id="teacher-media-mvp-summary-1014">10/14 MVP READY</section>
      <section id="teacher-media-studio-shell-1018">AI 媒體製作室</section>
    </section>
  `);
  await page.evaluate(() => {
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      hasPermission: permission => permission === 'material.manage'
    });
  });

  await page.addScriptTag({ path: asset('teacher-media-mvp-status-1014.js') });
  await expect(page.locator('#teacher-media-mvp-summary-1014')).toHaveCount(0);
  await expect(page.locator('#teacher-media-studio-shell-1018')).toHaveCount(1);
});
