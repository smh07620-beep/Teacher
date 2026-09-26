/* Teacher 7.0: role-aware workspace presentation.
 *
 * Server-side RBAC remains authoritative. This file only removes actions the
 * current account cannot use, keeps group-scoped teachers inside their own
 * management scope, and translates expired sessions into login guidance
 * instead of the obsolete ADMIN_KEY prompt.
 *
 * 7.0 presentation rule: users no longer enter one generic "admin" surface.
 * The same proven backend workspaces are presented as Teacher, Education, or
 * System workspaces according to canonical RBAC. professional_title and
 * responsibility_tags remain presentation metadata and never grant access.
 */
window.TeacherRBAC681Ready = (async function () {
  const ROLE_LABELS = {
    student:'學員', clinical_teacher:'臨床教師', group_leader:'組長', education_admin:'教學管理者',
    system_admin:'系統管理者', auditor:'稽核／唯讀', learner:'學員', teacher:'臨床教師', manager:'教學管理者'
  };
  const LEGACY_ROLE = {learner:'student', teacher:'clinical_teacher', manager:'education_admin'};
  const WORKSPACE_RULES = {
    'course-materials': ['course.manage','material.manage'],
    content: ['course.manage','material.manage'],
    assessment: ['question.manage','exam.manage'],
    questions: ['question.manage'],
    quiz: ['question.manage','exam.manage'],
    exams: ['exam.manage'],
    'exam-settings': ['exam.manage'],
    teacher: ['evaluation.submit','evaluation.review','teacher.assessment.sign','evaluation.finalize'],
    scoring: ['evaluation.review','result.group.read'],
    pgy: ['evaluation.submit','evaluation.review','teacher.assessment.sign','evaluation.finalize'],
    results: ['result.group.read'],
    compliance: ['training.compliance.read'],
    word: ['template.manage'],
    people: ['user.manage'],
    system: ['system.manage']
  };
  const EXTENSION_WORKSPACE_RULES = {
    audit: ['audit.read','audit.view'],
    maintenance: ['backup.manage','education.cross_group.manage'],
    worker: ['system.manage']
  };
  const NAV_RULES = {
    'admin-nav-course-materials': WORKSPACE_RULES['course-materials'],
    'admin-nav-assessment': WORKSPACE_RULES.assessment,
    'admin-nav-questions': WORKSPACE_RULES.questions,
    'admin-nav-exams': WORKSPACE_RULES.exams,
    'admin-nav-teacher': WORKSPACE_RULES.teacher,
    'admin-nav-results': WORKSPACE_RULES.results,
    'admin-nav-compliance': WORKSPACE_RULES.compliance,
    'admin-nav-word': WORKSPACE_RULES.word,
    'admin-nav-people': WORKSPACE_RULES.people,
    'admin-nav-system': WORKSPACE_RULES.system
  };

  const response = await fetch('/api/auth/profile', {cache: 'no-store'}).catch(() => null);
  const auth = response && response.ok ? await response.json().catch(() => ({})) : {};
  const user = auth.user || {};
  const rawRoles = Array.isArray(user.roles) && user.roles.length ? user.roles : [user.role || 'student'];
  const roles = new Set(rawRoles.map(role => LEGACY_ROLE[role] || role));
  const permissions = new Set(Array.isArray(user.permissions) ? user.permissions : []);
  const has = permission => permissions.has(permission);
  const hasAny = rules => (rules || []).some(has);
  const systemAdmin = roles.has('system_admin');
  const crossGroup = systemAdmin || roles.has('education_admin') || has('education.cross_group.manage');
  const scopedTeacher = !crossGroup && (roles.has('clinical_teacher') || roles.has('group_leader'));
  const workspaceAccess = [...Object.values(WORKSPACE_RULES), ...Object.values(EXTENSION_WORKSPACE_RULES)].some(hasAny);
  const canOpenWorkspace = name => hasAny(WORKSPACE_RULES[name] || EXTENSION_WORKSPACE_RULES[name] || []);
  const groupCatalog = typeof GROUPS !== 'undefined' ? GROUPS : (window.GROUPS || {});

  function workspaceSurface() {
    if (systemAdmin) {
      return {
        key: 'system',
        entryIcon: '⚙',
        entryLabel: '系統管理',
        heading: '系統管理工作區',
        summary: '教學、人員、平台設定與高風險維護集中於此。',
        teachingLabel: '教學管理',
        evaluationLabel: '評核與成績',
        platformLabel: '平台與系統'
      };
    }
    if (roles.has('education_admin') || has('education.cross_group.manage')) {
      return {
        key: 'education',
        entryIcon: '🎓',
        entryLabel: '教學管理',
        heading: '教學管理工作區',
        summary: '跨組管理課程、教材、評量與學習成效；系統基礎設施設定仍由系統管理者負責。',
        teachingLabel: '跨組教學內容',
        evaluationLabel: '跨組評核與成績',
        platformLabel: '教學平台工具'
      };
    }
    if (roles.has('group_leader')) {
      return {
        key: 'teacher',
        entryIcon: '👨‍🏫',
        entryLabel: '教師工作區',
        heading: '組別教學工作區',
        summary: '管理所屬組別的教材、題庫、考卷、評核與成績。',
        teachingLabel: '組內課程與評量',
        evaluationLabel: '學員評核與成績',
        platformLabel: '教學工具'
      };
    }
    if (roles.has('clinical_teacher')) {
      return {
        key: 'teacher',
        entryIcon: '👨‍🏫',
        entryLabel: '教師工作區',
        heading: '教師工作區',
        summary: '只顯示教學內容、題庫考卷與自己負責學員相關功能。',
        teachingLabel: '課程、教材與評量',
        evaluationLabel: '負責學員與成績',
        platformLabel: '教學工具'
      };
    }
    if (roles.has('auditor')) {
      return {
        key: 'audit',
        entryIcon: '🔎',
        entryLabel: '稽核檢視',
        heading: '稽核／唯讀工作區',
        summary: '僅檢視授權的稽核資料，不提供新增、修改、發布或刪除操作。',
        teachingLabel: '唯讀資料',
        evaluationLabel: '稽核資料',
        platformLabel: '稽核'
      };
    }
    return {
      key: 'learner',
      entryIcon: '📚',
      entryLabel: '學習中心',
      heading: '學習中心',
      summary: '教材、課程、考試、進度與個人成績。',
      teachingLabel: '學習內容',
      evaluationLabel: '學習進度',
      platformLabel: '個人學習'
    };
  }
  const surface = workspaceSurface();

  window.TeacherRBAC681 = {
    user, roles, permissions, systemAdmin, crossGroup, scopedTeacher, workspaceAccess, surface,
    hasPermission: has,
    canOpenWorkspace
  };

  function roleSummary() {
    const labels = [...roles].map(role => ROLE_LABELS[role] || role);
    return labels.join('／') || '學員';
  }

  function setWorkspaceEntry() {
    const entries = [document.getElementById('workspace-entry'), ...document.querySelectorAll('.v575-manage-direct')].filter(Boolean);
    entries.forEach(entry => {
      if (!workspaceAccess) {
        entry.classList.add('hidden');
        entry.setAttribute('aria-hidden', 'true');
        entry.disabled = true;
        return;
      }
      entry.classList.remove('hidden');
      entry.removeAttribute('aria-hidden');
      entry.disabled = false;
      if (entry.id === 'workspace-entry') {
        entry.innerHTML = `<span>${surface.entryIcon}</span>${surface.entryLabel}`;
      } else {
        entry.textContent = `${surface.entryIcon} ${surface.entryLabel}`;
      }
      entry.dataset.workspaceSurface = surface.key;
      entry.title = surface.summary;
    });
  }

  function renderAccessBadge() {
    const entry = document.getElementById('workspace-entry');
    if (!entry || document.getElementById('rbac-profile-badge')) return;
    const badge = document.createElement('span');
    badge.id = 'rbac-profile-badge';
    const group = (groupCatalog[user.preferredGroup] || {}).name || user.preferredGroup || '';
    const title = user.professionalTitle || roleSummary();
    badge.className = 'text-[11px] font-bold px-2 py-1 rounded-full bg-slate-100 text-slate-700';
    badge.textContent = [group, title].filter(Boolean).join(' · ');
    entry.parentNode?.insertBefore(badge, entry);
  }

  function renderWorkspaceBanner() {
    const groups = document.querySelector('.v580-admin-groups');
    if (!groups) return;
    const modal = document.getElementById('admin-modal');
    if (modal) {
      modal.dataset.workspaceSurface = surface.key;
      modal.setAttribute('aria-label', surface.heading);
    }
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    if (title) title.textContent = `檢驗科教學平台｜${surface.heading}`;
    if (summary) summary.textContent = surface.summary;
    let banner = document.getElementById('rbac-workspace-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'rbac-workspace-banner';
      banner.className = 'rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 mb-4';
      groups.parentNode?.insertBefore(banner, groups);
    }
    const group = scopedTeacher ? ((groupCatalog[user.preferredGroup] || {}).name || user.preferredGroup || '所屬組別') : '';
    const scopeText = scopedTeacher && group ? `目前管理範圍：${group}` : (crossGroup ? '管理範圍：跨組教學' : '');
    if (window.isAdminWorkspacePage?.()) {
      banner.innerHTML = `
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-black text-slate-800">${surface.entryIcon} ${surface.entryLabel}</span>
            <span class="text-[11px] text-slate-400">從左側選擇工作項目</span>
          </div>
          ${scopeText ? `<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-600">${scopeText}</span>` : ''}
        </div>`;
      return;
    }
    banner.innerHTML = `
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div class="text-sm font-black text-slate-900">${surface.entryIcon} ${surface.heading}</div>
          <div class="text-xs text-slate-500 mt-1">${surface.summary}</div>
        </div>
        ${scopeText ? `<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-600">${scopeText}</span>` : ''}
      </div>`;
  }

  function relabelNavigationGroups() {
    document.querySelectorAll('.v580-admin-group').forEach(group => {
      const label = group.querySelector('.v580-admin-group-label');
      if (!label) return;
      if (group.querySelector('#admin-nav-course-materials,#admin-nav-assessment,#admin-nav-questions,#admin-nav-exams')) {
        label.textContent = surface.teachingLabel;
      } else if (group.querySelector('#admin-nav-teacher,#admin-nav-results,#admin-nav-compliance')) {
        label.textContent = surface.evaluationLabel;
      } else if (group.querySelector('#admin-nav-word,#admin-nav-people,#admin-nav-system')) {
        label.textContent = surface.platformLabel;
      }
    });
  }

  function applyNavVisibility() {
    Object.entries(NAV_RULES).forEach(([id, rules]) => {
      const button = document.getElementById(id);
      if (!button) return;
      const allowed = hasAny(rules);
      button.classList.toggle('hidden', !allowed);
      button.disabled = !allowed;
      button.setAttribute('aria-hidden', allowed ? 'false' : 'true');
    });
    document.querySelectorAll('.v580-admin-group').forEach(group => {
      const visible = [...group.querySelectorAll('.admin-nav-btn')].some(button => !button.classList.contains('hidden'));
      group.classList.toggle('hidden', !visible);
    });
    relabelNavigationGroups();
  }

  function scopedGroupLabel() {
    return (groupCatalog[user.preferredGroup] || {}).label ||
      (groupCatalog[user.preferredGroup] || {}).name || user.preferredGroup || '所屬組別';
  }

  function applyScopedSelect(select) {
    if (!select || !scopedTeacher || !user.preferredGroup) return;
    const value = String(user.preferredGroup);
    if (select.dataset.rbacScoped === '1' && select.options.length === 1 && select.value === value && select.disabled) return;
    select.innerHTML = `<option value="${value.replace(/"/g, '&quot;')}">${scopedGroupLabel()}</option>`;
    select.value = value;
    select.disabled = true;
    select.title = '此帳號只能管理自己所屬組別；跨組操作由教學管理者或系統管理者執行。';
    select.dataset.rbacScoped = '1';
  }

  function applyGroupScope() {
    ['admin-material-group','admin-quiz-group','wizard-group','admin-compliance-group'].forEach(id => applyScopedSelect(document.getElementById(id)));
  }

  function hideMatches(root, selector) {
    if (root.matches?.(selector)) root.classList.add('hidden');
    root.querySelectorAll?.(selector).forEach(el => el.classList.add('hidden'));
  }

  function guardSensitiveGeneratedActions(root = document) {
    if (!has('exam.publish')) {
      hideMatches(root, '[onclick*="PublishQuiz"],[onclick*="publishQuiz"],[onclick*="PublishExam"],[onclick*="publishExam"]');
    }
    if (!has('question.review')) {
      hideMatches(root, '[onclick*="ReviewQuiz"],[onclick*="reviewQuiz"],[onclick*="approveQuiz"],[onclick*="ApproveQuiz"]');
    }
    if (!has('user.manage')) {
      hideMatches(root, '[onclick*="AdminUser"],[onclick*="adminUser"],[onclick*="UserAccount"],[onclick*="userAccount"]');
    }
    if (!has('system.manage')) {
      hideMatches(root, '[onclick*="renderAdminSystemStatus"],[onclick*="createAdminAnnouncement"],[onclick*="toggleAdminAnnouncement"],[onclick*="deleteAdminAnnouncement"]');
    }
  }

  setWorkspaceEntry();
  if (!workspaceAccess) return window.TeacherRBAC681;
  renderAccessBadge();
  renderWorkspaceBanner();
  applyNavVisibility();
  applyGroupScope();
  guardSensitiveGeneratedActions();

  const adminShell = window.AdminWorkspaceShell;
  if (adminShell) {
    adminShell.addWorkspaceGuard(({requested, workspace}) => {
      if (!canOpenWorkspace(requested) && !canOpenWorkspace(workspace)) {
        const status = document.getElementById('admin-workspace-status');
        if (status) status.textContent = '此帳號沒有此工作區權限。';
        return false;
      }
      return true;
    });
    adminShell.addAfterWorkspace(() => {
      applyGroupScope();
      guardSensitiveGeneratedActions();
    });
    adminShell.addModalGuard(({show}) => !(show && !workspaceAccess));
    adminShell.addAfterModal(({show}) => {
      if (show) {
        renderWorkspaceBanner();
        applyNavVisibility();
        applyGroupScope();
        guardSensitiveGeneratedActions();
      }
    });
  }

  // Replace the final remaining ADMIN_KEY-era error text in the material list.
  // The compatibility header is intentionally meaningless; the server uses the
  // authenticated session and canonical RBAC/scope checks.
  if (typeof window.fetchAdminMaterials === 'function') {
    window.fetchAdminMaterials = async function (force = false) {
      const now = Date.now();
      if (!force && Array.isArray(adminMaterialsCache.data) && (now - adminMaterialsCache.at) < ADMIN_CACHE_MS) {
        return adminMaterialsCache.data;
      }
      const res = await fetch('/api/slides/admin', {credentials:'same-origin', cache: 'no-store'});
      const data = await res.json().catch(() => []);
      if (res.status === 401) {
        invalidateAdminMaterialsCache();
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = `/login?next=${next}`;
        throw new Error('登入已逾時，請重新登入。');
      }
      if (res.status === 403) throw new Error((data && data.error) || '沒有教材管理權限。');
      if (!res.ok) throw new Error((data && data.error) || '無法取得教材清單');
      const list = Array.isArray(data) ? data : [];
      adminMaterialsCache = {data: list, at: Date.now()};
      return list;
    };
  }

  const observer = new MutationObserver(records => {
    for (const record of records) {
      record.addedNodes.forEach(node => {
        if (!(node instanceof Element)) return;
        guardSensitiveGeneratedActions(node);
      });
    }
    applyGroupScope();
  });
  observer.observe(document.body, {childList: true, subtree: true});
  return window.TeacherRBAC681;
})().catch(error => {
  console.error('RBAC UI initialization failed', error);
  return window.TeacherRBAC681 || {};
});
