const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

async function installTeacherRBAC(page) {
  await page.evaluate(() => {
    window.currentGroupKey = 'grpBio';
    window.currentTrainingArea = 'internal';
    window.TeacherRBAC681Ready = Promise.resolve({
      roles: new Set(['clinical_teacher']),
      user: { preferredGroup: 'grpBio', preferredArea: 'internal' },
      hasPermission: permission => permission === 'material.manage'
    });
  });
}

function completedDraftResult(sourceMaterialCount) {
  return {
    status: 'completed',
    progress: { percent: 100, stage: '完成', detail: '多來源整理完成' },
    result: {
      title: '整合來源｜投影片大綱',
      body: '第 1 張：目的與範圍。\\n- 整合來源重點。\\n- 保留原始步驟與警示。\\n第 2 張：流程。\\n- 依教材內容整理。\\n※ 本內容為 AI 草稿，需由教師確認後方可發布。',
      outputType: 'slides',
      outputLabel: '投影片大綱',
      sourceTitle: '整合來源',
      sourceMaterialCount,
      sourceChunks: [{ materialId: 'mat-existing', chunkId: 'chunk-1', section: 'SOP' }],
      sourceWarnings: [],
      provider: 'groq',
      model: 'test-model',
      fallbackUsed: false
    }
  };
}

test('existing material alone can create an AI slide draft end to end in the authoring UI', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"></section></main>');
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.generatePayload1030 = null;
    window.fetch = async (url, options = {}) => {
      const target = String(url);
      if (target === '/api/slides/admin') {
        return {
          ok: true,
          json: async () => [{
            id: 'mat-existing',
            title: 'C503 操作與維護',
            filename: 'c503.pdf',
            group: 'grpBio',
            area: 'internal',
            storageBackend: 'r2',
            active: true
          }]
        };
      }
      if (target.startsWith('/api/ai-material-drafts?materialId=')) {
        return { ok: true, json: async () => [] };
      }
      if (target === '/api/ai-material-drafts/generate' && options.method === 'POST') {
        window.generatePayload1030 = JSON.parse(options.body);
        return { ok: true, status: 202, json: async () => ({ jobId: 'msjob-existing' }) };
      }
      if (target === '/api/ai-material-drafts/jobs/msjob-existing') {
        return { ok: true, json: async () => ({
          status: 'completed',
          progress: { percent: 100, stage: '完成', detail: '既有教材整理完成' },
          result: {
            title: 'C503 操作與維護｜投影片大綱',
            body: '第 1 張：目的與範圍。\\n- 說明 C503 教學目標。\\n- 保留教材原始步驟。\\n第 2 張：操作流程。\\n- 依教材內容整理。\\n※ 本內容為 AI 草稿，需由教師確認後方可發布。',
            outputType: 'slides',
            outputLabel: '投影片大綱',
            sourceTitle: 'C503 操作與維護',
            sourceMaterialCount: 1,
            sourceChunks: [{ materialId: 'mat-existing', chunkId: 'chunk-1', section: '操作流程' }],
            sourceWarnings: [],
            provider: 'groq',
            model: 'test-model',
            fallbackUsed: false
          }
        }) };
      }
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-material-1014.js') });
  const source = page.locator('#teacher-ai-material-source-1014');
  await expect(source).toBeVisible();
  await expect(source).toContainText('C503 操作與維護');
  await source.selectOption(['mat-existing']);
  await page.locator('#teacher-ai-material-generate-1014').click();

  await expect.poll(() => page.evaluate(() => window.generatePayload1030)).toEqual({
    materialId: 'mat-existing',
    referenceMaterialIds: [],
    outputType: 'slides',
    targetMinutes: 5,
    tone: 'clinical',
    focus: ''
  });
  await expect(page.locator('#teacher-ai-material-status-1014')).toContainText('AI 草稿完成');
  await expect(page.locator('#teacher-ai-material-editor-1014')).toBeVisible();
  await expect(page.locator('#teacher-ai-material-source-info-1014')).toContainText('成功讀取：1 份來源');
});

