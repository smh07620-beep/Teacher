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
  const toggle=document.getElementById('forgot-password-toggle'),forgot=document.getElementById('forgot-password-form'),forgotStatus=document.getElementById('forgot-status');
  toggle?.addEventListener('click',()=>{forgot.hidden=!forgot.hidden;});
  forgot?.addEventListener('submit',async e=>{e.preventDefault();forgotStatus.textContent='處理中…';try{const d=await AppCore.api('/api/auth/forgot-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity:document.getElementById('forgot-identity').value})});forgotStatus.textContent=d.message||'若資料相符，系統將寄出重設信。';}catch(err){forgotStatus.textContent=err.message;}});
})();
