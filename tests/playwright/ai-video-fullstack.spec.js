const {test,expect}=require('@playwright/test');
const {login,api,job,outline,presentation}=require('./ai-fullstack-helpers');
const {spawnSync}=require('node:child_process');

// E validates the production H.264/AAC MP4 in a real browser. Playwright's
// bundled open-source Chromium can lack proprietary media codecs, so Linux CI
// deliberately uses branded Chrome instead of weakening or skipping playback.
test.use(process.env.CI && process.platform==='linux' ? {channel:'chrome'} : {});

test.skip(process.env.TEACHER_AI_FULLSTACK_RUN!=='1','Requires isolated canonical runner');

async function browserVideoState(player) {
  return player.evaluate(v=>({
    duration:Number.isFinite(v.duration)?v.duration:null,
    readyState:v.readyState,
    networkState:v.networkState,
    paused:v.paused,
    currentTime:v.currentTime,
    codecSupport:v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'),
    error:v.error?{code:v.error.code,message:v.error.message}:null,
  }));
}

test('Video: approved PPT → real Worker/FFmpeg → MP4/captions → browser review → publication ledger',async({page})=>{
  test.setTimeout(240000);page.setDefaultTimeout(20000);page.on('dialog',d=>d.accept());
  await login(page);
  const ppt=await presentation(page,await outline(page));
  await api(page,`/api/ai-presentations/${ppt.id}/approve`,{});
  await page.reload();
  const status=await api(page,'/api/ai-videos/status',null,'GET');
  expect(status.storage).toMatchObject({backend:'r2',requestedBackend:'mega',fallbackUsed:true});
  expect(status.ready).toBe(true);
  await page.waitForFunction(()=>Boolean(window.TeacherWorkspace1014?.openMedia));
  await page.evaluate(()=>window.TeacherWorkspace1014.openMedia());
  await page.locator('#teacher-media-tab-video-1018').click();
  await expect(page.locator('#teacher-ai-video-presentation-1015')).toContainText(ppt.title);
  await page.locator('#teacher-ai-video-presentation-1015').selectOption(ppt.id);
  await page.locator('#teacher-ai-video-voice-1015').selectOption('zf_002');
  const createdResponse=page.waitForResponse(r=>r.url().endsWith('/api/ai-videos/generate')&&r.request().method()==='POST');
  await page.locator('#teacher-ai-video-generate-1015').click();
  const queued=await(await createdResponse).json();expect(queued.jobId).toBeTruthy();
  const result=await job(page,'/api/ai-videos/jobs',queued.jobId);
  const card=page.locator(`[data-video-id="${result.videoId}"]`);await expect(card).toBeVisible({timeout:30000});
  const list=await api(page,`/api/ai-presentations/${ppt.id}/videos`,null,'GET');
  const video=list.videos.find(v=>v.id===result.videoId);
  expect(video).toMatchObject({artifactMimeType:'video/mp4',ttsProvider:'kokoro-local',ttsModel:'deterministic-kokoro-stub',ttsVoice:'zf_002',presentationId:ppt.id,presentationSha256:ppt.artifactSha256});
  expect(video.artifactBytes).toBeGreaterThan(1024);expect(video.artifactSha256).toMatch(/^[a-f0-9]{64}$/);
  expect(video.durationSeconds).toBeGreaterThan(0);expect(video.timeline.length).toBeGreaterThan(0);
  expect(video.timeline[0].start).toBe(0);
  expect(video.timeline.at(-1).end).toBeCloseTo(video.durationSeconds,2);
  for(let i=0;i<video.timeline.length;i++) {
    expect(video.timeline[i].durationSeconds).toBeGreaterThan(0);
    if(i)expect(video.timeline[i].start).toBeCloseTo(video.timeline[i-1].end,2);
  }
  expect(['text-fallback','libreoffice-headless']).toContain(video.frameRenderer);
  expect(video.renderMetrics.ttsSegmentCount).toBe(video.timeline.length);
  expect(video.renderMetrics.ffmpegSegmentCount).toBe(video.timeline.length);
  await expect(card.locator(`a[href="${video.previewUrl}"]`)).toContainText('MP4');
  await expect(card.locator(`a[href="${video.vttUrl}"]`)).toContainText('VTT');
  await expect(card.locator(`a[href="${video.srtUrl}"]`)).toContainText('SRT');
  const captions=await page.evaluate(async v=>({vtt:await(await fetch(v.vttUrl)).text(),srt:await(await fetch(v.srtUrl)).text()}),video);
  expect(captions.vtt).toContain('WEBVTT');expect(captions.vtt).toContain('-->');expect(captions.srt).toContain('-->');

  const previewHref=new URL(video.previewUrl,page.url()).href;
  const preview=await page.request.get(previewHref);
  expect(preview.headers()['content-type']).toContain('video/mp4');
  const bytes=await preview.body();expect(bytes.length).toBe(video.artifactBytes);
  expect(require('node:crypto').createHash('sha256').update(bytes).digest('hex')).toBe(video.artifactSha256);
  const key=decodeURIComponent(new URL(preview.url()).pathname).replace('/teacher-ai-media-e2e/','');
  const inspected=spawnSync(process.env.E2E_PYTHON,['tests/inspect_media_artifact.py',key,'mp4'],{encoding:'utf8'});
  expect(inspected.status,inspected.stderr).toBe(0);
  const artifact=JSON.parse(inspected.stdout);expect(artifact).toMatchObject({mime:'video/mp4',sha256:video.artifactSha256,decoded:true});
  expect(artifact.duration).toBeCloseTo(video.durationSeconds,1);

  // Native media elements depend on byte ranges for metadata/seek behavior.
  // Exercise the real authenticated preview route and signed R2 redirect.
  const ranged=await page.request.get(previewHref,{headers:{Range:'bytes=0-1023'}});
  expect(ranged.status()).toBe(206);
  expect(ranged.headers()['content-range']).toMatch(/^bytes 0-\d+\/\d+$/);
  expect((await ranged.body()).length).toBeGreaterThan(0);

  // Follow the real UI preview link, not a synthetic response or fake player.
  const popupPromise=page.waitForEvent('popup');await card.locator(`a[href="${video.previewUrl}"]`).click();
  const popup=await popupPromise;await popup.waitForLoadState('domcontentloaded');
  const player=popup.locator('video');
  await expect(player).toBeVisible();
  expect(new URL(popup.url()).pathname).toContain('/ai-videos/artifacts/');

  // Windows local Chromium can still lack the OS H264 decoder, but Linux CI
  // explicitly runs this file in branded Chrome and must prove real playback.
  if(process.platform!=='win32') {
    const codecSupport=await player.evaluate(v=>v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'));
    expect(codecSupport,'CI browser must advertise H.264/AAC MP4 support').not.toBe('');
    await player.evaluate(v=>v.load());
    try {
      await expect.poll(async()=>{
        const state=await browserVideoState(player);
        return !state.error && state.readyState>=1 && Number(state.duration)>0;
      },{timeout:30000,message:'Browser must load MP4 metadata and expose a positive duration'}).toBe(true);
    } catch(error) {
      const state=await browserVideoState(player);
      throw new Error(`Browser MP4 metadata failed: ${JSON.stringify(state)}\n${error.message}`);
    }
    const mediaState=await browserVideoState(player);
    expect(mediaState.duration).toBeCloseTo(video.durationSeconds,1);
    await player.evaluate(v=>{v.muted=true;return v.play();});
    try {
      await expect.poll(async()=>Number((await browserVideoState(player)).currentTime),{timeout:15000,message:'Browser must advance real MP4 playback'}).toBeGreaterThan(0);
    } catch(error) {
      const failedState=await browserVideoState(player);
      throw new Error(`Browser MP4 playback failed: ${JSON.stringify(failedState)}\n${error.message}`);
    }
  }
  await popup.close();
  const approveResponse=page.waitForResponse(r=>r.url().endsWith(`/api/ai-videos/${video.id}/approve`));
  await card.locator('[data-video-action="approve"]').click();expect((await(await approveResponse).json()).video.status).toBe('approved');
  const publishResponse=page.waitForResponse(r=>r.url().endsWith(`/api/ai-videos/${video.id}/publish`));
  await card.locator('[data-video-action="publish"]').click();
  const published=await(await publishResponse).json();expect(published.video.status).toBe('published');
  expect(published.publicationReceipt.receiptKey).toBeTruthy();
  expect(published.publicationReceipt.receipt).toMatchObject({videoId:video.id,artifactBackend:'r2',artifactStorageKey:key,artifactSha256:video.artifactSha256,artifactMimeType:'video/mp4'});
  expect(published.materialDerivative).toMatchObject({type:'video',derivativeId:video.id,materialId:'e2e-source'});
  const versions=await api(page,'/api/slides/e2e-source/versions',null,'GET');
  const derivative=versions.flatMap(v=>v.derivatives||[]).find(d=>d.derivativeId===video.id);
  expect(derivative).toBeTruthy();
  expect(JSON.stringify(derivative)).toContain(video.artifactSha256);
  await page.locator('#teacher-ai-video-refresh-1015').click();await expect(card).toContainText('published');
});
