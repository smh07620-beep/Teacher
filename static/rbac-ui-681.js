/* Teacher 6.8.1: display modes complement, never replace, server-side RBAC. */
(async function () {
  const response = await fetch('/api/auth/profile', {cache: 'no-store'}).catch(() => null);
  const auth = response && response.ok ? await response.json() : {};
  const user = auth.user || {};
  const roles = new Set(Array.isArray(user.roles) ? user.roles : [user.role || 'student']);
  const systemAdmin = roles.has('system_admin');
  const teacher = systemAdmin || ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role));
  window.TeacherRBAC681 = {user, roles, systemAdmin, teacher};
  const entry = document.getElementById('workspace-entry');
  if (!teacher) { entry?.remove(); return; }
  if (entry) entry.innerHTML = systemAdmin ? '<span>⚙</span>系統管理後台' : '<span>👨‍🏫</span>教師工作區';
  const profile = document.createElement('span');
  const group = (window.GROUPS && window.GROUPS[user.preferredGroup] || {}).name || user.preferredGroup || '';
  const title = user.professionalTitle || ({student:'學員', clinical_teacher:'臨床教師', group_leader:'組長', education_admin:'教學管理者', system_admin:'系統管理員', auditor:'稽核／唯讀'})[user.role] || '';
  profile.className = 'text-[11px] font-bold px-2 py-1 rounded-full bg-slate-100 text-slate-700';
  profile.textContent = [group, title].filter(Boolean).join(' · ');
  entry?.parentNode?.insertBefore(profile, entry);
  if (!systemAdmin) ['word', 'people', 'system'].forEach(name => document.getElementById(`admin-nav-${name}`)?.remove());
  const legacy = window.switchAdminWorkspace;
  window.switchAdminWorkspace = async function (name, force) {
    if (!systemAdmin && ['word', 'people', 'system'].includes(name)) return;
    return legacy(name, force);
  };
  const renderSystemStatus = window.renderAdminSystemStatus;
  window.renderAdminSystemStatus = async function (force) {
    if (!systemAdmin) return;
    return renderSystemStatus(force);
  };
  // Non-system roles never call storage/Groq status endpoints, so a 403 is
  // not converted into a false "not configured" status.
})();
