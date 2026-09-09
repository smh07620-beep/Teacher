/* V5.9.0 · 全站共用核心：路由、組別、API 與使用者身分 */
(function (global) {
  const groups = Object.freeze({
    grpBio: Object.freeze({ label: '1 生化組', name: '生化組', icon: '🧫' }),
    grpMicro: Object.freeze({ label: '2 鏡檢組', name: '鏡檢組', icon: '🔬' }),
    grpSero: Object.freeze({ label: '3 血清組', name: '血清組', icon: '🧪' }),
    grpBB: Object.freeze({ label: '4 血庫組', name: '血庫組', icon: '🩸' }),
    grpBact: Object.freeze({ label: '5 細菌組', name: '細菌組', icon: '🦠' }),
    grpHema: Object.freeze({ label: '6 血液組', name: '血液組', icon: '🧬' }),
    grpNew: Object.freeze({ label: '新進醫檢師專區', name: '新進醫檢師專區', icon: '🧑‍🔬', pgyOnly: true }),
    grpPgyDocs: Object.freeze({ label: 'PGY專用資料區', name: 'PGY專用資料放置區', icon: '📘', pgyOnly: true })
  });

  const memoryKeys = Object.freeze({ learnerName: 'smh_learner_name', learnerEmpId: 'smh_learner_empid' });
  const readMemory = key => { try { return localStorage.getItem(key) || ''; } catch (_) { return ''; } };
  const writeMemory = (key, value) => { try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch (_) {} };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', ...options });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : await response.text();
    if (!response.ok) {
      const error = new Error((data && data.error) || `請求失敗（${response.status}）`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function getCurrentUser() {
    const state = await api('/api/auth/me', { cache: 'no-store' });
    const user = state.authenticated ? state.user : null;
    if (user) {
      writeMemory(memoryKeys.learnerName, user.name || '');
      writeMemory(memoryKeys.learnerEmpId, user.empId || '');
    }
    return user;
  }

  function learningUrl({ area = 'internal', group = 'grpBio', module = 'materials', ...extra } = {}) {
    const params = new URLSearchParams({ area, group, module });
    Object.entries(extra).forEach(([key, value]) => value !== undefined && value !== null && params.set(key, String(value)));
    return `/system?${params.toString()}`;
  }

  global.AppCore = Object.freeze({ api, escapeHtml, getCurrentUser, groups, learningUrl, memoryKeys, readMemory, writeMemory });
})(window);
