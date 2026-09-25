/* V6.1.0: public home-area switch plus role-aware dashboard bootstrap. */
(function(){
  const $=(s,r=document)=>r.querySelector(s); const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const LEARNER_NAME_KEY='smh_learner_name', LEARNER_EMPID_KEY='smh_learner_empid';
  let authUser=null;
  const header=$('.v56-header'), menu=$('[data-v56-menu]');
  if(menu&&header) menu.addEventListener('click',()=>header.classList.toggle('menu-open'));
  const back=$('.v56-backtop');
  if(back){const sync=()=>back.classList.toggle('show',scrollY>350);addEventListener('scroll',sync,{passive:true});back.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));sync();}
  const search=$('[data-v56-search]');
  if(search){
    const routes=[
      ['生化','/system?area=internal&group=grpBio&module=materials'],['鏡檢','/system?area=internal&group=grpMicro&module=materials'],['血清','/system?area=internal&group=grpSero&module=materials'],['血庫','/system?area=internal&group=grpBB&module=materials'],['細菌','/system?area=internal&group=grpBact&module=materials'],['血液','/system?area=internal&group=grpHema&module=materials'],['PGY','/system?area=pgy&group=grpNew&module=materials&from=home'],['新進','/system?area=pgy&group=grpNew&module=materials&from=home'],['考核','/system?area=internal&group=grpBio&module=exam'],['教材','/internal'],['課程管理','/system?area=internal&group=grpBio&admin=1&workspace=course-materials'],['題庫','/system?area=internal&group=grpBio&admin=1&workspace=questions'],['教師評核','/system?area=internal&group=grpBio&admin=1&workspace=teacher']
    ];
    search.addEventListener('keydown',e=>{if(e.key!=='Enter')return;const q=search.value.trim().toLowerCase();if(!q)return;const hit=routes.find(([k])=>q.includes(k.toLowerCase())||k.toLowerCase().includes(q));location.href=hit?hit[1]:'/#groups';});
  }
  const fmtDate=v=>{if(!v)return '';const d=new Date(v);return Number.isNaN(d.getTime())?String(v).slice(0,10):d.toLocaleDateString('zh-TW',{year:'numeric',month:'2-digit',day:'2-digit'});};
  const typeOf=m=>{const n=(m.filename||m.title||'').toLowerCase();if(n.endsWith('.pdf'))return['PDF','pdf'];if(/\.(ppt|pptx)$/.test(n))return['PPT','ppt'];if(/\.(doc|docx)$/.test(n))return['DOC','doc'];if(/\.(png|jpe?g|webp|gif)$/.test(n))return['IMG','img'];return['FILE','doc'];};
  const readLocal=k=>{try{return localStorage.getItem(k)||'';}catch(_){return '';}};
  const writeLocal=(k,v)=>{try{if(v)localStorage.setItem(k,v);else localStorage.removeItem(k);}catch(_){}};
  const setText=(id,v)=>{const el=$(id);if(el)el.textContent=String(v);};

  // Teacher 6.6 M2:
  // 首頁 API 使用短 TTL session cache + 同網址 inflight dedupe。
  // 不快取登入狀態；登入仍每次向伺服器確認。
  const HOME_CACHE_TTL=45000;
  const HOME_PERSONAL_TTL=15000;
  const HOME_SLIDES_TTL=60000;
  const HOME_CACHE_PREFIX='teacher66-home:';
  const homeMemoryCache=new Map();
  const homeInflight=new Map();

  function homeCacheKey(url){
    return HOME_CACHE_PREFIX+url;
  }

  function readHomeCache(url,ttl){
    const now=Date.now();
    const mem=homeMemoryCache.get(url);

    if(mem && (now-mem.at)<ttl){
      return mem.data;
    }

    try{
      const raw=sessionStorage.getItem(homeCacheKey(url));
      if(!raw)return null;

      const cached=JSON.parse(raw);

      if(
        !cached
        || typeof cached.at!=='number'
        || (now-cached.at)>=ttl
      ){
        sessionStorage.removeItem(homeCacheKey(url));
        return null;
      }

      homeMemoryCache.set(url,cached);
      return cached.data;
    }catch(_){
      return null;
    }
  }

  function writeHomeCache(url,data){
    const cached={
      at:Date.now(),
      data
    };

    homeMemoryCache.set(url,cached);

    try{
      sessionStorage.setItem(
        homeCacheKey(url),
        JSON.stringify(cached)
      );
    }catch(_){}
  }

  function clearHomeCache(){
    homeMemoryCache.clear();
    homeInflight.clear();

    try{
      for(let i=sessionStorage.length-1;i>=0;i--){
        const key=sessionStorage.key(i);
        if(key && key.startsWith(HOME_CACHE_PREFIX)){
          sessionStorage.removeItem(key);
        }
      }
    }catch(_){}
  }

  async function fetchJSONCached(
    url,
    ttl=HOME_CACHE_TTL
  ){
    const cached=readHomeCache(url,ttl);

    if(cached!==null){
      return cached;
    }

    if(homeInflight.has(url)){
      return homeInflight.get(url);
    }

    const request=(
      async()=>{
        const response=await fetch(url,{
          credentials:'same-origin'
        });

        const data=await response
          .json()
          .catch(()=>null);

        if(!response.ok){
          const message=
            data?.error
            || `讀取失敗（${response.status}）`;

          throw new Error(message);
        }

        writeHomeCache(
          url,
          data
        );

        return data;
      }
    )();

    homeInflight.set(
      url,
      request
    );

    try{
      return await request;
    }finally{
      homeInflight.delete(url);
    }
  }

  function setupPhase3AreaSwitch(){
    const buttons=$$('[data-phase3-area]'), groups=$$('[data-phase3-group]'), all=$('#phase3-area-all'), pendingAll=$('#v66-pending-all'), progressLinks=$$('[data-home-progress-link]'), areaLinks=$$('[data-home-area-link]');
    if(!buttons.length||!groups.length)return;
    const saved=readLocal('smh_home_training_area');
    const apply=area=>{
      const next=area==='pgy'?'pgy':'internal';writeLocal('smh_home_training_area',next);
      buttons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.phase3Area===next)));
      groups.forEach(link=>{link.href=`/system?area=${next}&group=${encodeURIComponent(link.dataset.phase3Group)}&module=materials&from=home`;});
      if(all){
        all.href=next==='pgy'?'/pgy':'/internal';
        all.textContent=next==='pgy'?'PGY 全部 →':'院內全部 →';
      }
      areaLinks.forEach(link=>{link.href=next==='pgy'?'/pgy':'/internal';});

      if(pendingAll){
        const examGroup=next==='pgy'?'grpNew':'grpBio';

        const qs=new URLSearchParams({
          area:next,
          group:examGroup,
          module:'exam',
          from:'home'
        });

        pendingAll.href=`/system?${qs.toString()}`;
      }
      const progressGroup=next==='pgy'?'grpNew':'grpBio';
      const progressQs=new URLSearchParams({area:next,group:progressGroup,module:'progress',from:'home'});
      progressLinks.forEach(link=>{link.href=`/system?${progressQs.toString()}`;});
    };
    buttons.forEach(button=>button.addEventListener('click',()=>apply(button.dataset.phase3Area)));
    apply(saved);
  }

  async function loadAuthState(){
    try{const r=await fetch('/api/auth/me',{cache:'no-store'}),d=await r.json().catch(()=>({}));authUser=d.authenticated?d.user:null;}catch(_){authUser=null;}
    if(authUser){writeLocal(LEARNER_NAME_KEY,authUser.name||'');writeLocal(LEARNER_EMPID_KEY,authUser.empId||'');}
    return authUser;
  }

  function renderPendingExams(rows,materialsPending=0,pendingCourses=[],materialsRetraining=0){
    const box=$('#v571-pending-exams');if(!box)return;const groups={grpBio:'生化組',grpMicro:'鏡檢組',grpSero:'血清組',grpBB:'血庫組',grpBact:'細菌組',grpHema:'血液組',grpNew:'新進醫檢師',grpPgyDocs:'PGY'};
    const courses=Array.isArray(pendingCourses)?pendingCourses.slice(0,3):[];
    const assignedIds=new Set(courses.map(x=>String(x?.id||'')));
    const list=(Array.isArray(rows)?rows:[]).filter(x=>!assignedIds.has(String(x?.courseId||''))).slice(0,3);
    const courseTasks=courses.map(x=>{const qs=new URLSearchParams({area:x.area||'internal',group:x.group||'grpBio',module:'materials',from:'home'});const due=x.dueAt?`${x.overdue?'已逾期':'期限'} ${String(x.dueAt).slice(0,10)}`:'正式指派';return `<a class="v56-assessment-row phase3-home-task-row" href="/system?${qs.toString()}"><span class="v56-assessment-badge ${x.overdue?'':'material'}">${x.overdue?'逾期':'必修'}</span><span><strong>${escapeHtml(x.title||'待完成課程')}</strong><span>${escapeHtml(due)} · 教材 ${Number(x.materialsCompleted||0)}/${Number(x.materialsTotal||0)}${x.examRequired?(x.examPassed?' · 考核已通過':' · 尚待考核'):''}</span></span><b aria-hidden="true">›</b></a>`;}).join('');
    const retrainingTask=Number(materialsRetraining||0)>0?`<a class="v56-assessment-row phase3-home-task-row" href="#groups"><span class="v56-assessment-badge">重訓</span><span><strong>${Number(materialsRetraining)} 份教材需要重新訓練</strong><span>教材或 SOP 已更新重大版本，請重新完成最新版</span></span><b aria-hidden="true">›</b></a>`:'';
    const ordinaryPending=Math.max(0,Number(materialsPending||0)-Number(materialsRetraining||0));
    const materialTask=!courses.length&&ordinaryPending>0?`<a class="v56-assessment-row phase3-home-task-row" href="#groups"><span class="v56-assessment-badge material">教材</span><span><strong>尚有 ${ordinaryPending} 份教材待完成</strong><span>前往學習中心繼續目前進度</span></span><b aria-hidden="true">›</b></a>`:'';
    const examTasks=list.map(x=>{
      const area=x.area==='pgy'?'PGY':'院內';
      const g=groups[x.group]||'';
      const examId=String(x.id||x.examId||x.quizId||'');

      const qs=new URLSearchParams({
        area:x.area||'internal',
        group:x.group||'grpBio',
        module:'exam',
        from:'home'
      });

      if(examId){
        qs.set('examId',examId);
      }

      const href=`/system?${qs.toString()}`;

      return `<a class="v56-assessment-row phase3-home-task-row" href="${href}"><span class="v56-assessment-badge">${area}考核</span><span><strong>${escapeHtml(x.title||'未命名考核')}</strong><span>${escapeHtml(g)} · 及格 ${Number(x.passingScore||80)} 分</span></span><b aria-hidden="true">›</b></a>`;
    }).join('');
    box.innerHTML=retrainingTask||courseTasks||materialTask||examTasks?retrainingTask+courseTasks+materialTask+examTasks:'<div class="v56-empty">目前沒有待辦，今天可以依自己的節奏繼續學習。</div>';
  }

  function resetPersonalDashboard(){
    setText('#v561-course-count','—'); setText('#v561-exam-pending','—'); setText('#v561-progress-percent','—');
    setText('#v681-home-todo-count','—');setText('#v681-home-materials-pending','—');setText('#v681-home-exams-pending','—');
    const bar=$('#v561-progress-bar'); if(bar)bar.style.width='0%';renderPendingExams([],0,[],0);
  }

  function setupProfileDialog(){
    const dialog=$('#v561-profile-dialog'), trigger=$('#v561-profile-trigger'), form=$('#v561-profile-form');
    const name=$('#v561-profile-name'), emp=$('#v561-profile-empid'), status=$('#v561-profile-status'), clear=$('#v561-profile-clear'), close=$('#v561-profile-close'), cancel=$('#v561-profile-cancel');
    if(!dialog||!trigger||!form)return;
    const shut=()=>{try{dialog.close();}catch(_){dialog.removeAttribute('open');}};
    const open=()=>{if(!authUser){location.href='/login?next=%2F';return;}if(name){name.value=authUser.name||'';name.readOnly=true;}if(emp){emp.value=authUser.empId||'';emp.readOnly=true;}if(status)status.textContent=`已登入 ${authUser.username}；個人資料由管理者維護。`;if(typeof dialog.showModal==='function'&&!dialog.open)dialog.showModal();else dialog.setAttribute('open','');};
    trigger.addEventListener('click',open);
    trigger.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
    close?.addEventListener('click',shut); cancel?.addEventListener('click',shut);
    dialog.addEventListener('click',e=>{if(e.target===dialog)shut();});
    form.addEventListener('submit',e=>{e.preventDefault();shut();});
    clear?.addEventListener('click',async()=>{await fetch('/api/auth/logout',{method:'POST'}).catch(()=>{});authUser=null;clearHomeCache();writeLocal(LEARNER_NAME_KEY,'');writeLocal(LEARNER_EMPID_KEY,'');shut();location.href='/';});
  }

  function setupProgressEntry(){
    const links=$$('[data-home-progress-link]');
    links.forEach(link=>link.addEventListener('click',async event=>{
      if(authUser)return;
      event.preventDefault();
      const href=link.getAttribute('href')||'/';
      const user=await loadAuthState();
      if(user){location.href=href;return;}
      location.href=`/login?next=${encodeURIComponent(href)}`;
    }));
  }

  async function loadAnnouncements(){
    const dialog=$('#v571-announcement-dialog'), list=$('#v571-announcement-list'), count=$('#v571-announcement-count');
    const strip=$('#v681-announcement-strip'), stripTitle=$('#v681-announcement-title'), stripMeta=$('#v681-announcement-meta');
    const openBtns=[$('#v571-notice-trigger'),$('#v571-announcement-open'),$('#v573-nav-announcement'),$('#v681-announcement-open')].filter(Boolean), close=$('#v571-announcement-close');
    if(!dialog||!list)return;
    const shut=()=>{try{dialog.close();}catch(_){dialog.removeAttribute('open');}};
    const open=()=>{if(typeof dialog.showModal==='function'&&!dialog.open)dialog.showModal();else dialog.setAttribute('open','');};
    openBtns.forEach(b=>b.addEventListener('click',open)); close?.addEventListener('click',shut); dialog.addEventListener('click',e=>{if(e.target===dialog)shut();});
    try{
      const data=await fetchJSONCached(
        '/api/announcements?limit=8',
        HOME_CACHE_TTL
      );
      const rows=Array.isArray(data)?data:[]; if(count)count.textContent=String(rows.length);
      const dot=$('.v56-dot'); if(dot)dot.style.display=rows.length?'block':'none';
      if(strip){strip.hidden=!rows.length;if(rows.length){const latest=rows[0]||{};if(stripTitle)stripTitle.textContent=latest.title||'平台公告';if(stripMeta)stripMeta.textContent=fmtDate(latest.publishedAt||latest.createdAt||'');}}
      list.innerHTML=rows.length?rows.map(a=>`<article class="v571-announcement-item"><h4>${escapeHtml(a.title||'平台公告')}</h4>${a.body?`<p>${escapeHtml(a.body)}</p>`:''}<time>${fmtDate(a.publishedAt||a.createdAt||'')}</time></article>`).join(''):'<div class="v571-announcement-empty">目前沒有新的公告。</div>';
    }catch(err){if(count)count.textContent='0';if(strip)strip.hidden=true;list.innerHTML=`<div class="v571-announcement-empty">公告暫時無法讀取：${escapeHtml(err.message)}</div>`;}
  }

  async function loadPersonalDashboard(){
    const empId=authUser?.empId||'', name=authUser?.name||'', welcome=$('#v561-welcome');
    if(!authUser){resetPersonalDashboard();setText('#v561-header-name','登入學習帳號');setText('#v561-header-id','登入後讀取個人進度');if(welcome)welcome.textContent='尚未登入｜登入後自動顯示你的課程、考核與學習進度';return;}
    setText('#v561-header-name',name||'讀取個人資料中…');setText('#v561-header-id',`工號 ${empId}`);if(welcome)welcome.textContent='正在讀取你的學習紀錄…';
    try{
      const qs=new URLSearchParams({empId}); if(name)qs.set('name',name);
      const d=await fetchJSONCached(
        `/api/dashboard/me?${qs.toString()}`,
        HOME_PERSONAL_TTL
      );
      if(d.name){writeLocal(LEARNER_NAME_KEY,d.name);setText('#v561-header-name',d.name);}else setText('#v561-header-name',name||'學習者');
      setText('#v561-header-id',`工號 ${d.empId||empId}`);
      setText('#v561-course-count',Number(d.activeCourses||0));
      setText('#v561-exam-pending',Number(d.examsPending||0));
      const materialsPending=Math.max(0,Number(d.materialsPending||0));
      const materialsRetraining=Math.max(0,Number(d.materialsRetraining||0));
      const examsPending=Math.max(0,Number(d.examsPending||0));
      const pendingCourses=Array.isArray(d.pendingCourses)?d.pendingCourses:[];
      const pendingCourseIds=new Set(pendingCourses.map(x=>String(x?.id||'')));
      const standaloneExams=(Array.isArray(d.pendingExams)?d.pendingExams:[]).filter(x=>!pendingCourseIds.has(String(x?.courseId||''))).length;
      const todoCount=d?.scopeSource==='assignments'?pendingCourses.length+standaloneExams:materialsPending+examsPending;
      setText('#v681-home-materials-pending',materialsPending);setText('#v681-home-exams-pending',examsPending);setText('#v681-home-todo-count',todoCount);
      renderPendingExams(d.pendingExams||[],materialsPending,pendingCourses,materialsRetraining);
      const pct=Math.max(0,Math.min(100,Number(d.progressPercent||0)));setText('#v561-progress-percent',pct);const bar=$('#v561-progress-bar');if(bar)bar.style.width=`${pct}%`;
      if(welcome)welcome.textContent=d?.scopeSource==='assignments'
        ? `早安，${d.name||name||'同仁'}｜正式指派 ${Number(d.requiredAssignments||0)} 門必修・待完成 ${pendingCourses.length} 門${Number(d.overdueAssignments||0)?`・逾期 ${Number(d.overdueAssignments)} 門`:''}・整體進度 ${pct}%`
        : `早安，${d.name||name||'同仁'}｜教材完成 ${Number(d.materialsCompleted||0)}/${Number(d.materialsTotal||0)}・考核通過 ${Number(d.examsPassed||0)}/${Number(d.examsTotal||0)}・教師評核 ${Number(d.teacherAssessmentsCompleted||0)} 次${Number(d.essayReviewsPending||0)?`・待人工批改 ${Number(d.essayReviewsPending)} 份`:''}`;
    }catch(err){resetPersonalDashboard();if(welcome)welcome.textContent=`個人紀錄暫時無法讀取：${err.message}`;}
  }

  async function loadDashboard(){
    const list=$('#v56-latest-materials'); if(!list)return;
    if(!authUser){list.innerHTML='<div class="v56-empty">登入後顯示最新教材與個人可用資源。</div>';return;}
    try{
      const [internalSlides,pgySlides]=await Promise.all([
        fetchJSONCached(
          '/api/slides?area=internal',
          HOME_SLIDES_TTL
        ),
        fetchJSONCached(
          '/api/slides?area=pgy',
          HOME_SLIDES_TTL
        )
      ]);

      const all=[
        ...(Array.isArray(internalSlides)?internalSlides:[]),
        ...(Array.isArray(pgySlides)?pgySlides:[])
      ].filter(x=>x&&x.active!==false);
      all.sort((x,y)=>String(y.dateAdded||y.date_added||y.uploadedAt||y.createdAt||'').localeCompare(String(x.dateAdded||x.date_added||x.uploadedAt||x.createdAt||'')));
      const latest=all.slice(0,4);
      if(!latest.length){list.innerHTML='<div class="v56-empty">尚無公開教材。管理者新增教材後，這裡會自動顯示最新項目。</div>';return;}
      list.innerHTML=latest.map(m=>{const [label,cls]=typeOf(m);const area=m.area==='pgy'?'PGY':'院內';const group={grpBio:'生化組',grpMicro:'鏡檢組',grpSero:'血清組',grpBB:'血庫組',grpBact:'細菌組',grpHema:'血液組',grpNew:'新進專區',grpPgyDocs:'PGY資料區'}[m.group]||'';const href=`/system?area=${encodeURIComponent(m.area||'internal')}&group=${encodeURIComponent(m.group||'grpBio')}&module=materials&from=home`;return `<a class="v56-list-row" href="${href}"><span class="v56-file-pill ${cls}">${label}</span><span class="v56-list-title"><strong>${escapeHtml(m.title||m.filename||'未命名教材')}</strong><span>${area}${group?' · '+group:''}${fmtDate(m.dateAdded||m.date_added||m.uploadedAt||m.createdAt)?' · '+fmtDate(m.dateAdded||m.date_added||m.uploadedAt||m.createdAt):''}</span></span><b>›</b></a>`;}).join('');
    }catch(err){list.innerHTML='<div class="v56-empty">教材摘要暫時無法讀取，仍可直接進入各組學習。</div>';}
  }
  function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  setupPhase3AreaSwitch();
  setupProfileDialog();
  setupProgressEntry();

  // Non-blocking data begins immediately instead of waiting for auth.
  loadAnnouncements();

  Promise.all([
    fetchJSONCached(
      '/api/slides?area=internal',
      HOME_SLIDES_TTL
    ),
    fetchJSONCached(
      '/api/slides?area=pgy',
      HOME_SLIDES_TTL
    )
  ]).catch(()=>{});

  (async()=>{
    await loadAuthState();

    await Promise.all([
      loadPersonalDashboard(),
      loadDashboard()
    ]);
  })();
})();
