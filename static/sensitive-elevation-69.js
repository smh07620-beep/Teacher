/* Teacher 6.9: elevation only for sensitive administration.
 *
 * Normal teacher requests stay session-RBAC only.  This bridge watches for the
 * server's 428 elevationRequired contract, asks for the break-glass credential
 * once, and retries the original same-origin request.  Legacy fake
 * X-Admin-Key: rbac-session headers are stripped before they reach the server.
 */
(function(){
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  let elevationFlight = null;

  function sameOrigin(input){
    try{
      const raw = typeof input === 'string' ? input : input?.url;
      return new URL(raw || '', location.href).origin === location.origin;
    }catch(_error){
      return false;
    }
  }

  function normalizeOptions(input, init={}){
    const options = {...init};
    if(!sameOrigin(input)) return options;
    const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
    if(headers.get('X-Admin-Key') === 'rbac-session') headers.delete('X-Admin-Key');
    options.headers = headers;
    if(options.credentials == null) options.credentials = 'same-origin';
    return options;
  }

  async function elevationStatus(){
    const response = await nativeFetch('/api/admin/elevation', {
      credentials:'same-origin',
      cache:'no-store'
    });
    if(!response.ok) return {elevated:false};
    return response.json().catch(()=>({elevated:false}));
  }

  async function ensureElevation(){
    if(elevationFlight) return elevationFlight;
    elevationFlight = (async()=>{
      const current = await elevationStatus();
      if(current.elevated) return true;

      const password = window.prompt('此操作會變更帳號、儲存、備份或系統資料。請輸入系統管理驗證碼（驗證後 15 分鐘內有效）：');
      if(password === null || password === '') return false;

      const response = await nativeFetch('/api/admin/elevation', {
        method:'POST',
        credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({password})
      });
      const data = await response.json().catch(()=>({}));
      if(response.status === 401 && data.loginRequired){
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = `/login?next=${next}`;
        return false;
      }
      if(!response.ok){
        window.alert(data.error || '敏感操作驗證失敗。');
        return false;
      }
      return true;
    })();
    try{
      return await elevationFlight;
    }finally{
      elevationFlight = null;
    }
  }

  window.ensureSensitiveElevation69 = ensureElevation;

  window.fetch = async function(input, init={}){
    const options = normalizeOptions(input, init);
    const response = await nativeFetch(input, options);
    if(!sameOrigin(input) || response.status !== 428) return response;

    const contract = await response.clone().json().catch(()=>({}));
    if(!contract.elevationRequired) return response;
    if(typeof input === 'string' && input.startsWith('/api/admin/elevation')) return response;

    const ok = await ensureElevation();
    if(!ok) return response;

    // Legacy callers use URL + plain init objects, so their bodies remain
    // reusable.  If a future caller supplies a Request object with a consumed
    // body, fail safely rather than guessing how to replay it.
    if(input instanceof Request && input.bodyUsed) return response;
    return nativeFetch(input, normalizeOptions(input, init));
  };
})();
