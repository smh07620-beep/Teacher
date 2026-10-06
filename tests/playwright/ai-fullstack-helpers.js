const { expect } = require('@playwright/test');
const baseURL = 'http://127.0.0.1:4176';
async function login(page, username='e2eteacher', next='/system?area=internal&group=grpBio&admin=1&workspace=course-materials&persona=teacher') {
  await page.goto(`${baseURL}/login?next=${encodeURIComponent(next)}`);
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(process.env.TEACHER_CI_BROWSER_PASSWORD);
  await Promise.all([page.waitForURL(u=>!u.pathname.endsWith('/login')),page.locator('#login-form button[type=submit]').click()]);
  await page.waitForLoadState('domcontentloaded');
}
async function api(page,path,body,method='POST') {
  return page.evaluate(async ({path,body,method})=>{
    const r=await fetch(path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
    const data=await r.json(); if(!r.ok) throw new Error(`${method} ${path}: ${r.status} ${JSON.stringify(data)}`); return data;
  },{path,body,method});
}
async function job(page,path,id) {
  let result;
  await expect.poll(async()=>{
    result=await api(page,`${path}/${id}`,null,'GET');
    if(result.status==='failed') throw new Error(JSON.stringify(result));
    return result.status;
  },{timeout:90000,intervals:[300,500,1000]}).toBe('completed');
  return result.result;
}
async function outline(page, materialId='e2e-source', referenceMaterialIds=[]) {
  const queued=await api(page,'/api/ai-material-drafts/generate',{materialId,referenceMaterialIds,outputType:'slides'});
  const generated=await job(page,'/api/ai-material-drafts/jobs',queued.jobId||queued.id);
  const {draft}=await api(page,'/api/ai-material-drafts',{jobId:queued.jobId||queued.id,title:generated.title,body:generated.body});
  const approved=await api(page,`/api/ai-material-drafts/${draft.id}`,{status:'approved'},'PATCH');
  expect(approved.draft.approvedBy).toBe('e2eteacher');
  return approved.draft;
}
async function presentation(page,draft) {
  const queued=await api(page,'/api/ai-presentations/generate',{draftId:draft.id});
  const generated=await job(page,'/api/ai-presentations/jobs',queued.id);
  const ppt=await api(page,`/api/ai-presentations/${generated.presentationId}`,null,'GET');
  expect(ppt.artifactBytes).toBeGreaterThan(1000); expect(ppt.artifactReady).toBeTruthy();
  return ppt;
}
async function upload(page,name) {
  const fs=require('node:fs'),path=require('node:path');
  const bytes=fs.readFileSync(path.join(process.env.E2E_SOURCE_DIR,name)).toString('base64');
  await page.waitForFunction(()=>Boolean(window.MaterialUploadClient?.directUpload));
  const queued=await page.evaluate(async({name,bytes})=>{
    const file=new File([Uint8Array.from(atob(bytes),c=>c.charCodeAt(0))],name);
    const form=new FormData();form.append('file',file);
    for(const [key,value] of Object.entries({title:`E2E-TEST-20261006 ${name}`,group:'grpBio',area:'internal',materialType:'standard',authoringOnly:'true'}))form.append(key,value);
    return window.MaterialUploadClient.directUpload(form,{fileName:name});
  },{name,bytes});
  await job(page,'/api/material-jobs',queued.jobId);
  const persisted=await api(page,`/api/material-jobs/${queued.jobId}`,null,'GET');
  expect(persisted.materialId).toBeTruthy();
  expect(queued.materialId).toBe(persisted.materialId);
  return persisted.materialId;
}
module.exports={baseURL,login,api,job,outline,presentation,upload};
