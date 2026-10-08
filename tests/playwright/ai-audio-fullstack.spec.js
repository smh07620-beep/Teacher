const {test,expect}=require('@playwright/test');
const {login,api,job}=require('./ai-fullstack-helpers');
const {spawnSync}=require('node:child_process');
test.skip(process.env.TEACHER_AI_FULLSTACK_RUN!=='1','Requires isolated canonical runner');
function inspect(key,kind='wav') {
  const r=spawnSync(process.env.E2E_PYTHON,['tests/inspect_media_artifact.py',key,kind],{encoding:'utf8'});
  expect(r.status,r.stderr).toBe(0);return JSON.parse(r.stdout);
}
test('Audio: real preview and approved-script job → Worker → S3 WAV → canonical material → UI',async({page})=>{
  test.setTimeout(180000);page.setDefaultTimeout(20000);page.on('dialog',d=>d.accept());
  await login(page);
  const queued=await api(page,'/api/media-scripts/generate',{materialId:'e2e-source'});
  const generated=await job(page,'/api/media-scripts/jobs',queued.jobId);
  const saved=await api(page,'/api/media-scripts',{jobId:queued.jobId,title:'E2E-TEST-20261006 D approved narration',body:generated.body});
  await api(page,`/api/media-scripts/${saved.script.id}`,{status:'approved'},'PATCH');
  await page.waitForFunction(()=>Boolean(window.TeacherWorkspace1014?.openMedia));
  await page.evaluate(()=>window.TeacherWorkspace1014.openMedia());
  await page.locator('#teacher-media-tab-narration-1018').click();
  await expect(page.locator('#teacher-script-material-1014')).toContainText('E2E 多來源教材');
  // 已有教材的選單預設收合在「改用已有教材」裡；老師要用既有教材時先展開它。
  await page.locator('#teacher-script-existing-source-1033 > summary').click();
  await page.locator('#teacher-script-material-1014').selectOption('e2e-source');
  await expect(page.locator('#teacher-audio-script-1014')).toContainText('D approved narration');
  await page.locator('#teacher-audio-script-1014').selectOption(saved.script.id);
  await page.locator('#teacher-audio-voice-1014').selectOption('zm_010');
  const previewResponse=page.waitForResponse(r=>r.url().endsWith('/api/media-audio/preview')&&r.request().method()==='POST');
  await page.locator('#teacher-audio-preview-1014 button').click();
  const preview=await(await previewResponse).json();expect(preview.jobId).toBeTruthy();
  const previewResult=await job(page,'/api/media-audio/jobs',preview.jobId);
  expect(previewResult.voice).toBe('zm_010');
  const key=decodeURIComponent(new URL(previewResult.previewUrl).pathname).replace('/teacher-ai-media-e2e/','');
  expect(inspect(key)).toMatchObject({mime:'audio/wav',rate:24000,channels:1});
  const player=page.locator('#teacher-audio-preview-1014 audio');
  await expect.poll(()=>player.evaluate(a=>Number.isFinite(a.duration)&&a.duration>0)).toBe(true);
  await player.evaluate(a=>a.play());await expect.poll(()=>player.evaluate(a=>a.currentTime)).toBeGreaterThan(0);
  const formalResponse=page.waitForResponse(r=>r.url().endsWith('/api/media-audio/generate')&&r.request().method()==='POST');
  await page.locator('#teacher-audio-generate-1014').click();
  const formal=await(await formalResponse).json();
  const result=await job(page,'/api/media-audio/jobs',formal.jobId);
  await expect(page.locator('#teacher-audio-result-1014')).toContainText('AI 語音教材已建立',{timeout:30000});
  expect(result.voice).toBe('zm_010');expect(result.materialId).toBeTruthy();
  const materials=await api(page,'/api/slides/admin',null,'GET');
  const material=materials.find(m=>m.id===result.materialId);expect(material).toBeTruthy();
  expect(material.storageBackend).toBe('r2');
  expect(material.storageMeta).toMatchObject({sourceScriptId:saved.script.id,sourceMaterialId:'e2e-source',ttsVoice:'zm_010',ttsProvider:'kokoro-local',teacherApprovedBy:'e2eteacher'});
  const artifact=inspect(material.storageKey);expect(artifact.bytes).toBeGreaterThan(1024);
  expect(artifact.metadata['teacher-script-id']).toBe(saved.script.id);
  expect(result.model).toBe('deterministic-kokoro-stub');
});
