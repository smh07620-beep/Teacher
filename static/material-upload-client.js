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
  const SHA256_INITIAL=new Uint32Array([
    0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
  ]);
  const SHA256_K=new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ]);

  function apiHeaders(extra={}){
    return new Headers(extra||{});
  }

  async function bodyError(response,fallback){
    const body=await response.clone().json().catch(()=>({}));
    const error=new Error(body.error||fallback||`HTTP ${response.status}`);
    error.status=response.status;
    error.body=body;
    return error;
  }

  function rotateRight(value,bits){
    return ((value>>>bits)|(value<<(32-bits)))>>>0;
  }

  class StreamingSha256{
    constructor(){
      this.state=new Uint32Array(SHA256_INITIAL);
      this.buffer=new Uint8Array(64);
      this.bufferLength=0;
      this.bytesHashed=0;
      this.words=new Uint32Array(64);
    }

    processBlock(data,offset=0){
      const w=this.words;
      for(let i=0;i<16;i++){
        const j=offset+i*4;
        w[i]=((data[j]<<24)|(data[j+1]<<16)|(data[j+2]<<8)|data[j+3])>>>0;
      }
      for(let i=16;i<64;i++){
        const x=w[i-15],y=w[i-2];
        const s0=(rotateRight(x,7)^rotateRight(x,18)^(x>>>3))>>>0;
        const s1=(rotateRight(y,17)^rotateRight(y,19)^(y>>>10))>>>0;
        w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
      }
      let a=this.state[0],b=this.state[1],c=this.state[2],d=this.state[3];
      let e=this.state[4],f=this.state[5],g=this.state[6],h=this.state[7];
      for(let i=0;i<64;i++){
        const s1=(rotateRight(e,6)^rotateRight(e,11)^rotateRight(e,25))>>>0;
        const ch=((e&f)^((~e)&g))>>>0;
        const t1=(h+s1+ch+SHA256_K[i]+w[i])>>>0;
        const s0=(rotateRight(a,2)^rotateRight(a,13)^rotateRight(a,22))>>>0;
        const maj=((a&b)^(a&c)^(b&c))>>>0;
        const t2=(s0+maj)>>>0;
        h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
      }
      this.state[0]=(this.state[0]+a)>>>0;this.state[1]=(this.state[1]+b)>>>0;
      this.state[2]=(this.state[2]+c)>>>0;this.state[3]=(this.state[3]+d)>>>0;
      this.state[4]=(this.state[4]+e)>>>0;this.state[5]=(this.state[5]+f)>>>0;
      this.state[6]=(this.state[6]+g)>>>0;this.state[7]=(this.state[7]+h)>>>0;
    }

    update(value){
      const data=value instanceof Uint8Array?value:new Uint8Array(value);
      this.bytesHashed+=data.byteLength;
      let offset=0;
      if(this.bufferLength){
        const take=Math.min(64-this.bufferLength,data.byteLength);
        this.buffer.set(data.subarray(0,take),this.bufferLength);
        this.bufferLength+=take;offset+=take;
        if(this.bufferLength===64){this.processBlock(this.buffer);this.bufferLength=0;}
      }
      while(offset+64<=data.byteLength){this.processBlock(data,offset);offset+=64;}
      if(offset<data.byteLength){
        this.buffer.set(data.subarray(offset),0);
        this.bufferLength=data.byteLength-offset;
      }
      return this;
    }

    digestHex(){
      const bitLength=this.bytesHashed*8;
      this.buffer[this.bufferLength++]=0x80;
      if(this.bufferLength>56){
        this.buffer.fill(0,this.bufferLength);
        this.processBlock(this.buffer);
        this.bufferLength=0;
      }
      this.buffer.fill(0,this.bufferLength,56);
      const high=Math.floor(bitLength/0x100000000)>>>0;
      const low=bitLength>>>0;
      this.buffer[56]=high>>>24;this.buffer[57]=high>>>16;this.buffer[58]=high>>>8;this.buffer[59]=high;
      this.buffer[60]=low>>>24;this.buffer[61]=low>>>16;this.buffer[62]=low>>>8;this.buffer[63]=low;
      this.processBlock(this.buffer);
      return [...this.state].map(value=>value.toString(16).padStart(8,'0')).join('');
    }
  }

  async function sha256Blob(blob){
    const hasher=new StreamingSha256();
    if(typeof blob.stream==='function'){
      const reader=blob.stream().getReader();
      try{
        while(true){
          const {done,value}=await reader.read();
          if(done)break;
          hasher.update(value);
        }
      }finally{
        reader.releaseLock?.();
      }
    }else{
      const chunkSize=1024*1024;
      for(let start=0;start<blob.size;start+=chunkSize){
        const chunk=await blob.slice(start,Math.min(blob.size,start+chunkSize)).arrayBuffer();
        hasher.update(new Uint8Array(chunk));
      }
    }
    return hasher.digestHex();
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

  async function enqueue(formData,options={}){
    try{return await directUpload(formData,options);}
    catch(error){
      if(error?.status===401){options.onUnauthorized?.();throw new Error('登入已逾時，請重新登入。');}
      if(error?.status===403)throw error;
      throw error;
    }
  }

  window.MaterialUploadClient={enqueue,directUpload,abort:abortUpload,sha256Blob,fingerprintFile};
})();
