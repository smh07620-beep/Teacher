/* Shared material upload transport.
 *
 * This is deliberately presentation- and credential-agnostic.  Callers may
 * supply legacy headers while session-based callers simply use same-origin
 * cookies.  Both paths use the one /api/material-jobs/upload background queue.
 */
(function(){
  'use strict';

  function asError(xhr, fallback){
    let body={};
    try{body=JSON.parse(xhr.responseText||'{}');}catch(_e){}
    return new Error(body.error||fallback||`HTTP ${xhr.status}`);
  }

  function enqueue(formData, options={}){
    const fileName=options.fileName||formData.get('file')?.name||'教材';
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();
      xhr.open('POST','/api/material-jobs/upload',true);
      xhr.withCredentials=true;
      xhr.timeout=options.timeout||20*60*1000;
      Object.entries(options.headers||{}).forEach(([name,value])=>{
        if(value) xhr.setRequestHeader(name,value);
      });
      xhr.upload.onprogress=event=>{
        if(event.lengthComputable) options.onProgress?.({loaded:event.loaded,total:event.total,percent:Math.round(event.loaded/event.total*100),fileName});
      };
      xhr.onload=()=>{
        if(xhr.status===401){options.onUnauthorized?.();reject(new Error('登入已逾時，請重新登入。'));return;}
        if(xhr.status===403){reject(asError(xhr,'此帳號沒有這項操作權限。'));return;}
        if(xhr.status>=200&&xhr.status<300){
          try{resolve(JSON.parse(xhr.responseText||'{}'));}catch(_e){resolve({});}
          return;
        }
        reject(asError(xhr));
      };
      xhr.onerror=()=>reject(new Error(`${fileName} 網路上傳失敗`));
      xhr.ontimeout=()=>reject(new Error(`${fileName} 傳送到伺服器逾時`));
      xhr.send(formData);
    });
  }

  window.MaterialUploadClient={enqueue};
})();
