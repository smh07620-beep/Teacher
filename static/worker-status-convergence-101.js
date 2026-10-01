/* Product convergence: normalize Worker/job presentation to four human states.
 * Raw job/Worker diagnostics remain available on demand for system admins.
 */
(function(){
  'use strict';

  const PANEL_ID='admin-section-worker';
  const HUMAN_LABELS=new Map([
    ['🔁 等待重試','⏳ 等待處理'],
    ['✅ 已完成','✅ 可使用'],
    ['❌ 失敗','⚠️ 需要處理'],
    ['⏹ 已取消','⚠️ 需要處理'],
    ['等待重試','等待處理'],
    ['已完成','可使用'],
    ['失敗','需要處理'],
    ['已取消','需要處理'],
  ]);

  function normalizeText(node){
    if(!(node instanceof HTMLElement))return;
    const current=(node.textContent||'').trim();
    const replacement=HUMAN_LABELS.get(current);
    if(replacement)node.textContent=replacement;
  }

  function collapseJobDiagnostics(panel){
    panel.querySelectorAll('tbody tr').forEach(row=>{
      if(row.dataset.productConvergence==='1')return;
      const cells=row.querySelectorAll('td');
      if(cells.length<4)return;
      const detailCell=cells[3];
      if(!detailCell)return;
      const details=document.createElement('details');
      details.className='rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-xs';
      const summary=document.createElement('summary');
      summary.className='cursor-pointer font-bold text-slate-600';
      summary.textContent='查看處理細節';
      details.appendChild(summary);
      const body=document.createElement('div');
      body.className='mt-2 space-y-1';
      while(detailCell.firstChild)body.appendChild(detailCell.firstChild);
      details.appendChild(body);
      detailCell.appendChild(details);
      row.dataset.productConvergence='1';
    });
  }

  function normalizeQueueCards(panel){
    panel.querySelectorAll('div').forEach(node=>{
      if(!(node instanceof HTMLElement))return;
      const text=(node.textContent||'').trim();
      if(text==='🔁 等待重試')node.textContent='⏳ 等待處理';
      if(text==='❌ 失敗')node.textContent='⚠️ 需要處理';
    });
  }

  function apply(){
    const panel=document.getElementById(PANEL_ID);
    if(!panel)return;
    panel.querySelectorAll('span').forEach(normalizeText);
    normalizeQueueCards(panel);
    collapseJobDiagnostics(panel);
  }

  function start(){
    apply();
    const host=document.getElementById(PANEL_ID)||document.getElementById('admin-workspace-content');
    if(!host)return;
    const observer=new MutationObserver(()=>apply());
    observer.observe(host,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();