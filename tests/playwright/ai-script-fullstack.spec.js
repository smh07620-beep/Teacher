const {test,expect}=require('@playwright/test');
const {login,api,job,outline}=require('./ai-fullstack-helpers');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
test.skip(process.env.TEACHER_AI_FULLSTACK_RUN!=='1','Requires isolated full-stack runner');

async function openScript(page) {
  await page.waitForFunction(()=>Boolean(window.TeacherWorkspace1014?.openMedia));
  await page.evaluate(()=>window.TeacherWorkspace1014.openMedia());
  await page.locator('#teacher-media-tab-narration-1018').click();
  await expect(page.locator('#teacher-script-material-1014')).toContainText('E2E 多來源教材');
  await page.locator('#teacher-script-material-1014').selectOption('e2e-source');
}

test('Script: real mixed source job → UI edit → save → reload → approved narration source',async({page},testInfo)=>{
  test.setTimeout(180000);page.setDefaultTimeout(20000);
  page.on('dialog',dialog=>dialog.accept());
  await login(page);
  await openScript(page);
  const formats=(process.env.E2E_SOURCE_FORMATS||'source.pdf,source.pptx').split(',').filter(n=>['source.pdf','source.pptx'].includes(n));
  await page.locator('#teacher-script-source-file-1030').setInputFiles(formats.map(n=>path.join(process.env.E2E_SOURCE_DIR,n)));
  await page.locator('#teacher-script-source-upload-1030').click();
  await expect(page.locator('#teacher-script-status-1014')).toContainText(`已加入 ${formats.length} 份`,{timeout:90000});
  await page.locator('#teacher-script-paste-title-1030').fill('E2E-TEST-20261006 補充 SOP');
  await page.locator('#teacher-script-paste-1030').fill('Specimen collection safety, quality control and patient identity verification. '.repeat(5));
  await page.locator('#teacher-script-paste-add-1030').click();
  await expect(page.locator('#teacher-script-status-1014')).toContainText('已加入',{timeout:90000});
  await page.locator('#teacher-script-generate-1014').click();
  await expect(page.locator('#teacher-script-body-1014')).not.toHaveValue('',{timeout:90000});
  const original=await page.locator('#teacher-script-body-1014').inputValue();
  const savedResponse=page.waitForResponse(r=>r.url().endsWith('/api/media-scripts')&&r.request().method()==='POST');
  await page.locator('#teacher-script-save-1014').click();
  const saved=await(await savedResponse).json();expect(new Set(saved.script.sourceChunks.map(c=>c.materialId)).size).toBe(formats.length+2);
  expect(saved.script.body).toBe(original);
  const edited=original+'\n教師修改：E2E-TEST-20261006 核對檢體品質後再執行分析。';
  await page.locator('#teacher-script-title-1014').fill('E2E-TEST-20261006 已修改講稿');
  await page.locator('#teacher-script-body-1014').fill(edited);
  const updatedResponse=page.waitForResponse(r=>r.url().endsWith(`/api/media-scripts/${saved.script.id}`)&&r.request().method()==='PATCH');
  await page.locator('#teacher-script-save-1014').click();
  const updated=await(await updatedResponse).json();expect(updated.script).toMatchObject({id:saved.script.id,body:edited,status:'draft'});
  await page.locator('#teacher-script-approve-1014').click();
  await expect(page.locator('#teacher-script-saved-1014')).toContainText('已核准');
  await page.reload();await openScript(page);
  await page.locator(`[data-script-id="${saved.script.id}"]`).click();
  await expect(page.locator('#teacher-script-body-1014')).toHaveValue(edited);
  const persisted=await api(page,'/api/media-scripts?materialId=e2e-source',null,'GET');
  expect(persisted.find(s=>s.id===saved.script.id)).toMatchObject({body:edited,status:'approved',approvedBy:'e2eteacher'});
  await expect(page.locator('#teacher-audio-script-1014')).toContainText('E2E-TEST-20261006 已修改講稿');
  // Existing production video contract consumes approved PowerPoint speaker
  // notes. Carry the reloaded, approved script through that durable handoff;
  // video rendering itself belongs to segment E, not this script test.
  const draft=await outline(page);
  const queued=await api(page,'/api/ai-presentations/generate',{draftId:draft.id,slides:[
    {title:'E2E 講稿引用',bullets:['核對檢體品質'],speakerNotes:persisted.find(s=>s.id===saved.script.id).body},
    {title:'E2E 教師確認',bullets:['發布前核准'],speakerNotes:'教師確認後才可發布。'},
  ]});
  const result=await job(page,'/api/ai-presentations/jobs',queued.id);
  await page.evaluate(id=>{const a=document.createElement('a');a.id='e2e-script-ppt';a.href=`/api/ai-presentations/${id}/download`;a.textContent='下載講稿引用簡報';document.body.append(a);},result.presentationId);
  const pending=page.waitForEvent('download');await page.locator('#e2e-script-ppt').click();
  const target=testInfo.outputPath('script-handoff.pptx');await(await pending).saveAs(target);
  const inspected=spawnSync(process.env.E2E_PYTHON,['tests/inspect_ai_artifact.py',target,'pptx',edited],{encoding:'utf8'});
  expect(inspected.status,inspected.stderr).toBe(0);
});