test('new private uploads and an existing material are combined into one deterministic AI request', async ({ page }) => {
  await page.setContent('<main><section id="teacher-media-production-1014"></section></main>');
  await installTeacherRBAC(page);
  await page.evaluate(() => {
    window.uploadedSources1030 = [];
    window.uploadContracts1030 = [];
    window.generatePayloadMixed1030 = null;
    window.MaterialUploadClient = {
      enqueue: async (form, options = {}) => {
        const index = window.uploadedSources1030.length + 1;
        const materialId = `mat-upload-${index}`;
        const jobId = `job-source-${index}`;
        window.uploadedSources1030.push(materialId);
        window.uploadContracts1030.push({
          materialId,
          fileName: form.get('file')?.name || '',
          authoringOnly: form.get('authoringOnly'),
          group: form.get('group'),
          area: form.get('area'),
          fallbackToSameOriginQueue: options.fallbackToSameOriginQueue
        });
        options.onProgress?.({ percent: 100 });
        return { accepted: true, status: 'queued', jobId, materialId };
      }
    };
    window.fetch = async (url, options = {}) => {
      const target = String(url);
      if (target === '/api/slides/admin') {
        return {
          ok: true,
          json: async () => [
            {
              id: 'mat-existing',
              title: '既有生化 SOP',
              filename: 'existing.pdf',
              group: 'grpBio',
              area: 'internal',
              storageBackend: 'r2',
              active: true
            },
            ...window.uploadedSources1030.map((id, index) => ({
              id,
              title: index === 0 ? '補充資料 A' : '補充資料 B',
              filename: index === 0 ? 'extra-a.pdf' : 'extra-b.docx',
              group: 'grpBio',
              area: 'internal',
              storageBackend: 'r2',
              active: false
            }))
          ]
        };
      }
      if (target.startsWith('/api/material-jobs/job-source-')) {
        return { ok: true, json: async () => ({ status: 'completed', stage: '已完成', detail: '來源已建立' }) };
      }
      if (target.startsWith('/api/ai-material-drafts?materialId=')) {
        return { ok: true, json: async () => [] };
      }
      if (target === '/api/ai-material-drafts/generate' && options.method === 'POST') {
        window.generatePayloadMixed1030 = JSON.parse(options.body);
        return { ok: true, status: 202, json: async () => ({ jobId: 'msjob-mixed' }) };
      }
      if (target === '/api/ai-material-drafts/jobs/msjob-mixed') {
        return { ok: true, json: async () => ({
          status: 'completed',
          progress: { percent: 100, stage: '完成', detail: '三份來源整理完成' },
          result: {
            title: '多來源整合｜投影片大綱',
            body: '第 1 張：多來源目的。\\n- 整合兩份新資料與一份既有教材。\\n- 保留各來源的重要警示。\\n第 2 張：流程。\\n- 依來源內容整理。\\n※ 本內容為 AI 草稿，需由教師確認後方可發布。',
            outputType: 'slides',
            outputLabel: '投影片大綱',
            sourceTitle: '補充資料 A',
            sourceMaterialCount: 3,
            sourceChunks: [{ materialId: 'mat-upload-1', chunkId: 'chunk-1', section: '來源' }],
            sourceWarnings: [],
            provider: 'groq',
            model: 'test-model',
            fallbackUsed: false
          }
        }) };
      }
      return { ok: true, json: async () => ({}) };
    };
  });

  await page.addScriptTag({ path: asset('teacher-ai-material-1014.js') });

  await page.locator('#teacher-ai-material-file-1014').setInputFiles([
    { name: 'extra-a.pdf', mimeType: 'application/pdf', buffer: Buffer.from('source A') },
    { name: 'extra-b.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: Buffer.from('source B') }
  ]);
  await page.locator('#teacher-ai-material-upload-1014').click();

  await expect(page.locator('#teacher-ai-material-status-1014')).toContainText('已加入 2 份原始資料');
  await expect.poll(() => page.evaluate(() => window.uploadContracts1030)).toEqual([
    {
      materialId: 'mat-upload-1',
      fileName: 'extra-a.pdf',
      authoringOnly: '1',
      group: 'grpBio',
      area: 'internal',
      fallbackToSameOriginQueue: false
    },
    {
      materialId: 'mat-upload-2',
      fileName: 'extra-b.docx',
      authoringOnly: '1',
      group: 'grpBio',
      area: 'internal',
      fallbackToSameOriginQueue: false
    }
  ]);

  const source = page.locator('#teacher-ai-material-source-1014');
  await expect(source).toContainText('既有生化 SOP');
  await source.selectOption(['mat-existing']);
  await page.locator('#teacher-ai-material-generate-1014').click();

  await expect.poll(() => page.evaluate(() => window.generatePayloadMixed1030)).toEqual({
    materialId: 'mat-upload-1',
    referenceMaterialIds: ['mat-upload-2', 'mat-existing'],
    outputType: 'slides',
    targetMinutes: 5,
    tone: 'clinical',
    focus: ''
  });
  await expect(page.locator('#teacher-ai-material-status-1014')).toContainText('AI 草稿完成');
  await expect(page.locator('#teacher-ai-material-source-info-1014')).toContainText('成功讀取：3 份來源');
});
