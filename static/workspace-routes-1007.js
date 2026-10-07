/* Workspace route registry (single source of truth for back-office destinations).
 *
 * The back office has eleven internal "workspace" keys, but people only see
 * four product areas (docs/PRODUCT_INFORMATION_ARCHITECTURE_20261001.md).  This
 * file records that mapping once so that links, labels and headers never have to
 * hand-write workspace URLs or names again:
 *
 *   AppWorkspaceRoutes.url('assessment', {persona:'teacher', from:'incident'})
 *   AppWorkspaceRoutes.open('course-materials')
 *   AppWorkspaceRoutes.areaLabel('word')        // -> '教學'
 *
 * Presentation only: server-side RBAC stays authoritative.  The same table is
 * mirrored in teacher_app/common/workspace_routes.py (a test keeps them equal).
 */
(() => {
  'use strict';

  const AREAS = Object.freeze({
    learning: Object.freeze({label: '我的學習'}),
    teaching: Object.freeze({label: '教學'}),
    assessment: Object.freeze({label: '評量'}),
    system: Object.freeze({label: '系統管理'}),
  });

  const entry = (area, icon, label, title, summary) =>
    Object.freeze({area, icon, label, title, summary});

  const WORKSPACES = Object.freeze({
    'course-materials': entry('teaching', '📚', '教材與課程', '教材與課程 Workspace', '管理課程、教材、影音、圖譜與內容處理進度。'),
    word: entry('teaching', '📝', 'Word 範本', 'Word 範本 Workspace', '維護各組正式考核表範本與套版輸出。'),
    assessment: entry('assessment', '📝', '評量與追蹤', '評量與追蹤 Workspace', '管理考卷、題庫、AI 輔助出題、審核發布、待批改與學員追蹤。'),
    teacher: entry('assessment', '👩‍🏫', '教師評核', '教師評核 Workspace', '集中處理人工閱卷、問答評分與 PGY 教師評核。'),
    results: entry('assessment', '📊', '成績管理', '成績管理 Workspace', '查閱歷次成績、通過狀態、批改結果與考核分析。'),
    compliance: entry('assessment', '✅', '訓練合規', '訓練合規 Workspace', '依指派查看人員完訓、逾期、重訓、補強、考核與完訓證明狀態。'),
    people: entry('system', '👥', '人員管理', '人員管理 Workspace', '管理帳號、角色、範圍與教學存取權限。'),
    system: entry('system', '⚙️', '系統設定', '系統設定 Workspace', '檢查系統服務、儲存、安全設定與維運型系統公告。'),
    maintenance: entry('system', '🛡️', '備份維護', '備份維護 Workspace', '執行授權範圍內的備份、還原與維護工作。'),
    audit: entry('system', '🔎', '稽核紀錄', '稽核紀錄 Workspace', '唯讀檢視授權範圍內的系統與教學稽核紀錄。'),
    worker: entry('system', '⚙️', 'Worker', 'Worker Workspace', '檢查教材背景處理與工作執行狀態。'),
  });

  // Older names still arrive from bookmarks, notifications and legacy buttons.
  // ``pgy`` is meaningful to the router (it picks the PGY sub-section), so URLs
  // keep the requested name and only lookups are normalised.
  const ALIASES = Object.freeze({
    courses: 'course-materials',
    materials: 'course-materials',
    questions: 'assessment',
    exams: 'assessment',
    scoring: 'teacher',
    pgy: 'teacher',
  });

  const DEFAULT_WORKSPACE = 'course-materials';
  const PAGE_PATH = '/system';

  function normalize(name) {
    const key = String(name || '').trim();
    return Object.prototype.hasOwnProperty.call(ALIASES, key) ? ALIASES[key] : key;
  }

  function has(name) {
    return Object.prototype.hasOwnProperty.call(WORKSPACES, normalize(name));
  }

  function must(name) {
    const key = normalize(name);
    if (!Object.prototype.hasOwnProperty.call(WORKSPACES, key)) {
      throw new Error(`Unknown workspace: ${String(name)}`);
    }
    return key;
  }

  const get = name => WORKSPACES[must(name)];
  const areaOf = name => get(name).area;
  const areaLabel = name => AREAS[areaOf(name)].label;
  const isSystem = name => has(name) && areaOf(name) === 'system';
  const names = () => [...Object.keys(WORKSPACES), ...Object.keys(ALIASES)];
  const systemNames = () => Object.keys(WORKSPACES).filter(key => WORKSPACES[key].area === 'system');

  // Query order is kept identical to the links that used to be written by hand
  // (area, group, admin, workspace, persona, from, ...extra) so old bookmarks
  // and tests keep matching.
  function url(name, options = {}) {
    must(name);
    const query = [];
    const add = (key, value) => {
      if (value !== undefined && value !== null && value !== '') {
        query.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
      }
    };
    add('area', options.area);
    add('group', options.group);
    add('admin', '1');
    add('workspace', name);
    add('persona', options.persona || (isSystem(name) ? 'system' : ''));
    add('from', options.from);
    Object.entries(options.params || {}).forEach(([key, value]) => add(key, value));
    return `${PAGE_PATH}?${query.join('&')}`;
  }

  // Navigate to a workspace page / reveal it through the shell router.
  function open(name) {
    must(name);
    return typeof window.openAdminWorkspace === 'function'
      ? window.openAdminWorkspace(name)
      : Promise.resolve(true);
  }

  // Switch inside an already-open workspace shell.
  function show(name, force = false) {
    must(name);
    return typeof window.switchAdminWorkspace === 'function'
      ? window.switchAdminWorkspace(name, force)
      : Promise.resolve(true);
  }

  window.AppWorkspaceRoutes = Object.freeze({
    AREAS,
    WORKSPACES,
    ALIASES,
    DEFAULT_WORKSPACE,
    normalize,
    has,
    get,
    areaOf,
    areaLabel,
    isSystem,
    names,
    systemNames,
    url,
    open,
    show,
  });
})();
