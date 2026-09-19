/* Shared material upload transport.
 *
 * Production uploads go Browser -> R2 -> material_jobs.  Multipart uploads
 * persist only an opaque upload/session identity locally.  Server/R2 list-parts
 * state is authoritative; browser-local ETags are never used for resume.
 */
(function(){
  'use strict';

  const PART_MB=16;
  const CONCURRENCY=3;
  const MAX_RETRIES=3;
  const FINGERPRINT_STRATEGY='sha256-part-tree-v1';
  const RESUME_STORAGE_KEY='teacher.materialUpload.multipart.v1';

  function apiHeaders(extra={}){
    const headers=new Headers(extra||{});
    headers.delete('X-Admin-Key');
    return headers;
  }

  async function bodyError(response,fallback){
    const body=await response.clone().json().catch(()=>({}));
    const error=new Error(body.error||fallback||`HTTP ${response.status}`);
    error.status=response.status;
    error.body=body;
    return error;
  }

  async function sha256Blob(blob){
    const buffer=await blob.arrayBuffer();
    const digest=await crypto.subtle.digest('SHA-256',buffer);
    return [...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
  }

  async function sha256Text(value){
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(String(value)));
    return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
  }

  async function fingerprintFile(file,fileName){
    const partSize=PART_MB*1024*1024;
    const partHashes=[];
    for(let start=0;start<file.size;start+=partSize){
      partHashes.push(await sha256Blob(file.slice(start,Math.min(file.size,start+partSize))));
    }
    const manifest=[FINGERPRINT_STRATEGY,String(file.size),String(partSize),...partHashes].join('\n');
    const fingerprint=await sha256Text(manifest);
    return {
      filename:fileName,
      size:file.size,
      lastModified:Number(file.lastModified||0),
      fingerprint,
      fingerprintStrategy:FINGERPRINT_STRATEGY,
      fingerprintPartSize:partSize,
      partHashes
    };
  }

  function readResumeStore(){
    try{
      const parsed=JSON.parse(localStorage.getItem(RESUME_STORAGE_KEY)||'{}');
      return parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?parsed:{};
    }catch(_e){return {};}
  }

  function writeResumeStore(store){
    try{
      const keys=Object.keys(store||{});
      if(!keys.length) localStorage.removeItem(RESUME_STORAGE_KEY);
      else localStorage.setItem(RESUME_STORAGE_KEY,JSON.stringify(store));
    }catch(_e){}
  }

  function clearResume(uploadId){
    if(!uploadId)return;
    const store=readResumeStore();
    if(Object.prototype.hasOwnProperty.call(store,uploadId)){
      delete store[uploadId];
      writeResumeStore(store);
    }
  }

  function saveResume(session,identity){
    if(!session?.uploadId||session.mode!=='multipart'||!session.resumable)return;
    const store=readResumeStore();
    store[session.uploadId]={
      uploadId:session.uploadId,
      jobId:session.jobId||'',
      materialId:session.materialId||'',
      filename:identity.filename,
      size:identity.size,
      lastModified:identity.lastModified,
      fingerprint:identity.fingerprint,
      fingerprintStrategy:identity.fingerprintStrategy,
      fingerprintPartSize:identity.fingerprintPartSize,
      savedAt:Date.now()
    };
    writeResumeStore(store);
  }

  function findResume(identity){
    const store=readResumeStore();
    let changed=false;
    let match=null;
    for(const [uploadId,item] of Object.entries(store)){
      if(!item||item.filename!==identity.filename)continue;
      if(Number(item.size)===Number(identity.size)&&Number(item.lastModified)===Number(identity.lastModified)&&item.fingerprint===identity.fingerprint&&item.fingerprintStrategy===identity.fingerprintStrategy&&Number(item.fingerprintPartSize)===Number(identity.fingerprintPartSize)){
        if(!match)match=item;
      }else{
        delete store[uploadId];
        changed=true;
      }
    }
    if(changed)writeResumeStore(store);
    return match;
  }

  function resumeIdentityBody(identity){
    return {
      filename:identity.filename,
      size:identity.size,
      lastModified:identity.lastModified,
      fingerprint:identity.fingerprint,
      fingerprintStrategy:identity.fingerprintStrategy,
      fingerprintPartSize:identity.fingerprintPartSize
    };
  }

  function formMetadata(formData){
    const metadata={};
    for(const [name,value] of formData.entries()){
      if(name==='file' || value instanceof File || value instanceof Blob) continue;
      metadata[name]=String(value??'');
    }
    return metadata;
  }

  async function retryPut(url,chunk,headers){
    let lastError=null;
    for(let attempt=0;attempt<MAX_RETRIES;attempt++){
      try{
        const response=await fetch(url,{method:'PUT',body:chunk,headers:headers||undefined});
        if(response.ok)return response;
        lastError=new Error(`R2 upload failed (${response.status})`);
      }catch(error){lastError=error;}
      if(attempt+1<MAX_RETRIES){
        await new Promise(resolve=>setTimeout(resolve,Math.min(4000,300*(2**attempt))));
      }
    }
    throw lastError||new Error('R2 upload failed');
  }

  async function completeUpload(session,completed,options){
    const complete=await fetch(`/api/material-upload/${encodeURIComponent(session.uploadId)}/complete`,{
      method:'POST',
      credentials:'same-origin',
      headers:apiHeaders({'Content-Type':'application/json',...(options.headers||{})}),
      body:JSON.stringify({parts:completed})
    });
    if(!complete.ok)throw await bodyError(complete,'R2 直傳完成驗證失敗');
    return await complete.json();
  }

  async function abortUpload(uploadId,options={}){
    try{
      const response=await fetch(`/api/material-upload/${encodeURIComponent(uploadId)}/abort`,{
        method:'POST',
        credentials:'same-origin',
        headers:apiHeaders(options.headers||{})
      });
      if(!response.ok)throw await bodyError(response,'無法中止 R2 直傳工作');
      return await response.json();
    }finally{
      clearResume(uploadId);
    }
  }

  async function uploadSingle(file,fileName,session,options){
    const maxBytes=Number(session.singlePutMaxBytes||0);
    if(!Number.isFinite(maxBytes)||maxBytes<=0||file.size>maxBytes)throw new Error('伺服器回傳的單檔直傳限制不合法');
    const url=String(session.url||session.parts?.[0]?.url||'');
    if(!url)throw new Error('R2 單檔直傳沒有可用網址');
    const [sha256,response]=await Promise.all([sha256Blob(file),retryPut(url,file,session.headers||undefined)]);
    const etag=response.headers.get('etag');
    if(!etag)throw new Error('R2 未回傳 ETag，請檢查 bucket CORS ExposeHeaders');
    options.onProgress?.({loaded:file.size,total:file.size,percent:100,fileName});
    return completeUpload(session,[{partNumber:1,etag,sha256}],options);
  }

  function partBytes(file,partNumber,partSize){
    const start=(Number(partNumber)-1)*Number(partSize);
    const end=Math.min(file.size,start+Number(partSize));
    return Math.max(0,end-start);
  }

  async function uploadMultipart(file,fileName,session,options,identity){
    const partSize=Number(session.partSize||0);
    const expectedParts=Number(session.expectedParts||identity.partHashes.length||0);
    if(partSize!==Number(identity.fingerprintPartSize)||expectedParts!==identity.partHashes.length){
      clearResume(session.uploadId);
      throw new Error('續傳分段設定與本機檔案指紋不符');
    }
    const parts=Array.isArray(session.parts)?session.parts:[];
    const uploadedSet=new Set((session.uploadedParts||[]).map(part=>Number(part.partNumber)).filter(Number.isFinite));
    let uploaded=[...uploadedSet].reduce((total,number)=>total+partBytes(file,number,partSize),0);
    if(uploaded){
      options.onProgress?.({loaded:Math.min(uploaded,file.size),total:file.size,percent:Math.min(100,Math.round(uploaded/file.size*100)),fileName});
    }
    let cursor=0;
    const worker=async()=>{
      while(true){
        const index=cursor++;
        if(index>=parts.length)return;
        const part=parts[index];
        const number=Number(part.partNumber);
        if(!Number.isFinite(number)||number<1||number>expectedParts||uploadedSet.has(number))continue;
        const start=(number-1)*partSize;
        const end=Math.min(file.size,start+partSize);
        const chunk=file.slice(start,end);
        const response=await retryPut(part.url,chunk,part.headers||undefined);
        if(!response.headers.get('etag'))throw new Error('R2 未回傳 ETag，請檢查 bucket CORS ExposeHeaders');
        uploadedSet.add(number);
        uploaded+=chunk.size;
        options.onProgress?.({loaded:Math.min(uploaded,file.size),total:file.size,percent:Math.min(100,Math.round(uploaded/file.size*100)),fileName});
      }
    };
    await Promise.all(Array.from({length:Math.min(CONCURRENCY,Math.max(1,parts.length))},()=>worker()));
    const completed=identity.partHashes.map((sha256,index)=>({partNumber:index+1,sha256}));
    const result=await completeUpload(session,completed,options);
    clearResume(session.uploadId);
    return result;
  }

  async function resumeMultipart(saved,identity,options){
    const response=await fetch(`/api/material-upload/${encodeURIComponent(saved.uploadId)}/resume`,{
      method:'POST',
      credentials:'same-origin',
      headers:apiHeaders({'Content-Type':'application/json',...(options.headers||{})}),
      body:JSON.stringify(resumeIdentityBody(identity))
    });
    if(!response.ok){
      const error=await bodyError(response,'無法恢復 R2 multipart 上傳');
      if([404,409].includes(error.status)&&['file_identity_mismatch','upload_missing','upload_terminal','resume_not_supported'].includes(error.body?.code)){
        clearResume(saved.uploadId);
        return null;
      }
      throw error;
    }
    const session=await response.json();
    if(session.status==='completed'){
      clearResume(saved.uploadId);
      return {completed:true,result:{accepted:true,jobId:session.jobId,status:'queued',resumedComplete:true}};
    }
    saveResume({...session,resumable:true},identity);
    return {completed:false,session};
  }

  async function createDirectSession(formData,file,fileName,identity,options){
    const init=await fetch('/api/material-upload/init',{
      method:'POST',
      credentials:'same-origin',
      headers:apiHeaders({'Content-Type':'application/json',...(options.headers||{})}),
      body:JSON.stringify({
        ...formMetadata(formData),
        filename:fileName,
        size:file.size,
        hashStrategy:'sha256-parts-v1',
        partSizeMb:PART_MB,
        ...resumeIdentityBody(identity)
      })
    });
    if(!init.ok){
      const error=await bodyError(init,'無法建立 R2 直傳工作');
      error.directUnavailable=error.body?.available===false;
      throw error;
    }
    return await init.json();
  }

  async function directUpload(formData,options={}){
    const file=formData.get('file');
    if(!(file instanceof Blob)||!file.size)throw new Error('未收到教材檔案');
    if(!window.crypto?.subtle)throw new Error('此瀏覽器不支援安全分段上傳');
    const fileName=options.fileName||file.name||'教材';
    const identity=await fingerprintFile(file,fileName);

    const saved=findResume(identity);
    if(saved){
      const resumed=await resumeMultipart(saved,identity,options);
      if(resumed?.completed)return resumed.result;
      if(resumed?.session)return uploadMultipart(file,fileName,resumed.session,options,identity);
    }

    const session=await createDirectSession(formData,file,fileName,identity,options);
    if(session.mode==='single'){
      try{return await uploadSingle(file,fileName,session,options);}
      catch(error){await abortUpload(session.uploadId,options).catch(()=>null);throw error;}
    }
    if(session.mode==='multipart'||!session.mode){
      if(!session.resumable)throw new Error('伺服器未啟用安全 multipart 續傳');
      saveResume(session,identity);
      return uploadMultipart(file,fileName,session,options,identity);
    }
    await abortUpload(session.uploadId,options).catch(()=>null);
    throw new Error(`不支援的 R2 直傳模式：${session.mode}`);
  }

  function asError(xhr,fallback){
    let body={};
    try{body=JSON.parse(xhr.responseText||'{}');}catch(_e){}
    return new Error(body.error||fallback||`HTTP ${xhr.status}`);
  }

  function webByteUpload(formData,options={}){
    const fileName=options.fileName||formData.get('file')?.name||'教材';
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();
      xhr.open('POST','/api/material-jobs/upload',true);
      xhr.withCredentials=true;
      xhr.timeout=options.timeout||20*60*1000;
      Object.entries(options.headers||{}).forEach(([name,value])=>{
        if(String(name).toLowerCase()==='x-admin-key')return;
        if(value)xhr.setRequestHeader(name,value);
      });
      xhr.upload.onprogress=event=>{
        if(event.lengthComputable)options.onProgress?.({loaded:event.loaded,total:event.total,percent:Math.round(event.loaded/event.total*100),fileName});
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

  async function enqueue(formData,options={}){
    try{return await directUpload(formData,options);}
    catch(error){
      if(error?.status===401){options.onUnauthorized?.();throw new Error('登入已逾時，請重新登入。');}
      if(error?.status===403)throw error;
      const allowFallback=options.allowLegacyWebFallback!==false;
      const mayFallback=allowFallback&&(error?.directUnavailable||!window.crypto?.subtle);
      if(!mayFallback)throw error;
      return webByteUpload(formData,options);
    }
  }

  window.MaterialUploadClient={enqueue,directUpload,abort:abortUpload,sha256Blob,fingerprintFile};
})();
