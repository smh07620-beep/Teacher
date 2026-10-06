const { test, expect } = require('playwright/test');
const path = require('path');

const asset = name => path.resolve(__dirname, '../../static', name);
if (process.env.TEACHER_PLAYWRIGHT_BROWSER) {
  test.use({ launchOptions: { executablePath: process.env.TEACHER_PLAYWRIGHT_BROWSER } });
}

test('guided course authoring keeps AI and assessment inside the four-step draft flow', async ({ page }) => {
  await page.setContent(`
    <select id="wizard-area"><option value="internal" selected>院內</option></select>
    <select id="wizard-group"><option value="grpBio" selected>生化</option></select>
    <input id="wizard-course-title">
    <textarea id="wizard-course-desc"></textarea>
    <input id="wizard-exam-title">
    <div id="course-wizard-legacy-fields"></div>
    <div><button id="wizard-create-btn" type="button">legacy create</button></div>
    <div id="admin-courses-list"></div>
    <div id="admin-course-material-hub"></div>
  `);

  await page.evaluate(() => {
    window.escapeHtml = value => String(value ?? '');
    window.currentTrainingArea = 'internal';
    window.currentGroupKey = 'grpBio';
    window.courseAuthoringTrace = [];
    window.courseAuthoringMaterials = [];

    window.TeacherRBAC681Ready = new Promise(resolve => {
      setTimeout(() => resolve({
        hasPermission: permission => ['learning.assign', 'course.manage', 'material.manage', 'question.manage', 'exam.manage'].includes(permission)
      }), 250);
    });

    const response = (data, status = 200) => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => data
    });

    window.fetch = async (url, options = {}) => {
      const target = String(url);
      const method = String(options.method || 'GET').toUpperCase();
      let body = {};
      try { body = typeof options.body === 'string' ? JSON.parse(options.body) : {}; } catch (_error) {}

      if (target.startsWith('/api/learning-assignments/audience-options')) {
        return response({
          group: 'grpBio',
          groups: [{ key: 'grpBio', label: '生化' }],
          allowedAssigneeTypes: ['group', 'user'],
          people: [{ username: 'student-1', name: '學員一' }]
        });
      }
      if (target.startsWith('/api/slides?area=')) return response([]);
      if (target === '/api/course-bundles' && method === 'POST') {
        window.courseAuthoringTrace.push({ type: 'bundle', body });
        return response({
          ok: true,
          workflowId: body.workflowId,
          course: {
            id: 'course-guided-1',
            area: body.area,
            group: body.group,
            title: body.title,
            desc: body.desc,
            active: false,
            lifecycleStatus: 'draft'
          },
          quizCategory: null
        }, 201);
      }
      if (target === '/api/slides/admin') {
        return response(window.courseAuthoringMaterials.map(item => ({ ...item })));
      }
      if (target.startsWith('/api/slides/') && method === 'PATCH') {
        const materialId = decodeURIComponent(target.split('/').pop());
        const existing = window.courseAuthoringMaterials.find(item => item.id === materialId)
          || { id: materialId, title: 'AI C503 PowerPoint', area: 'internal', group: 'grpBio', active: true };
        Object.assign(existing, body);
        if (!window.courseAuthoringMaterials.some(item => item.id === materialId)) window.courseAuthoringMaterials.push(existing);
        window.courseAuthoringTrace.push({ type: 'material-link', materialId, body });
        return response({ ok: true });
      }
      if (target === '/api/quiz-categories' && method === 'POST') {
        window.courseAuthoringTrace.push({ type: 'assessment-create', body });
        return response({
          id: 'cat-guided-1',
          area: body.area,
          group: body.group,
          courseId: body.courseId,
          title: body.title,
          active: false,
          reviewStatus: 'draft'
        }, 201);
      }
      if (target === '/api/quiz-categories/cat-guided-1/materials' && method === 'PUT') {
        window.courseAuthoringTrace.push({ type: 'assessment-materials', body });
        return response({ ok: true, linkedIds: body.materialIds || [], linked: (body.materialIds || []).length });
      }
      if (target === '/api/courses/course-guided-1/readiness') {
        window.courseAuthoringTrace.push({ type: 'readiness' });
        return response({ ready: true, lifecycleStatus: 'draft', blockers: [] });
      }
      if (target === '/api/courses/course-guided-1/lifecycle' && method === 'POST') {
        window.courseAuthoringTrace.push({ type: 'lifecycle', action: body.action });
        if (body.action === 'mark_ready') {
          return response({ course: { id: 'course-guided-1', lifecycleStatus: 'ready', active: false } });
        }
        if (body.action === 'publish') {
          window.coursePublished = true;
          return response({ course: { id: 'course-guided-1', lifecycleStatus: 'published', active: true } });
        }
      }
      throw new Error(`Unexpected request ${method} ${target}`);
    };

    window.openTeacherCourseMediaAuthoring = async mode => {
      window.courseAuthoringTrace.push({ type: 'media-open', mode });
      window.lastCourseMediaMode = mode;
      return true;
    };
    window.openTeacherCourseAssessmentAuthoring = async (categoryId, mode) => {
      window.courseAuthoringTrace.push({ type: 'assessment-open', categoryId, mode });
      window.lastAssessmentOpen = { categoryId, mode };
      return true;
    };
    window.switchAdminWorkspace = async workspace => {
      window.courseAuthoringTrace.push({ type: 'workspace', workspace });
      return true;
    };
    window.renderAdminCourseMaterialHub = async () => true;
    window.teacherContentStudioClose = () => true;
  });

  await page.addScriptTag({ path: asset('course-wizard-681.js') });

  await expect(page.locator('#course-wizard-681')).toContainText('正在確認你的學習指派權限');
  await expect(page.locator('#course-wizard-681')).not.toContainText('此帳號沒有「學習指派」權限');
  await expect(page.locator('#course-wizard-681')).toContainText('發布後立即建立學習指派', { timeout: 2500 });

  await page.locator('#cw681-title').fill('C503 操作與維護');
  await page.locator('#cw681-desc').fill('院內生化組教育訓練');
  await page.evaluate(() => window.courseWizard681Next());

  await expect(page.locator('#course-wizard-681')).toContainText('2. 教材與 AI 製作');
  await expect(page.locator('#course-wizard-681')).toContainText('AI PowerPoint');
  await expect(page.locator('#course-wizard-681')).not.toContainText('3. 評量與 AI');

  await page.locator('[data-cw-ai-plan="presentation"]').click();
  await expect(page.locator('#course-wizard-681')).toContainText('開啟 AI PowerPoint');
  await page.evaluate(() => window.courseWizard681OpenAiAuthoring());

  expect(await page.evaluate(() => window.lastCourseMediaMode)).toBe('presentation');
  const checkpoint = await page.evaluate(() => window.courseAuthoringTrace.find(item => item.type === 'bundle'));
  expect(checkpoint.body.examMode).toBe('later');
  expect(checkpoint.body.examTitle).toBe('');
  expect(checkpoint.body.title).toBe('C503 操作與維護');

  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('teacher-ai-presentation-published', {
      detail: {
        presentationId: 'ppt-guided-1',
        materialId: 'mat-ai-ppt-1',
        title: 'C503 AI 教學投影片'
      }
    }));
  });
  await expect(page.locator('#course-wizard-681')).toContainText('C503 AI 教學投影片');
  await expect(page.locator('#course-wizard-681')).toContainText('等待加入本課程');
  await page.evaluate(() => window.courseWizard681AttachAiProducts());
  await expect(page.locator('#course-wizard-681')).toContainText('已加入本課程');

  const materialLink = await page.evaluate(() => window.courseAuthoringTrace.find(item => item.type === 'material-link'));
  expect(materialLink.materialId).toBe('mat-ai-ppt-1');
  expect(materialLink.body.courseId).toBe('course-guided-1');

  await page.evaluate(() => window.courseWizard681Next());
  await expect(page.locator('#course-wizard-681')).toContainText('3. 評量／考卷');
  await expect(page.locator('#course-wizard-681')).toContainText('自己出題');
  await expect(page.locator('#course-wizard-681')).toContainText('AI 協助出題');
  await expect(page.locator('#course-wizard-681')).toContainText('進階：Blueprint／題型配額');
  await expect(page.locator('#course-wizard-681')).not.toContainText('從題庫選');

  await page.evaluate(() => window.courseWizard681SetMode('ai'));
  await page.locator('#cw681-exam').fill('C503 課後評量');
  await page.evaluate(() => window.courseWizard681OpenAssessmentAuthoring());

  const assessmentCreate = await page.evaluate(() => window.courseAuthoringTrace.find(item => item.type === 'assessment-create'));
  expect(assessmentCreate.body.courseId).toBe('course-guided-1');
  expect(assessmentCreate.body.title).toBe('C503 課後評量');
  expect(await page.evaluate(() => window.lastAssessmentOpen)).toEqual({ categoryId: 'cat-guided-1', mode: 'ai' });

  await page.evaluate(() => window.courseWizard681ResumeStep(3));
  await expect(page.locator('#course-wizard-681')).toContainText('✅ 考卷草稿已建立，可繼續編輯。');
  await page.evaluate(() => window.courseWizard681Next());

  await expect(page.locator('#course-wizard-681')).toContainText('4. 確認與發布');
  await expect(page.locator('#course-wizard-681')).toContainText('這一步是唯一正式發布點');
  await expect(page.locator('#course-wizard-681')).toContainText('AI 產物 1 份');

  await page.evaluate(() => window.courseWizard681CreateAndPublish());
  await expect.poll(() => page.evaluate(() => Boolean(window.coursePublished))).toBe(true);

  const trace = await page.evaluate(() => window.courseAuthoringTrace);
  expect(trace.filter(item => item.type === 'bundle')).toHaveLength(1);
  expect(trace.filter(item => item.type === 'assessment-create')).toHaveLength(1);
  expect(trace.filter(item => item.type === 'media-open')).toHaveLength(1);
  expect(trace.some(item => item.type === 'lifecycle' && item.action === 'mark_ready')).toBe(true);
  expect(trace.some(item => item.type === 'lifecycle' && item.action === 'publish')).toBe(true);
  expect(trace.filter(item => item.type === 'media-open')).toEqual([{ type: 'media-open', mode: 'presentation' }]);
});

