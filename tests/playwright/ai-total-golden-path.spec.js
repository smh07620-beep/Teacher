const {test,expect}=require('@playwright/test');
test.skip(process.env.TEACHER_AI_FG_FULLSTACK_RUN!=='1','Requires isolated F/G full-stack runner');
const baseURL=process.env.TEACHER_AI_FG_FULLSTACK_BASE_URL||'http://127.0.0.1:4177';
const password=process.env.TEACHER_CI_BROWSER_PASSWORD||'';

async function login(page,username='e2eteacher',next='/system?area=internal&group=grpBio&admin=1&workspace=course-materials&persona=teacher'){
  await page.goto(`${baseURL}/login?next=${encodeURIComponent(next)}`);
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(password);
  await Promise.all([
    page.waitForURL(url=>!url.pathname.endsWith('/login'), { timeout: 45000, waitUntil: 'commit' }),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
  await page.waitForLoadState('domcontentloaded');
}
async function api(page,path,body,method='POST'){
  return page.evaluate(async({path,body,method})=>{
    const response=await fetch(path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(`${method} ${path}: ${response.status} ${JSON.stringify(data)}`);
    return data;
  },{path,body,method});
}
async function waitJob(page,path,id,timeout=120000){
  let state;
  await expect.poll(async()=>{
    state=await api(page,`${path}/${id}`,null,'GET');
    if(state.status==='failed')throw new Error(JSON.stringify(state));
    return state.status;
  },{timeout,intervals:[300,500,1000,2000]}).toBe('completed');
  return state;
}
async function uploadTextMaterial(page){
  await page.waitForFunction(()=>Boolean(window.MaterialUploadClient?.directUpload));
  const queued=await page.evaluate(async()=>{
    const file=new File([
      'E2E-TEST-20261006 教材。檢體收件須核對病人識別、檢體種類、採檢時間與品質控制。'.repeat(8)
    ],'E2E-TEST-20261006-golden-path.txt',{type:'text/plain;charset=utf-8'});
    const form=new FormData();
    form.append('file',file);
    for(const [key,value] of Object.entries({
      title:'E2E-TEST-20261006 總驗收教材',desc:'F/G combined full-stack source',
      group:'grpBio',area:'internal',courseId:'',category:'',materialType:'standard',authoringOnly:'false',
    }))form.append(key,value);
    return window.MaterialUploadClient.directUpload(form,{fileName:file.name});
  });
  const completed=await waitJob(page,'/api/material-jobs',queued.jobId,120000);
  const materialId=completed.materialId||queued.materialId;
  expect(materialId).toBeTruthy();
  return materialId;
}
async function generateOutline(page,materialId){
  const queued=await api(page,'/api/ai-material-drafts/generate',{materialId,referenceMaterialIds:[],outputType:'slides'});
  const generated=(await waitJob(page,'/api/ai-material-drafts/jobs',queued.jobId||queued.id)).result;
  const saved=await api(page,'/api/ai-material-drafts',{jobId:queued.jobId||queued.id,title:generated.title,body:generated.body});
  const approved=await api(page,`/api/ai-material-drafts/${saved.draft.id}`,{status:'approved'},'PATCH');
  return approved.draft;
}
async function generateApprovedScript(page,materialId){
  const queued=await api(page,'/api/media-scripts/generate',{
    materialId,referenceMaterialIds:[],targetMinutes:3,tone:'clinical',focus:'檢體品質與病人識別',
  });
  const state=await waitJob(page,'/api/media-scripts/jobs',queued.jobId);
  const generated=state.result;
  const saved=await api(page,'/api/media-scripts',{
    jobId:queued.jobId,title:'E2E-TEST-20261006 核准講稿',body:generated.body,
  });
  const approved=await api(page,`/api/media-scripts/${saved.script.id}`,{
    title:saved.script.title,body:saved.script.body,status:'approved',
  },'PATCH');
  expect(approved.script.status).toBe('approved');
  return approved.script;
}
async function approveVideoSubtitle(page){
  const queued=await api(page,'/api/media-subtitles/generate',{
    materialId:'e2e-video-source',language:'zh-TW',label:'E2E 繁體中文字幕',
  });
  const state=await waitJob(page,'/api/media-subtitles/jobs',queued.jobId);
  const rows=await api(page,'/api/media-subtitles?materialId=e2e-video-source',null,'GET');
  const draft=rows.find(row=>row.id===state.result.subtitleId);
  const approved=await api(page,`/api/media-subtitles/${draft.id}`,{
    status:'approved',label:draft.label,vttText:draft.vttText,
  },'PATCH');
  return approved;
}

test('G: upload → script → audio → PowerPoint → video → questions/subtitles → learner → teacher record',async({page,browser})=>{
  test.setTimeout(360000);
  page.setDefaultTimeout(25000);
  await login(page);

  // 1. Real Browser direct upload → R2-compatible staging → material Worker → canonical material.
  const materialId=await uploadTextMaterial(page);
  const teacherMaterials=await api(page,'/api/slides/admin',null,'GET');
  expect(teacherMaterials.find(item=>item.id===materialId)).toMatchObject({active:true,group:'grpBio',area:'internal'});

  // 2. Real script job → saved/approved teacher script.
  const script=await generateApprovedScript(page,materialId);
  expect(script.approvedBy).toBe('e2eteacher');

  // 3. Real narration job → AI Worker → deterministic inference seam → R2-compatible WAV material.
  const audioQueued=await api(page,'/api/media-audio/generate',{scriptId:script.id,voice:'zf_001',instructions:'清楚、沉穩'});
  const audioState=await waitJob(page,'/api/media-audio/jobs',audioQueued.jobId,120000);
  expect(audioState.result.materialId).toBeTruthy();
  expect(audioState.result.voice).toBe('zf_001');
  const audioMaterial=await api(page,`/api/slides/admin`,null,'GET');
  expect(audioMaterial.find(item=>item.id===audioState.result.materialId)).toBeTruthy();

  // 4. Outline → PowerPoint with the approved script carried as speaker notes.
  const draft=await generateOutline(page,materialId);
  const presentationQueued=await api(page,'/api/ai-presentations/generate',{
    draftId:draft.id,
    slides:[
      {title:'E2E 教學重點',bullets:['核對病人識別','檢體品質'],speakerNotes:script.body},
      {title:'E2E 教師確認',bullets:['記錄品質控制'],speakerNotes:'教師確認後發布。'},
    ],
  });
  const presentationState=await waitJob(page,'/api/ai-presentations/jobs',presentationQueued.id,150000);
  const presentationId=presentationState.result.presentationId;
  let presentation=await api(page,`/api/ai-presentations/${presentationId}`,null,'GET');
  expect(presentation.artifactReady).toBeTruthy();
  expect(presentation.artifactBytes).toBeGreaterThan(1000);
  const approvedPresentation=await api(page,`/api/ai-presentations/${presentationId}/approve`,{});
  expect(approvedPresentation.presentation.status).toBe('approved');

  // 5. Approved PowerPoint → real AI video job → FFmpeg MP4 + VTT/SRT + durable storage.
  const videoQueued=await api(page,'/api/ai-videos/generate',{presentationId,voice:'zf_001'});
  const videoState=await waitJob(page,'/api/ai-videos/jobs',videoQueued.jobId,180000);
  expect(videoState.result.videoId).toBeTruthy();
  const videoList=await api(page,`/api/ai-presentations/${presentationId}/videos`,null,'GET');
  const video=videoList.videos.find(item=>item.id===videoState.result.videoId);
  expect(video.artifactBytes).toBeGreaterThan(0);
  expect(video.durationSeconds).toBeGreaterThan(0);
  expect(video.previewUrl).toBeTruthy();
  expect(video.vttUrl).toBeTruthy();
  expect(video.srtUrl).toBeTruthy();
  await api(page,`/api/ai-videos/${video.id}/approve`,{});
  const publishedVideo=await api(page,`/api/ai-videos/${video.id}/publish`,{acknowledgeWarnings:true});
  expect(publishedVideo.video.status).toBe('published');
  expect(publishedVideo.publicationReceipt).toBeTruthy();
  expect(publishedVideo.materialDerivative).toBeTruthy();

  // 6. Independent canonical video material gets real subtitle job and approval.
  const approvedSubtitle=await approveVideoSubtitle(page);
  expect(approvedSubtitle.status).toBe('approved');
  expect(approvedSubtitle.vttText).toContain('WEBVTT');

  // 7. AI question generation: one normal source question + one timed video question.
  const category=await api(page,'/api/quiz-categories',{
    title:'E2E-TEST-20261006 總 Golden Path',group:'grpBio',area:'internal',
    drawCount:2,audience:'grpBio 學員',
  });
  const normalQueued=await api(page,'/api/ai-questions/generate',{
    quizCategoryId:category.id,materialIds:[materialId],count:1,questionType:'choice',difficulty:'standard',strategy:'auto',
  });
  const normal=(await waitJob(page,'/api/ai-questions/jobs',normalQueued.jobId)).result.questions[0];
  const videoQuestionQueued=await api(page,'/api/ai-questions/generate',{
    quizCategoryId:category.id,materialIds:['e2e-video-source'],count:1,questionType:'video_choice',difficulty:'standard',strategy:'auto',
  });
  const timed=(await waitJob(page,'/api/ai-questions/jobs',videoQuestionQueued.jobId)).result.questions[0];
  expect(timed.questionType).toBe('video');
  expect(Number(timed.answerConfig.pauseAt)).toBeGreaterThan(0);
  const imported=await api(page,'/api/ai-questions/import',{quizCategoryId:category.id,questions:[normal,timed]});
  expect(imported.imported).toBe(2);
  await api(page,`/api/exam-windows/${category.id}`,{
    opensAt:new Date(Date.now()-3600000).toISOString(),
    closesAt:new Date(Date.now()+86400000).toISOString(),
  },'PUT');
  await api(page,`/api/quiz-categories/${category.id}/review`,{});
  expect((await api(page,`/api/quiz-categories/${category.id}/publish`,{})).active).toBeTruthy();

  // 8. Separate learner session sees the uploaded material and completes both questions.
  const learnerContext=await browser.newContext();
  const learner=await learnerContext.newPage();
  learner.setDefaultTimeout(25000);
  await login(learner,'e2estudent',`/system?area=internal&group=grpBio&examId=${category.id}`);
  const learnerMaterials=await api(learner,'/api/slides',null,'GET');
  expect(learnerMaterials.find(item=>item.id===materialId)).toBeTruthy();
  await learner.evaluate(()=>switchLearningModule('exam'));
  await expect(learner.locator('#quiz-questions-list .question-card-learning')).toHaveCount(2);

  const timedVideo=learner.locator('video[data-question-pause-at]');
  await expect(timedVideo).toHaveCount(1);
  const timedIndex=Number(await timedVideo.getAttribute('data-question-index'));
  await expect(learner.locator(`#video-answer-${timedIndex}`)).toHaveClass(/hidden/);
  await expect.poll(async()=>timedVideo.locator('track[kind="subtitles"]').count(),{timeout:15000}).toBe(1);
  await timedVideo.evaluate((node,pauseAt)=>{
    Object.defineProperty(node,'currentTime',{configurable:true,value:Number(pauseAt)+0.2});
    node.dispatchEvent(new Event('timeupdate'));
  },await timedVideo.getAttribute('data-question-pause-at'));
  await expect(learner.locator(`#video-answer-${timedIndex}`)).not.toHaveClass(/hidden/);

  for(let i=0;i<2;i++){
    await learner.locator(`#question-card-${i} input[type=radio]`).first().check();
  }
  const submitted=learner.waitForResponse(r=>r.url().includes('/submit')&&r.request().method()==='POST');
  await learner.locator('#submit-btn').click();
  const result=await(await submitted).json();
  expect(result.score).toBe(100);
  expect(result.recordId).toBeTruthy();
  await expect(learner.locator('#final-score-text')).toHaveText('100');

  // 9. Teacher sees the same durable learner record after learner completion.
  const records=await api(page,'/api/records',null,'GET');
  expect(records.find(row=>row.id===result.recordId)).toMatchObject({
    empId:'E2ES01',score:100,quizCategoryId:category.id,
  });
  await learnerContext.close();
});
