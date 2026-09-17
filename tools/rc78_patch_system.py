from pathlib import Path
import re

path=Path('static/system.html')
s=path.read_text(encoding='utf-8')
s,n=re.subn(r'\s*<section id="admin-quiz-guide"[\s\S]*?</section>\s*','\n',s,count=1)
assert n==1,n
new='''                    <section id="admin-quiz-workspace" class="bg-white border border-indigo-200 rounded-2xl p-5 shadow-sm space-y-4">
                        <div class="flex items-start justify-between gap-3 flex-wrap"><div><h4 class="font-black text-indigo-950 text-lg">📋 考卷管理</h4><p class="text-xs text-indigo-700 mt-1">清單只負責搜尋與開啟考卷；出題、AI、教材、設定與發布都在考卷內完成。</p></div><div class="flex items-center gap-2"><span id="admin-quiz-sync-status" class="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 text-slate-500 font-bold">待同步</span><details class="relative"><summary class="list-none cursor-pointer text-xs bg-white border border-slate-200 text-slate-600 px-3 py-2 rounded-lg font-bold">⋯</summary><div class="absolute right-0 mt-1 z-30 w-44 rounded-xl border border-slate-200 bg-white p-2 shadow-xl"><button type="button" onclick="renderAdminQuizCategories(true)" class="w-full text-left text-xs hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">↻ 重新同步</button></div></details></div></div>
                        <details id="admin-quiz-scope-78" class="rounded-xl border border-slate-200 bg-slate-50/60"><summary class="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-600">目前範圍 · 需要時切換訓練區／組別</summary><div class="grid md:grid-cols-2 gap-3 border-t border-slate-200 p-3"><div><label class="block text-xs font-bold text-slate-600 mb-1">訓練區</label><select id="admin-quiz-area" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm"><option value="internal">內部教育訓練區</option><option value="pgy">PGY訓練區</option></select></div><div><label class="block text-xs font-bold text-slate-600 mb-1">組別</label><select id="admin-quiz-group" onchange="onAdminQuizGroupChange()" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"></select></div></div></details>
                        <div data-teacher78-canonical-create-executor class="hidden" aria-hidden="true"><input id="admin-new-category-title" type="text" maxlength="255"><button type="button" onclick="adminCreateQuizCategory()">建立</button></div>
                        <div id="admin-quiz-categories-list" class="space-y-3"></div>
                    </section>'''
start=s.index('<section id="admin-quiz-workspace"')
list_pos=s.index('<div id="admin-quiz-categories-list"',start)
end=s.index('</section>',list_pos)+len('</section>')
s=s[:start]+new+s[end:]
s=s.replace('<small id="v573-system-user-id">請回首頁設定</small>','<small id="v573-system-user-id" aria-live="polite">載入身分…</small>',1)
path.write_text(s,encoding='utf-8')
