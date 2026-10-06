const {test,expect}=require('@playwright/test');
const {spawnSync}=require('node:child_process');
const {login,api,outline,presentation,upload}=require('./ai-fullstack-helpers');
test('PowerPoint: real draft job, teacher approval, Worker, R2 artifact, notes and download',async({page},testInfo)=>{
  test.setTimeout(180000);
  page.setDefaultTimeout(20000);
  await login(page);
  const draft=await outline(page);
  expect(draft.sourceChunks.length).toBeGreaterThan(0);
  const ppt=await presentation(page,draft);
  const provenance=await api(page,`/api/ai-presentations/${ppt.id}/provenance`,null,'GET');
  expect(JSON.stringify(provenance)).toContain('e2e-source');
  expect(JSON.stringify(provenance)).toContain(draft.id);
  await page.evaluate(id=>{const a=document.createElement('a');a.href=`/api/ai-presentations/${id}/download`;a.textContent='Download generated PowerPoint';a.id='e2e-download-ppt';document.body.append(a);},ppt.id);
  const pending=page.waitForEvent('download'); await page.locator('#e2e-download-ppt').click();
  const download=await pending; const target=testInfo.outputPath('generated.pptx');await download.saveAs(target);
  const inspected=spawnSync(process.env.E2E_PYTHON||'python',['tests/inspect_ai_artifact.py',target,'pptx'],{encoding:'utf8'});
  expect(inspected.status,inspected.stderr).toBe(0);
  expect(JSON.parse(inspected.stdout).slides).toBeGreaterThanOrEqual(2);
});
test('PowerPoint accepts uploaded PDF, DOCX, PPTX, image, pasted text and mixed existing sources',async({page})=>{
  test.setTimeout(600000);page.setDefaultTimeout(20000);
  await login(page);
  const ids=[];
  for(const name of ['source.pdf','source.docx','source.pptx','source.png','pasted.txt']) {
    const id=await upload(page,name);ids.push(id);
    const draft=await outline(page,id);
    expect(draft.sourceChunks.map(c=>c.materialId)).toContain(id);
    const ppt=await presentation(page,draft);expect(ppt.slides.length).toBeGreaterThan(0);
  }
  const mixed=await outline(page,'e2e-source',ids);
  expect(new Set(mixed.sourceChunks.map(c=>c.materialId))).toEqual(new Set(['e2e-source',...ids]));
  const ppt=await presentation(page,mixed);expect(ppt.artifactSha256).toMatch(/^[a-f0-9]{64}$/);
});
