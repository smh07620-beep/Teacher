const {test,expect}=require('@playwright/test');
test.skip(process.env.TEACHER_AI_FG_FULLSTACK_RUN!=='1','Requires isolated F/G full-stack runner');
const baseURL=process.env.TEACHER_AI_FG_FULLSTACK_BASE_URL||'http://127.0.0.1:4177';
const password=process.env.TEACHER_CI_BROWSER_PASSWORD||'';

async function login(page,username='e2eteacher',next='/system?area=internal&group=grpBio&admin=1'){
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
async function waitJob(page,path,id,timeout=90000){
  let state;
  await expect.poll(async()=>{
    state=await api(page,`${path}/${id}`,null,'GET');
    if(state.status==='failed')throw new Error(JSON.stringify(state));
    return state.status;
  },{timeout,intervals:[300,500,1000]}).toBe('completed');
  return state;
}

test('F: real subtitle job → approved VTT → timestamp video question → learner saved answer',async({page,browser})=>{
  test.setTimeout(180000);
  page.setDefaultTimeout(20000);
  await login(page);

  const subtitleQueued=await api(page,'/api/media-subtitles/generate',{
    materialId:'e2e-video-source',language:'zh-TW',label:'E2E 繁體中文字幕',
  });
  const subtitleState=await waitJob(page,'/api/media-subtitles/jobs',subtitleQueued.jobId);
  expect(subtitleState.result.subtitleId).toBeTruthy();

  const subtitles=await api(page,'/api/media-subtitles?materialId=e2e-video-source',null,'GET');
  const draft=subtitles.find(item=>item.id===subtitleState.result.subtitleId);
  expect(draft.vttText).toContain('WEBVTT');
  expect(draft.vttText).toContain('播放到一秒後進入時間點考題');
  const approved=await api(page,`/api/media-subtitles/${draft.id}`,{
    status:'approved',label:draft.label,vttText:draft.vttText,
  },'PATCH');
  expect(approved.status).toBe('approved');
  expect(approved.approvedBy).toBe('e2eteacher');

  const category=await api(page,'/api/quiz-categories',{
    title:'E2E-TEST-20261006 字幕時間點考題',group:'grpBio',area:'internal',
    drawCount:1,audience:'grpBio 學員',
  });
  const queued=await api(page,'/api/ai-questions/generate',{
    quizCategoryId:category.id,materialIds:['e2e-video-source'],count:1,
    questionType:'video_choice',difficulty:'standard',strategy:'auto',
  });
  const generated=await waitJob(page,'/api/ai-questions/jobs',queued.jobId);
  const question=generated.result.questions[0];
  expect(question.questionType).toBe('video');
  expect(question.answerConfig.mediaUrl).toBe('/view/e2e-video-source');
  expect(Number(question.answerConfig.pauseAt)).toBeGreaterThan(0);

  const imported=await api(page,'/api/ai-questions/import',{
    quizCategoryId:category.id,questions:[question],
  });
  expect(imported.imported).toBe(1);
  await api(page,`/api/exam-windows/${category.id}`,{
    opensAt:new Date(Date.now()-3600000).toISOString(),
    closesAt:new Date(Date.now()+86400000).toISOString(),
  },'PUT');
  await api(page,`/api/quiz-categories/${category.id}/review`,{});
  const published=await api(page,`/api/quiz-categories/${category.id}/publish`,{});
  expect(published.active).toBeTruthy();

  const learnerContext=await browser.newContext();
  const learner=await learnerContext.newPage();
  learner.setDefaultTimeout(20000);
  await login(learner,'e2estudent',`/system?area=internal&group=grpBio&examId=${category.id}`);
  await learner.evaluate(()=>switchLearningModule('exam'));

  const video=learner.locator('#question-video-0');
  await expect(video).toBeVisible();
  await expect(learner.locator('#video-answer-0')).toHaveClass(/hidden/);

  // Approved material subtitle is attached as a real HTML5 text track.
  await expect.poll(async()=>video.locator('track[kind="subtitles"]').count(),{timeout:15000}).toBe(1);
  const track=video.locator('track[kind="subtitles"]');
  const trackSrc=await track.getAttribute('src');
  expect(trackSrc).toContain(`/api/media-subtitles/${draft.id}.vtt`);
  const vtt=await learner.evaluate(async src=>{
    const response=await fetch(src,{credentials:'same-origin'});
    return {status:response.status,text:await response.text(),type:response.headers.get('content-type')||''};
  },trackSrc);
  expect(vtt.status).toBe(200);
  expect(vtt.type).toContain('text/vtt');
  expect(vtt.text).toContain('WEBVTT');

  // The actual learner gating handler must keep answers hidden before the cue,
  // then pause/unlock at the persisted timestamp.
  await video.evaluate((node,pauseAt)=>{
    Object.defineProperty(node,'currentTime',{configurable:true,value:Number(pauseAt)-0.4});
    node.dispatchEvent(new Event('timeupdate'));
  },question.answerConfig.pauseAt);
  await expect(learner.locator('#video-answer-0')).toHaveClass(/hidden/);
  await video.evaluate((node,pauseAt)=>{
    Object.defineProperty(node,'currentTime',{configurable:true,value:Number(pauseAt)+0.2});
    node.dispatchEvent(new Event('timeupdate'));
  },question.answerConfig.pauseAt);
  await expect(learner.locator('#video-answer-0')).not.toHaveClass(/hidden/);
  await expect(learner.locator('#video-cue-0')).toContainText('已到達指定學習節點');

  await learner.locator('#question-card-0 input[type=radio]').first().check();
  const submitted=learner.waitForResponse(r=>r.url().includes('/submit')&&r.request().method()==='POST');
  await learner.locator('#submit-btn').click();
  const result=await(await submitted).json();
  expect(result.score).toBe(100);
  expect(result.recordId).toBeTruthy();

  const records=await api(page,'/api/records',null,'GET');
  expect(records.find(row=>row.id===result.recordId)).toMatchObject({score:100,empId:'E2ES01'});
  await learnerContext.close();
});
