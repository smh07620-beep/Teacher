/* CSP-safe event delegation for the canonical /system surface.
 *
 * HTML/templates declare actions with data-csp-* attributes.  This runtime
 * deliberately avoids dynamic code construction and only invokes a fixed set of
 * already-owned global UI entrypoints.  A small compatibility migrator removes
 * legacy inline event attributes produced by not-yet-converged optional assets
 * before delegated handling.
 */
(() => {
  'use strict';

  const ATTRIBUTE_BY_EVENT = {
    click: 'data-csp-click',
    change: 'data-csp-change',
    input: 'data-csp-input',
    keydown: 'data-csp-keydown',
    pointermove: 'data-csp-pointermove',
    submit: 'data-csp-submit'
  };
  const LEGACY_TO_DATA = {
    onclick: ATTRIBUTE_BY_EVENT.click,
    onchange: ATTRIBUTE_BY_EVENT.change,
    oninput: ATTRIBUTE_BY_EVENT.input,
    onkeydown: ATTRIBUTE_BY_EVENT.keydown,
    onpointermove: ATTRIBUTE_BY_EVENT.pointermove,
    onsubmit: ATTRIBUTE_BY_EVENT.submit
  };

  const ALLOWED_ACTIONS = new Set([
    'adminAddQuizQuestion','adminBulkDeleteQuestions','adminBulkSetQuestionActive','adminBulkSetQuestionTag',
    'adminCreateQuizCategory','adminDeleteCourse','adminDeleteDocTemplate','adminDeletePgyTemplate',
    'adminDeleteQuizCategory','adminDeleteQuizQuestion','adminEditQuizCategory','adminEditSelectedQuestions',
    'adminGenerateAiQuestions','adminImportAiCandidates','adminImportQuizUrl','adminImportTslmEpa',
    'adminInlineQuestionTypeChanged','adminResultDetail','adminSaveExpandedQuestionEdits','adminSaveOneInlineQuestion',
    'adminSelectAllQuestions','adminSetProfileTag','adminSyncProfileTagChecks','adminToggleBlindMode',
    'adminToggleInlineQuestionEditor','adminToggleQuizQuestion','adminTriggerDocTemplateUpload','adminTriggerPgyTemplateUpload',
    'adminUpdateQuestionSelection','adminUploadMaterials','applyWizardMaterialBulkType','atlasPointerMove','atlasReset','atlasZoom',
    'cancelMaterialJob','clearAllRecords','closeAdminUserEditor','closeAtlas','closeEssayReview',
    'closeExternalMaterialCreateDrawer','closeMediaViewer','closeQuizMaterialLinker','closeSlideViewer',
    'courseWizard681Back','courseWizard681Continue','courseWizard681Create','courseWizard681FilesChanged',
    'courseWizard681Next','courseWizard681OpenCourse','courseWizard681RefreshMaterials','courseWizard681Reset',
    'courseWizard681SelectExisting','courseWizard681SetFileMeta','courseWizard681SetMode','createAdminAnnouncement',
    'createAdminUserAccount','createExternalMaterialFromDrawer','deleteAdminAnnouncement','deleteAdminMaterial',
    'deleteUploadedSlide','editAdminMaterial','exportCurrentPgyAssessmentWord','exportRecordToWord','exportToCSV',
    'filterAdminUserAccounts','filterAiMaterials','filterQuizMaterialLinker','goBackLearning','goToExamModule','goToSlidePage',
    'handleGlobalLearningSearchKey','jumpToAdminQuiz','loadMoreAiMaterials','loadMyPgyAssessments',
    'markMaterialComplete','migrateLocalMaterialsToR2','migrateMaterialsToMega','onAdminMaterialGroupChange',
    'onAdminQuizGroupChange','openAdminUserEditor','openAtlas','openAtlasCreate','openAtlasDocxWizard','openCourseExam',
    'openEssayReview','openExternalMaterialCreateDrawer','openMaterial','openQuestionImage','openQuizMaterialLinker',
    'openTeacherContentExam','openTeachingMaterials','previewCurrentExam','publishCurrentExam','readerMaterialSearch',
    'publishMaterialVersion','rebuildMaterialIndex','recommendAiMaterials','renderAdminAnnouncements','renderAdminCourseMaterialHub',
    'renderAdminMaterials','renderAdminPeople','renderAdminPgyAssessments','renderAdminQuizCategories','renderAdminSystemStatus',
    'renderAdminTable','renderAdminUserAccounts','renderCourseOverview','renderFilteredQuestionList','renderFormalAtlas',
    'renderMaterialJobs','renderStorageStatus','renderWizardMaterialClassifier','resetAdminUserPassword','resetCurrentQuiz',
    'retryMaterialJob','reviewCurrentExam','saveAdminUserEditor','saveExamSettings','saveQuizMaterialLinks',
    'openExamRemediationMaterials','restartExamAfterRemediation',
    'scrollToFirstFlagged','scrollToFirstUnanswered','scrollToReview','searchTeachingResources','selectEssay','selectFill',
    'selectPgyAssessmentType','setMediaRate','setMediaSize','setMediaVolume','slideViewerNext','slideViewerPrev',
    'slideViewerResetZoom','slideViewerZoom','submitEssayReview','submitPgyAssessment','submitQuiz','switchAdminWorkspace',
    'switchDynamicCategory','switchLearningModule','switchTeacherMode','syncExamDrawModeUI','syncGlobalLearningSearch',
    'teacher78FilterQuizCategories','teacher78LoadMoreQuizCategories','teacher78SetQuizStatus','teachingCloseEditor',
    'teachingEditCourse','teachingFinishReading','teachingNextMaterial','teachingSaveCourse','toggleAdminAnnouncement',
    'toggleAdminMaterial','toggleAdminModal','toggleAdminUserAccount','toggleAiMaterialSelection','toggleAtlasFullscreen','viewMaterialVersions',
    'toggleFlag','toggleMediaFullscreen','toggleQuizQuestionsPanel','toggleSlideFullscreen','updateAdminMaterialTypeFields',
    'updateManualQuestionType'
  ]);

  function migrateElement(element) {
    if (!(element instanceof Element)) return;
    for (const [legacy, dataName] of Object.entries(LEGACY_TO_DATA)) {
      if (!element.hasAttribute(legacy)) continue;
      const program = element.getAttribute(legacy) || '';
      if (program && !element.hasAttribute(dataName)) element.setAttribute(dataName, program);
      element.removeAttribute(legacy);
    }
  }

  function migrateTree(root) {
    if (!(root instanceof Element)) return;
    migrateElement(root);
    const selector = Object.keys(LEGACY_TO_DATA).map(name => `[${name}]`).join(',');
    root.querySelectorAll(selector).forEach(migrateElement);
  }

  function splitTopLevel(text, delimiter) {
    const parts = [];
    let current = '';
    let quote = '';
    let escaped = false;
    let depth = 0;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (escaped) {
        current += char;
        escaped = false;
        continue;
      }
      if (quote) {
        current += char;
        if (char === '\\') escaped = true;
        else if (char === quote) quote = '';
        continue;
      }
      if (char === '"' || char === "'") {
        quote = char;
        current += char;
        continue;
      }
      if (char === '(' || char === '[' || char === '{') depth += 1;
      if (char === ')' || char === ']' || char === '}') depth = Math.max(0, depth - 1);
      if (depth === 0 && text.startsWith(delimiter, i)) {
        parts.push(current.trim());
        current = '';
        i += delimiter.length - 1;
        continue;
      }
      current += char;
    }
    parts.push(current.trim());
    return parts.filter(Boolean);
  }

  function decodeQuoted(value) {
    const quote = value[0];
    const body = value.slice(1, -1);
    let output = '';
    let escaped = false;
    for (const char of body) {
      if (escaped) {
        output += ({n: '\n', r: '\r', t: '\t'}[char] ?? char);
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else {
        output += char;
      }
    }
    if (escaped) output += '\\';
    return output;
  }

  function resolveArgument(raw, element, event) {
    const value = raw.trim();
    if (!value) return undefined;
    if ((value[0] === "'" && value.at(-1) === "'") || (value[0] === '"' && value.at(-1) === '"')) {
      return decodeQuoted(value);
    }
    if (/^-?(?:\d+\.?\d*|\.\d+)$/.test(value)) return Number(value);
    if (value === 'true') return true;
    if (value === 'false') return false;
    if (value === 'null') return null;
    if (value === 'event') return event;
    if (value === 'this') return element;
    if (value === 'this.value') return element.value;
    if (value === 'this.checked') return Boolean(element.checked);
    const dataset = value.match(/^this\.dataset\.([A-Za-z0-9_]+)$/);
    if (dataset) return element.dataset?.[dataset[1]];
    throw new Error(`unsupported CSP action argument: ${value}`);
  }

  function invokeCall(source, element, event) {
    const match = source.trim().match(/^(?:window\.)?([A-Za-z_$][\w$]*)(\?\.)?\((.*)\)$/s);
    if (!match) throw new Error(`unsupported CSP action: ${source}`);
    const [, name, optional, argsText] = match;
    if (!ALLOWED_ACTIONS.has(name)) throw new Error(`blocked CSP action: ${name}`);
    const fn = window[name];
    if (typeof fn !== 'function') {
      if (optional) return undefined;
      throw new Error(`missing CSP action: ${name}`);
    }
    const args = argsText.trim()
      ? splitTopLevel(argsText, ',').map(arg => resolveArgument(arg, element, event))
      : [];
    return fn(...args);
  }

  function runProgram(program, element, event) {
    let source = String(program || '').trim();
    if (!source) return undefined;

    const enter = source.match(/^if\(event\.key===['"]Enter['"]\)(.+)$/s);
    if (enter) {
      if (event.key !== 'Enter') return undefined;
      source = enter[1].trim();
    }
    const targetSelf = source.match(/^if\(event\.target===this\)(.+)$/s);
    if (targetSelf) {
      if (event.target !== element) return undefined;
      source = targetSelf[1].trim();
    }

    const hide = source.match(/^document\.getElementById\((['"])([^'"]+)\1\)\.classList\.add\((['"])hidden\3\)$/);
    if (hide) {
      document.getElementById(hide[2])?.classList.add('hidden');
      return undefined;
    }

    if (source === 'adminResultsPage=1;renderAdminTable()') {
      window.adminResultsPage = 1;
      return invokeCall('renderAdminTable()', element, event);
    }

    const fallbacks = splitTopLevel(source, '||');
    if (fallbacks.length > 1) {
      let result;
      for (const part of fallbacks) {
        result = runProgram(part, element, event);
        if (result) return result;
      }
      return result;
    }

    let result;
    for (const statement of splitTopLevel(source, ';')) {
      if (statement === 'event.preventDefault()') {
        event.preventDefault();
        continue;
      }
      if (statement === 'event.stopPropagation()') {
        event.stopPropagation();
        continue;
      }
      result = invokeCall(statement, element, event);
    }
    return result;
  }

  function reportFailure(error, program) {
    console.error('[system-csp-actions]', error, program);
  }

  for (const [eventName, attribute] of Object.entries(ATTRIBUTE_BY_EVENT)) {
    document.addEventListener(eventName, event => {
      const target = event.target instanceof Element ? event.target.closest(`[${attribute}]`) : null;
      if (!target) return;
      try {
        const result = runProgram(target.getAttribute(attribute), target, event);
        if (result && typeof result.catch === 'function') result.catch(error => reportFailure(error, target.getAttribute(attribute)));
      } catch (error) {
        reportFailure(error, target.getAttribute(attribute));
      }
    });
  }

  migrateTree(document.documentElement);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') migrateElement(record.target);
      for (const node of record.addedNodes || []) migrateTree(node);
    }
  }).observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: Object.keys(LEGACY_TO_DATA)
  });
})();
