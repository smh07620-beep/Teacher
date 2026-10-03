/* Teacher 10/14: keep the visible Course Wizard group selector populated and scope-safe. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));

  function preferredGroup() {
    const user = R.user || {};
    return String(user.preferredGroup || user.preferred_group || '').trim();
  }

  function rowsFor(area) {
    const catalog = typeof GROUPS !== 'undefined' ? GROUPS : (window.GROUPS || {});
    let rows = Object.entries(catalog)
      .filter(([, group]) => area === 'pgy' || !group?.pgyOnly)
      .map(([value, group]) => ({
        value: String(value),
        label: String(group?.label || group?.name || value),
      }));
    const preferred = preferredGroup();
    if (R.scopedTeacher && preferred) rows = rows.filter(row => row.value === preferred);
    return rows;
  }

  function selectedValue(rows, current) {
    const candidates = [String(current || ''), preferredGroup(), 'grpBio'].filter(Boolean);
    return candidates.find(value => rows.some(row => row.value === value)) || rows[0]?.value || '';
  }

  function replaceOptions(select, rows, selected) {
    if (!select) return;
    const signature = rows.map(row => `${row.value}:${row.label}`).join('|');
    if (select.dataset.teacher1014GroupSignature !== signature) {
      select.replaceChildren(...rows.map(row => {
        const option = document.createElement('option');
        option.value = row.value;
        option.textContent = row.label;
        return option;
      }));
      select.dataset.teacher1014GroupSignature = signature;
    }
    if (selected && [...select.options].some(option => option.value === selected)) select.value = selected;
  }

  function syncVisibleGroup() {
    const area = document.getElementById('cw681-area')?.value || document.getElementById('wizard-area')?.value || 'pgy';
    const visible = document.getElementById('cw681-group');
    const hidden = document.getElementById('wizard-group');
    if (!visible && !hidden) return false;
    const rows = rowsFor(area);
    if (!rows.length) return false;
    const selected = selectedValue(rows, visible?.value || hidden?.value);
    replaceOptions(hidden, rows, selected);
    replaceOptions(visible, rows, selected);
    return true;
  }

  function bindVisibleControls() {
    const area = document.getElementById('cw681-area');
    const group = document.getElementById('cw681-group');
    if (area && area.dataset.teacher1014GroupBound !== '1') {
      area.dataset.teacher1014GroupBound = '1';
      area.addEventListener('change', () => {
        const hiddenArea = document.getElementById('wizard-area');
        if (hiddenArea) hiddenArea.value = area.value;
        const rows = rowsFor(area.value || 'pgy');
        const selected = selectedValue(rows, preferredGroup());
        replaceOptions(document.getElementById('wizard-group'), rows, selected);
        replaceOptions(document.getElementById('cw681-group'), rows, selected);
      });
    }
    if (group && group.dataset.teacher1014GroupBound !== '1') {
      group.dataset.teacher1014GroupBound = '1';
      group.addEventListener('change', () => {
        const hidden = document.getElementById('wizard-group');
        if (hidden) hidden.value = group.value;
      });
    }
  }

  function sync() {
    const ready = syncVisibleGroup();
    bindVisibleControls();
    return ready;
  }

  let observer = null;

  function nodeContainsWizard(node) {
    if (!(node instanceof Element)) return false;
    return node.id === 'course-wizard-681' || Boolean(node.querySelector?.('#course-wizard-681'));
  }

  function observeWizard() {
    observer?.disconnect();
    const root = document.getElementById('course-wizard-681');
    if (root) {
      observer = new MutationObserver(() => sync());
      observer.observe(root, {childList:true, subtree:true});
      return;
    }
    observer = new MutationObserver(records => {
      if (!records.some(record => [...(record.addedNodes || [])].some(nodeContainsWizard))) return;
      sync();
      observeWizard();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  sync();
  observeWizard();
  window.CourseWizardGroupFix1014 = Object.freeze({ sync });
})();
