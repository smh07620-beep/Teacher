/* Teacher 6.9: role-aware workspace presentation.
 *
 * Server-side RBAC remains authoritative.  This file only removes actions the
 * current account cannot use, keeps group-scoped teachers inside their own
 * management scope, and translates expired sessions into login guidance
 * instead of the obsolete ADMIN_KEY prompt.
 */
(async function () {
  const ROLE_PERMISSIONS = {
    student: new Set(['material.read','course.view','exam.take','progress.self.read','result.self.read','student.view_self']),
    clinical_teacher: new Set([
      'material.read','course.view','course.manage','material.manage','question.manage','exam.manage',
      'result.group.read','document.export','evaluation.submit','evaluation.review','evaluation.sign',
      'teacher.assessment.sign','student.view_assigned'
    ]),
    group_leader: new Set([
      'material.read','course.view','course.manage','course.edit','material.manage','question.manage','question.review',
      'exam.manage','exam.publish','result.group.read','group.member.read','group.content.manage','group.result.read',
      'document.export','evaluation.submit','evaluation.review','teacher.assessment.sign','evaluation.countersign',
      'student.view_assigned','student.view_group'
    ]),
    education_admin: new Set([
      'material.read','course.view','course.manage','course.edit','material.manage','question.manage','question.review',
      'exam.manage','result.group.read','document.export','education.cross_group.manage','evaluation.finalize','student.view_all'
    ]),
    system_admin: new Set([
      'material.read','course.view','course.manage','course.edit','material.manage','question.manage','question.review',
      'exam.manage','exam.publish','result.group.read','document.export','education.cross_group.manage','group.member.read',
      'group.content.manage','group.result.read','user.manage','role.manage','audit.read','audit.view','system.manage',
      'storage.manage','backup.manage','template.manage'
    ]),
    auditor: new Set(['audit.read','audit.view'])
  };
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
    word: ['template.manage'],
    people: ['user.manage'],
    system: ['system.manage']
  };
  const NAV_RULES = {
    'admin-nav-course-materials': WORKSPACE_RULES['course-materials'],
    'admin-nav-assessment': WORKSPACE_RULES.assessment,
    'admin-nav-questions': WORKSPACE_RULES.questions,
    'admin-nav-exams': WORKSPACE_RULES.exams,
    'admin-nav-teacher': WORKSPACE_RULES.teacher,
    'admin-nav-results': WORKSPACE_RULES.results,
    'admin-nav-word': WORKSPACE_RULES.word,
    'admin-nav-people': WORKSPACE_RULES.people,
    'admin-nav-system': WORKSPACE_RULES.system
  };

  const response = await fetch('/api/auth/profile', {cache: 'no-store'}).catch(() => null);
  const auth = response && response.ok ? await response.json().catch(() => ({})) : {};
  const user = auth.user || {};
  const rawRoles = Array.isArray(user.roles) && user.roles.length ? user.roles : [user.role || 'student'];
  const roles = new Set(rawRoles.map(role => LEGACY_ROLE[role] || role));
  const permissions = new Set();
  roles.forEach(role => (ROLE_PERMISSIONS[role] || new Set()).forEach(permission => permissions.add(permission)));
  const has = permission => permissions.has(permission);
  const hasAny = rules => (rules || []).some(has);
  const systemAdmin = roles.has('system_admin');
  const crossGroup = systemAdmin || roles.has('education_admin') || has('education.cross_group.manage');
  const scopedTeacher = !crossGroup && (roles.has('clinical_teacher') || roles.has('group_leader'));
  const workspaceAccess = Object.values(WORKSPACE_RULES).some(hasAny);
  const canOpenWorkspace = name => hasAny(WORKSPACE_RULES[name] || []);

  window.TeacherRBAC681 = {
    user, roles, permissions, systemAdmin, crossGroup, scopedTeacher, workspaceAccess,
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
        entry.innerHTML = systemAdmin ? '<span>⚙</span>系統管理後台' : '<span>👨‍🏫</span>教師工作區';
      } else {
        entry.textContent = systemAdmin ? '⚙️ 系統管理' : '👨‍🏫 教師工作區';
      }
    });
  }

  function renderAccessBadge() {
    const entry = document.getElementById('workspace-entry');
    if (!entry || document.getElementById('rbac-profile-badge')) return;
    const badge = document.createElement('span');
    badge.id = 'rbac-profile-badge';
    const group = (window.GROUPS && window.GROUPS[user.preferredGroup] || {}).name || user.preferredGroup || '';
    const title = user.professionalTitle || roleSummary();
    badge.className = 'text-[11px] font-bold px-2 py-1 rounded-full bg-slate-100 text-slate-700';
    badge.textContent = [group, title].filter(Boolean).join(' · ');
    entry.parentNode?.insertBefore(badge, entry);
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
  }

  function scopedGroupLabel() {
    return (window.GROUPS && window.GROUPS[user.preferredGroup] || {}).label ||
      (window.GROUPS && window.GROUPS[user.preferredGroup] || {}).name || user.preferredGroup || '所屬組別';
  }

  function applyScopedSelect(select) {
    if (!select || !scopedTeacher || !user.preferredGroup) return;
    const value = String(user.preferredGroup);
    select.innerHTML = `<option value="${value.replace(/"/g, '&quot;')}">${scopedGroupLabel()}</option>`;
    select.value = value;
    select.disabled = true;
    select.title = '此帳號只能管理自己所屬組別；跨組操作由教學管理者或系統管理者執行。';
    select.dataset.rbacScoped = '1';
  }

  function applyGroupScope() {
    ['admin-material-group','admin-quiz-group','wizard-group'].forEach(id => applyScopedSelect(document.getElementById(id)));
  }

  function guardSensitiveGeneratedActions(root = document) {
    if (!has('exam.publish')) {
      root.querySelectorAll('[onclick*="PublishQuiz"],[onclick*="publishQuiz"],[onclick*="PublishExam"],[onclick*="publishExam"]').forEach(el => el.classList.add('hidden'));
    }
    if (!has('question.review')) {
      root.querySelectorAll('[onclick*="ReviewQuiz"],[onclick*="reviewQuiz"],[onclick*="approveQuiz"],[onclick*="ApproveQuiz"]').forEach(el => el.classList.add('hidden'));
    }
    if (!has('user.manage')) {
      root.querySelectorAll('[onclick*="AdminUser"],[onclick*="adminUser"],[onclick*="UserAccount"],[onclick*="userAccount"]').forEach(el => el.classList.add('hidden'));
    }
    if (!has('system.manage')) {
      root.querySelectorAll('[onclick*="renderAdminSystemStatus"],[onclick*="createAdminAnnouncement"],[onclick*="toggleAdminAnnouncement"],[onclick*="deleteAdminAnnouncement"]').forEach(el => el.classList.add('hidden'));
    }
  }

  setWorkspaceEntry();
  if (!workspaceAccess) return;
  renderAccessBadge();
  applyNavVisibility();
  applyGroupScope();
  guardSensitiveGeneratedActions();

  const legacyPopulateGroups = window.populateAdminGroupSelects;
  if (typeof legacyPopulateGroups === 'function') {
    window.populateAdminGroupSelects = function () {
      const result = legacyPopulateGroups.apply(this, arguments);
      applyGroupScope();
      return result;
    };
  }

  const legacySwitch = window.switchAdminWorkspace;
  if (typeof legacySwitch === 'function') {
    window.switchAdminWorkspace = async function (name, force) {
      if (!canOpenWorkspace(name)) {
        const status = document.getElementById('admin-workspace-status');
        if (status) status.textContent = '此帳號沒有此工作區權限。';
        return false;
      }
      const result = await legacySwitch(name, force);
      applyGroupScope();
      guardSensitiveGeneratedActions();
      return result;
    };
  }

  const legacyToggle = window.toggleAdminModal;
  if (typeof legacyToggle === 'function') {
    window.toggleAdminModal = async function (show) {
      if (show && !workspaceAccess) return false;
      const result = await legacyToggle(show);
      if (show) {
        applyNavVisibility();
        applyGroupScope();
        guardSensitiveGeneratedActions();
      }
      return result;
    };
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
      const res = await fetch('/api/slides/admin', {headers: {'X-Admin-Key': 'rbac-session'}, cache: 'no-store'});
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
})();
