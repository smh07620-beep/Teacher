from pathlib import Path

p=Path('static/system-core.js')
s=p.read_text(encoding='utf-8')
old="    set('v573-system-user-name',display);set('v573-system-user-id',empId?`工號 ${empId}`:'請回首頁設定');"
new="    set('v573-system-user-name',display);const identityMeta=document.getElementById('v573-system-user-id');if(identityMeta&&identityMeta.dataset.profileHydrated!=='1'&&identityMeta.textContent!=='載入身分…')identityMeta.textContent='載入身分…';"
assert s.count(old)==1
p.write_text(s.replace(old,new,1),encoding='utf-8')

p=Path('static/training-command-center-71.js')
s=p.read_text(encoding='utf-8')
old="      meta.textContent = [title, emp ? `工號 ${emp}` : ''].filter(Boolean).join(' · ');"
new="      meta.textContent = [title, emp ? `工號 ${emp}` : ''].filter(Boolean).join(' · ');\n      meta.dataset.profileHydrated = '1';"
assert s.count(old)==1
p.write_text(s.replace(old,new,1),encoding='utf-8')
