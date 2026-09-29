/* V5.9.0 · 登入與安全導向 */
(function(){
  const form=document.getElementById('login-form'),status=document.getElementById('login-status'),button=form.querySelector('button[type="submit"]');
  const rawNext=new URLSearchParams(location.search).get('next')||'/';
  const next=rawNext.startsWith('/')&&!rawNext.startsWith('//')?rawNext:'/';
  form.addEventListener('submit',async e=>{e.preventDefault();status.textContent='正在登入…';status.className='loading';button.disabled=true;
    try{const d=await AppCore.api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('login-username').value,password:document.getElementById('login-password').value})});
      try{localStorage.setItem('smh_learner_name',d.user.name||'');localStorage.setItem('smh_learner_empid',d.user.empId||'');}catch(_){}
      status.textContent=`登入成功，歡迎 ${d.user.name}。`;status.className='success';location.href=next;
    }catch(err){status.textContent=err.message;status.className='error';button.disabled=false;document.getElementById('login-password').select();}
  });

  const toggle=document.getElementById('forgot-password-toggle');
  const forgot=document.getElementById('forgot-password-form');
  const forgotStatus=document.getElementById('forgot-status');
  const forgotIdentity=document.getElementById('forgot-identity');

  function setForgotOpen(open){
    if(!forgot||!toggle)return;
    const expanded=Boolean(open);
    forgot.hidden=!expanded;
    if(expanded){
      forgot.style.removeProperty('display');
      toggle.textContent='收起忘記密碼';
      forgotIdentity?.focus();
    }else{
      forgot.style.setProperty('display','none','important');
      toggle.textContent='忘記密碼？';
      if(forgotStatus)forgotStatus.textContent='';
    }
    toggle.setAttribute('aria-expanded',expanded?'true':'false');
    toggle.setAttribute('aria-controls','forgot-password-form');
  }

  // Some portal form rules use display:grid; force the reset form closed until
  // the user explicitly asks for it so Email/reset controls are never shown by default.
  setForgotOpen(false);
  toggle?.addEventListener('click',()=>setForgotOpen(forgot?.hidden));
  forgot?.addEventListener('submit',async e=>{e.preventDefault();forgotStatus.textContent='處理中…';try{const d=await AppCore.api('/api/auth/forgot-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity:forgotIdentity?.value||''})});forgotStatus.textContent=d.message||'若資料相符，系統將寄出重設信。';}catch(err){forgotStatus.textContent=err.message;}});
})();