test('AI question authoring exposes manual-equivalent core types', async ({ page }) => {
  await page.setContent(`
    <section data-ai-question-studio="cat-1">
      <select id="ai-type-cat-1">
        <option value="mixed_all">mixed</option>
        <option value="choice">choice</option>
        <option value="multi">multi</option>
        <option value="true_false">true false</option>
        <option value="fill">fill</option>
        <option value="essay">essay</option>
      </select>
      <div id="ai-candidates-cat-1"></div>
    </section>
  `);
  await page.evaluate(() => {
    window.escapeHtml = value => String(value ?? '');
  });
  await page.addScriptTag({ path: asset('admin-ai-questions.js') });

  await page.evaluate(() => {
    window.renderAiQuestionCandidates('cat-1', [
      { questionType: 'choice', question: '單選', options: ['A','B','C','D'], correct: 0, answerConfig: {} },
      { questionType: 'multi', question: '多選', options: ['A','B','C','D'], correct: 0, answerConfig: { correctIndices: [0,2] } },
      { questionType: 'true_false', question: '是非', options: ['是','否'], correct: 1, answerConfig: {} },
      { questionType: 'fill', question: '填空', options: [], correct: 0, answerConfig: { acceptedAnswers: ['答案'] } },
      { questionType: 'essay', question: '問答', options: [], correct: 0, answerConfig: {} }
    ], {});
  });

  await expect(page.locator('#ai-candidates-cat-1')).toContainText('是非題選項：是／否');
  const collected = await page.evaluate(() => window.collectAiCandidate('cat-1', 2, {
    questionType: 'true_false',
    answerConfig: {}
  }));
  expect(collected.questionType).toBe('true_false');
  expect(collected.options).toEqual(['是', '否']);
  expect(collected.correct).toBe(1);
});
