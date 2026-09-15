/* One modal/promise for every concurrent privileged action.  No secret is persisted. */
let inFlight = null;
export function requestAdminElevation(openModal) {
  if (inFlight) return inFlight;
  inFlight = Promise.resolve().then(openModal).then(async password => {
    if (!password) throw new Error('cancelled');
    const response = await fetch('/api/admin/elevation', { method: 'POST', headers: {'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify({password}) });
    if (!response.ok) throw new Error('驗證失敗');
    return response.json();
  }).finally(() => { inFlight = null; });
  return inFlight;
}

export function onceWhilePending(action) {
  let pending = false;
  return async (...args) => { if (pending) return; pending = true; try { return await action(...args); } finally { pending = false; } };
}
