/* V5.9.0 · 教材、課程、進度與閱讀器 */
const slideCategoryLabels = {
    subA1: '1-1 一致性與法定傳染病通報',
    subA2: '1-2 c503一般作業流程與異常訊號故障排除',
    subA3: '1-3 Cobas b 211異常訊號故障排除與QC設定',
    zoneB: '2 COVER C1人員考區（Sebia）',
    '': '未分類 / 一般補充教材'
};

let cachedSlidesList = []; // 最近一次從後端取得的簡報清單快取，供開啟檢視器使用
let cachedCourses = [];
let cachedQuizCategories = [];
let myCompletedMaterials = {};

function formatFileSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildSlideCardHTML(s) {
    const catLabel = s.categoryLabel || slideCategoryLabels[s.category] || slideCategoryLabels[''];
    const groupKey = s.group || 'grpBio';
    const jumpBtn = s.category
        ? `<button onclick="goToExamModule('${s.category}', '${groupKey}')" class="flex-1 text-xs font-semibold bg-teal-600 hover:bg-teal-500 text-white py-2 rounded-lg transition-colors flex items-center justify-center gap-1">📝 前往對應考題作答</button>`
        : `<span class="flex-1 text-xs text-slate-400 flex items-center justify-center">未連結考題模組</span>`;
    const openBtn = `<button onclick="openMaterial('${s.id}')" class="flex-1 text-xs font-bold bg-[#006b64] hover:bg-[#005a54] text-white py-2.5 rounded-lg transition-colors flex items-center justify-center gap-1">📖 開始閱讀</button>`;
    const deleteBtn = s.isBuiltin
        ? ''
        : `<button onclick="deleteUploadedSlide('${s.id}')" class="text-xs font-semibold text-rose-600 hover:text-rose-800 px-2 py-1 rounded-lg transition-colors">🗑️ 刪除</button>`;
    const badge = s.materialType==='sop' ? `<span class="text-xs font-semibold px-2 py-0.5 bg-sky-100 text-sky-800 rounded whitespace-nowrap">📑 SOP・站內閱讀</span>` : s.materialType==='troubleshooting' ? `<span class="text-xs font-semibold px-2 py-0.5 bg-amber-100 text-amber-800 rounded whitespace-nowrap">🧰 Troubleshooting</span>` : s.materialType==='case' ? `<span class="text-xs font-semibold px-2 py-0.5 bg-rose-100 text-rose-800 rounded whitespace-nowrap">🩸 案例分析</span>` : s.materialType==='infographic' ? `<span class="text-xs font-semibold px-2 py-0.5 bg-violet-100 text-violet-700 rounded whitespace-nowrap">📊 資訊圖表</span>` : (s.isBuiltin ? `<span class="text-xs font-semibold px-2 py-0.5 bg-slate-100 text-slate-600 rounded whitespace-nowrap">內建教材</span>` : `<span class="text-xs font-semibold px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded whitespace-nowrap">自行上傳</span>`);
    const pageLabel = s.pageCount ? `<span class="text-slate-400">共 ${s.pageCount} 頁</span>` : '';
    const dateLabel = s.dateAdded ? `<span class="text-slate-400">上傳於 ${s.dateAdded}</span>` : '';
    const courseLabel = s.courseTitle ? `<span class="px-2 py-0.5 bg-violet-50 text-violet-700 rounded-full font-medium">課程：${escapeHtml(s.courseTitle)}</span>` : '';
    const done = !!myCompletedMaterials[s.id];
    const completeBtn = s.isBuiltin ? '' : `<button onclick="markMaterialComplete('${s.id}')" class="w-full mt-2 text-xs font-semibold ${done?'bg-emerald-100 text-emerald-800 border-emerald-200':'bg-white text-emerald-700 border-emerald-300'} border py-2 rounded-lg">${done?'✅ 已完成教材':'☑️ 標記教材完成'}</button>`;

    return `
        <div class="slide-card lesson-card micro-card p-5 sm:p-6 ${s.materialType==='infographic'?'infographic-card':s.materialType==='sop'?'sop-card':s.materialType==='troubleshooting'?'troubleshoot-card':s.materialType==='case'?'case-card':''}">
            <div class="flex items-start justify-between gap-2">
                <span class="text-2xl">${s.viewerMode==='video'?'🎬':s.viewerMode==='audio'?'🎧':s.viewerMode==='image'?'🖼️':s.viewerMode==='slides'?'📊':'📎'}</span>
                ${badge}
            </div>
            <div><p class="edu-kicker">LEARNING MATERIAL</p><h4 class="text-base font-black text-slate-900 break-all leading-snug mt-1">${s.title}</h4></div>
            <p class="text-xs text-slate-500 flex-grow">${s.desc || ''}</p>
            <div class="flex flex-wrap items-center gap-1.5 text-xs">
                <span class="px-2 py-0.5 bg-teal-50 text-teal-700 rounded-full font-medium">${catLabel}</span>
                ${pageLabel}
                ${dateLabel}
                ${courseLabel}
            </div>
            <div class="flex gap-2 pt-1">
                ${openBtn}
                ${jumpBtn}
            </div>
            ${completeBtn}
            ${deleteBtn ? `<div class="text-right">${deleteBtn}</div>` : ''}
        </div>
    `;
}


function isAtlasMaterial(m){return m.materialType==='atlas'||(m.materialType!=='infographic'&&m.viewerMode==='image'&&currentGroupKey==='grpMicro');}
function buildAtlasCardHTML(m){const src=m.viewUrl||`/view/${encodeURIComponent(m.id)}`;const meta=m.atlasMeta||{};const chips=[meta.category,meta.magnification,meta.normality].filter(Boolean).map(x=>`<span class="atlas-chip">${escapeHtml(x)}</span>`).join('');const tagchips=(meta.tags||'').split(',').map(x=>x.trim()).filter(Boolean).slice(0,5).map(x=>`<span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">#${escapeHtml(x)}</span>`).join('');return `<article class="atlas-card micro-card"><button onclick="openAtlas('${m.id}')" class="atlas-preview w-full text-left"><img src="${src}" loading="lazy" decoding="async" alt="${escapeHtml(m.title||'Atlas 圖譜')}"><span class="absolute right-2 bottom-2 px-2 py-1 rounded-lg bg-black/65 text-white text-[11px] font-bold">🔍 點擊放大</span></button><div class="p-4"><div class="flex items-center gap-2 flex-wrap"><span class="atlas-chip">Atlas</span>${chips}${tagchips}<span class="text-[11px] text-slate-400">高解析原圖</span></div><h4 class="font-black text-slate-900 mt-2">${escapeHtml(m.title||m.filename)}</h4><p class="text-xs text-slate-500 mt-1 leading-5">${escapeHtml(meta.interpretation||m.desc||'適合鏡檢照片、結晶、細胞型態與微生物圖像判讀。')}</p><button onclick="openAtlas('${m.id}')" class="micro-btn mt-3 w-full bg-[#006b64] text-white rounded-lg py-2 text-xs font-bold">🔬 檢視細節</button></div></article>`;}
let atlasState={entry:null,zoom:1};
function openAtlas(id){const m=cachedSlidesList.find(x=>x.id===id);if(!m)return;atlasState={entry:m,zoom:1};const img=document.getElementById('atlas-modal-image');img.src=m.viewUrl||`/view/${encodeURIComponent(m.id)}`;document.getElementById('atlas-modal-title').textContent=m.title||m.filename||'Atlas 圖譜';const meta=m.atlasMeta||{};const lines=[meta.category?`分類：${meta.category}`:'',meta.magnification?`倍率 / 染色：${meta.magnification}`:'',meta.interpretation?`判讀重點：${meta.interpretation}`:(m.desc||''),meta.clinical?`臨床意義：${meta.clinical}`:'',meta.differential?`鑑別重點：${meta.differential}`:'',meta.normality?`標記：${meta.normality}`:'',meta.tags?`標籤：${meta.tags}`:''].filter(Boolean);document.getElementById('atlas-modal-desc').textContent=lines.join('　｜　')||'滑鼠移動可改變放大中心；使用 +/- 調整倍率。';const modal=document.getElementById('atlas-modal');modal.classList.remove('hidden');modal.classList.add('flex');document.body.style.overflow='hidden';atlasReset();}
function applyAtlasZoom(){const z=Math.max(.5,Math.min(5,atlasState.zoom||1));atlasState.zoom=z;const img=document.getElementById('atlas-modal-image');img.style.transform=`scale(${z})`;document.getElementById('atlas-zoom-text').textContent=`${Math.round(z*100)}%`;}
function atlasZoom(d){atlasState.zoom=(atlasState.zoom||1)+d;applyAtlasZoom();}
function atlasReset(){atlasState.zoom=1;const img=document.getElementById('atlas-modal-image');img.style.transformOrigin='center';applyAtlasZoom();const st=document.getElementById('atlas-stage');if(st)st.scrollTo({top:0,left:0});}
function atlasPointerMove(ev){if((atlasState.zoom||1)<=1)return;const r=ev.currentTarget.getBoundingClientRect();const x=Math.max(0,Math.min(100,(ev.clientX-r.left)/r.width*100));const y=Math.max(0,Math.min(100,(ev.clientY-r.top)/r.height*100));document.getElementById('atlas-modal-image').style.transformOrigin=`${x}% ${y}%`;}
async function toggleAtlasFullscreen(){const m=document.getElementById('atlas-modal');try{if(!document.fullscreenElement)await m.requestFullscreen?.();else await document.exitFullscreen?.();}catch(_){}}
function closeAtlas(){const m=document.getElementById('atlas-modal');m.classList.add('hidden');m.classList.remove('flex');document.body.style.overflow='';if(document.fullscreenElement)document.exitFullscreen?.();}

async function renderSlidesGrid() {
    const grid = document.getElementById('slides-grid');
    if (!grid) return;
    grid.innerHTML = `<p class="text-xs text-slate-400 col-span-full text-center py-6">載入教材清單中…</p>`;
    try {
        const [res, courseRes, quizRes] = await Promise.all([fetch(`/api/slides?area=${encodeURIComponent(currentTrainingArea)}`), fetch(`/api/courses?area=${encodeURIComponent(currentTrainingArea)}&group=${encodeURIComponent(currentGroupKey)}`), fetch(`/api/quiz-categories?group=${encodeURIComponent(currentGroupKey)}&area=${encodeURIComponent(currentTrainingArea)}`)]);
        if (!res.ok) throw new Error('無法取得教材清單');
        cachedCourses = courseRes.ok ? await courseRes.json() : [];
        cachedQuizCategories = quizRes.ok ? await quizRes.json() : [];
        dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`] = cachedQuizCategories;
        const courseMap = Object.fromEntries(cachedCourses.map(c => [c.id, c.title]));
        cachedSlidesList = (await res.json()).map(x => ({...x, courseTitle: courseMap[x.courseId] || ''}));
        const allInGroup = cachedSlidesList.filter(s => (s.group || 'grpBio') === currentGroupKey);
        const atlasAll=allInGroup.filter(isAtlasMaterial);
        let standard=[]; let atlas=[];
        if(currentMaterialView==='atlas'){
            atlas=atlasAll;
        } else if(currentMaterialView==='media'){
            standard=allInGroup.filter(m=>!isAtlasMaterial(m)&&(m.materialType==='video'||['video','audio'].includes(m.viewerMode||'')));
        } else if(currentMaterialView==='troubleshooting'){
            standard=allInGroup.filter(m=>['troubleshooting','case'].includes(m.materialType||''));
        } else if(currentMaterialView==='sop'){
            standard=allInGroup.filter(m=>m.materialType==='sop');
        } else {
            standard=allInGroup.filter(m=>!isAtlasMaterial(m)&&!['video','troubleshooting','case','sop'].includes(m.materialType||'')&&!['video','audio'].includes(m.viewerMode||''));
        }
        const courseOverview=document.getElementById('course-overview');
        if(currentMaterialView==='materials'){renderCourseOverview();}
        else if(courseOverview) courseOverview.classList.add('hidden');
        const atlasSection=document.getElementById('atlas-section'),atlasGrid=document.getElementById('atlas-grid'),atlasCount=document.getElementById('atlas-count');
        if(atlasSection&&atlasGrid){
            const showAtlas=currentMaterialView==='atlas';
            atlasSection.classList.toggle('hidden',!showAtlas);
            atlasGrid.innerHTML=atlas.length?atlas.map(buildAtlasCardHTML).join(''):`<div class="sm:col-span-2 xl:col-span-3 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-400">目前尚無 Atlas 高畫質圖譜，請由管理者後台上傳。</div>`;
            if(atlasCount)atlasCount.textContent=`${atlas.length} 張`;
        }
        const emptyText=currentMaterialView==='media'?'目前尚無操作教學影片／影音教材。':(currentMaterialView==='troubleshooting'?'目前尚無常見錯誤分析或案例教材。':(currentMaterialView==='sop'?'目前尚無 SOP；可由管理者後台上傳，學員端僅提供站內閱讀。':'本區尚未上傳任何核心課程教材，請由管理者後台新增。'));
        const hideFlatGrid=currentMaterialView==='atlas'||currentMaterialView==='materials';
        grid.classList.toggle('hidden',hideFlatGrid);
        if(currentMaterialView==='materials') grid.innerHTML='';
        else grid.innerHTML = standard.length ? standard.map(buildSlideCardHTML).join('') : `<p class="text-xs text-slate-400 col-span-full text-center py-8 bg-white border border-dashed border-slate-300 rounded-2xl">${emptyText}</p>`;
    } catch (err) {
        console.error(err);
        grid.innerHTML = `<p class="text-xs text-rose-500 col-span-full text-center py-6">❌ 讀取教材清單失敗，請確認後端伺服器 (Flask) 是否已啟動。</p>`;
    }
}

// --- 教材檢視器：V5.7.0 單一 preview.pdf + Range/Fast Web View；舊教材保留逐頁圖片相容 ---
let slideViewerState = { images: [], previewUrl: '', pageCount: 0, mode: 'images', index: 0, title: '', zoom: 1, materialId: '' };

function openMaterial(id) {
    const e = cachedSlidesList.find(s => s.id === id);
    if (!e) return;
    if (e.viewerMode === 'preview_pdf') {
        if (!e.previewUrl) return alert('此教材的單一預覽檔尚未建立，請聯絡管理者重新轉檔。');
        openPdfPreview(e); return;
    }
    if (e.viewerMode && e.viewerMode !== "slides") {
        if (!e.viewUrl) return alert('此教材暫時無法開啟。');
        openMediaViewer(e);
        return;
    }
    openSlide(id);
}

function openMediaViewer(entry){
    const modal=document.getElementById('media-viewer-modal');
    const video=document.getElementById('media-video');
    const audio=document.getElementById('media-audio');
    const image=document.getElementById('media-image');
    const audioWrap=document.getElementById('media-audio-wrap');
    [video,image,audioWrap].forEach(x=>x.classList.add('hidden'));
    video.pause(); audio.pause(); video.removeAttribute('src'); audio.removeAttribute('src'); image.removeAttribute('src');
    document.getElementById('media-viewer-title').textContent=entry.title||'多媒體教材';
    const vol=document.getElementById('media-volume-controls');
    if(entry.viewerMode==='video'){video.src=entry.viewUrl;video.classList.remove('hidden');vol?.classList.remove('hidden');}
    else if(entry.viewerMode==='audio'){audio.src=entry.viewUrl;audioWrap.classList.remove('hidden');vol?.classList.remove('hidden');}
    else if(entry.viewerMode==='image'){image.src=entry.viewUrl;image.classList.remove('hidden');vol?.classList.add('hidden');}
    else { window.open(entry.viewUrl,'_blank','noopener'); return; }
    setMediaSize('md'); setMediaVolume(1);
    modal.classList.remove('hidden'); modal.classList.add('flex'); document.body.style.overflow='hidden';
}
function setMediaSize(size){const f=document.getElementById('media-frame');f.classList.remove('size-sm','size-lg');if(size==='sm')f.classList.add('size-sm');if(size==='lg')f.classList.add('size-lg');}
function setMediaVolume(value){const v=Math.max(0,Math.min(1,Number(value)));const video=document.getElementById('media-video');const audio=document.getElementById('media-audio');video.volume=v;audio.volume=v;const range=document.getElementById('media-volume');if(range)range.value=v;const t=document.getElementById('media-volume-text');if(t)t.textContent=`${Math.round(v*100)}%`;}
function setMediaRate(value){const r=Math.max(.5,Math.min(2,Number(value)||1));document.getElementById('media-video').playbackRate=r;document.getElementById('media-audio').playbackRate=r;}
async function toggleMediaFullscreen(){const shell=document.getElementById('media-viewer-shell');try{if(!document.fullscreenElement)await shell.requestFullscreen?.();else await document.exitFullscreen?.();}catch(_){}}
function closeMediaViewer(){const modal=document.getElementById('media-viewer-modal');document.getElementById('media-video').pause();document.getElementById('media-audio').pause();modal.classList.add('hidden');modal.classList.remove('flex');document.body.style.overflow='';if(document.fullscreenElement)document.exitFullscreen?.();}

function openSlide(id) {
    const entry = cachedSlidesList.find(s => s.id === id);
    if (!entry) { alert('找不到該份簡報，可能已被刪除，請重新整理頁面。'); return; }
    const images = [];
    for (let i = 1; i <= entry.pageCount; i++) {
        const fmt=(entry.slideFormat||entry.storageMeta?.slideFormat||'png').toLowerCase(); images.push(`${entry.imageFolder}/slide-${String(i).padStart(2, '0')}.${fmt}`);
    }
    if (!images.length) { alert("此教材尚無可閱讀頁面，請聯絡教師確認轉檔狀態。"); return; }
    openSlideViewer({ images, title: entry.title, materialId: id });
}

function openPdfPreview(entry) {
    openSlideViewer({ previewUrl: entry.previewUrl, pageCount: Number(entry.pageCount||entry.storageMeta?.pageCount||1), title: entry.title, materialId: entry.id });
}

function openSlideViewer({ images = [], previewUrl = '', pageCount = 0, title, materialId = "" }) {
    const mode = previewUrl ? 'pdf' : 'images';
    const total = mode === 'pdf' ? Math.max(1, Number(pageCount||1)) : images.length;
    slideViewerState = { images, previewUrl, pageCount: total, mode, index: teachingReadPage(materialId, total), title, zoom: 1, materialId };
    document.getElementById('slide-viewer-title').textContent = title;
    const shell=document.getElementById('slide-viewer-shell'), canvas=document.getElementById('slide-viewer-canvas'), pdf=document.getElementById('slide-viewer-pdf');
    const subtitle=document.getElementById('slide-viewer-subtitle');
    shell?.classList.toggle('single-preview-mode', mode==='pdf');
    canvas?.classList.toggle('hidden', mode==='pdf');
    pdf?.classList.toggle('hidden', mode!=='pdf');
    document.querySelectorAll('[data-slide-image-tool]').forEach(el=>el.classList.toggle('hidden',mode==='pdf'));
    if(subtitle) subtitle.textContent=mode==='pdf'?'教學專用・不得轉發、轉載、販售｜單一預覽檔・原始教材不提供下載':'教學專用・不得轉發、轉載、販售｜原始教材不提供下載';
    renderSlideThumbs();
    if(mode==='pdf') updateSlideViewerPdf(); else updateSlideViewerImage();
    document.getElementById('slide-viewer-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    initSlidePan(); updateSlidePanState();
}

function applySlideZoom() {
    if(slideViewerState.mode==='pdf') return;
    const img = document.getElementById('slide-viewer-image');
    const zoom = Math.max(0.7, Math.min(2.5, slideViewerState.zoom || 1));
    slideViewerState.zoom = zoom;
    if (Math.abs(zoom - 1) < 0.01) {
        img.style.width = 'auto'; img.style.maxWidth = '100%';
        img.style.maxHeight = 'calc(100dvh - 145px)';
    } else {
        img.style.width = `${Math.round(zoom * 100)}%`; img.style.maxWidth = 'none'; img.style.maxHeight = 'none';
    }
    document.getElementById('slide-viewer-zoom').textContent = `${Math.round(zoom * 100)}%`;
    updateSlidePanState();
}

function slideViewerZoom(delta) { if(slideViewerState.mode==='pdf')return; slideViewerState.zoom = (slideViewerState.zoom || 1) + delta; applySlideZoom(); updateSlidePanState(); }
function slideViewerResetZoom() { if(slideViewerState.mode==='pdf')return; slideViewerState.zoom = 1; applySlideZoom(); updateSlidePanState(); document.getElementById('slide-viewer-stage').scrollTo({top:0,left:0,behavior:'smooth'}); }

const slidePanState={active:false,startX:0,startY:0,scrollLeft:0,scrollTop:0,pointerId:null};
function updateSlidePanState(){
    const stage=document.getElementById('slide-viewer-stage'), hint=document.getElementById('slide-pan-hint');
    const enabled=slideViewerState.mode!=='pdf'&&(slideViewerState.zoom||1)>1.01; stage?.classList.toggle('slide-pan-enabled',enabled); hint?.classList.toggle('hidden',!enabled);
    if(!enabled){slidePanState.active=false;stage?.classList.remove('is-panning');}
}
function initSlidePan(){
    const stage=document.getElementById('slide-viewer-stage'); if(!stage||stage.dataset.panReady==='1')return; stage.dataset.panReady='1';
    stage.addEventListener('pointerdown',e=>{
        if(slideViewerState.mode==='pdf'||(slideViewerState.zoom||1)<=1.01||e.pointerType==='touch'||e.button!==0||e.target.closest('button'))return;
        slidePanState.active=true;slidePanState.pointerId=e.pointerId;slidePanState.startX=e.clientX;slidePanState.startY=e.clientY;slidePanState.scrollLeft=stage.scrollLeft;slidePanState.scrollTop=stage.scrollTop;
        stage.classList.add('is-panning');try{stage.setPointerCapture(e.pointerId)}catch(_e){};e.preventDefault();
    });
    stage.addEventListener('pointermove',e=>{if(!slidePanState.active||e.pointerId!==slidePanState.pointerId)return;stage.scrollLeft=slidePanState.scrollLeft-(e.clientX-slidePanState.startX);stage.scrollTop=slidePanState.scrollTop-(e.clientY-slidePanState.startY);e.preventDefault();});
    const end=e=>{if(!slidePanState.active)return;slidePanState.active=false;slidePanState.pointerId=null;stage.classList.remove('is-panning');};
    stage.addEventListener('pointerup',end);stage.addEventListener('pointercancel',end);stage.addEventListener('lostpointercapture',end);
}

async function toggleSlideFullscreen() {
    const shell = document.getElementById('slide-viewer-shell');
    try {
        if (!document.fullscreenElement) await shell.requestFullscreen?.();
        else await document.exitFullscreen?.();
    } catch (_) {}
}

function updateViewerNav(total){
    const index=slideViewerState.index;
    document.getElementById('slide-viewer-page-info').textContent = `第 ${index + 1} / ${total} 頁`;
    document.getElementById('slide-prev-btn').disabled = index === 0;
    document.getElementById('slide-next-btn').disabled = index === total - 1;
    document.getElementById('slide-prev-btn').classList.toggle('opacity-30', index === 0);
    document.getElementById('slide-next-btn').classList.toggle('opacity-30', index === total - 1);
    document.querySelectorAll('.slide-thumb-card,.slide-page-btn').forEach((btn, i) => btn.classList.toggle('active', i === index));
    const sideInfo = document.getElementById('slide-viewer-page-info-side'); if (sideInfo) sideInfo.textContent = `${index + 1} / ${total}`;
    const active = document.querySelectorAll('.slide-thumb-card,.slide-page-btn')[index];
    active?.scrollIntoView({behavior:'smooth',inline:'center',block:'nearest'});
}

function updateSlideViewerPdf(){
    const total=Math.max(1,Number(slideViewerState.pageCount||1));
    teachingSavePage();
    const frame=document.getElementById('slide-viewer-pdf');
    const page=slideViewerState.index+1;
    const base=slideViewerState.previewUrl;
    const wanted=`${base}#page=${page}&toolbar=0&navpanes=0&scrollbar=1&view=FitH`;
    if(frame.dataset.src!==wanted){frame.dataset.src=wanted;frame.src=wanted;}
    updateViewerNav(total);
    const hint=document.getElementById('reader-learning-context');
    if(hint&&!hint.textContent) hint.textContent='正在載入單一預覽檔…';
}

function updateSlideViewerImage() {
    if(slideViewerState.mode==='pdf') return updateSlideViewerPdf();
    const { images, index } = slideViewerState;
    teachingSavePage();
    if (!images.length) return;
    const img = document.getElementById('slide-viewer-image');
    img.onerror = () => { const hint=document.getElementById('reader-learning-context'); if(hint) hint.innerHTML='<span class="text-rose-700 font-bold">❌ 教材頁面載入失敗</span><span class="text-slate-500">請檢查網路／雲端儲存狀態後重試；目前閱讀進度不會被清除。</span>'; };
    img.onload = () => { applySlideZoom(); const hint=document.getElementById('reader-learning-context'); if(hint&&hint.textContent.includes('載入失敗')) hint.textContent='教材已恢復載入，可繼續閱讀。'; };
    img.src = images[index];
    updateViewerNav(images.length);
    document.getElementById('slide-viewer-stage').scrollTo({top:0,left:0});
}

function renderSlideThumbs() {
    const container = document.getElementById('slide-viewer-thumbs');
    if(slideViewerState.mode==='pdf'){
        const total=Math.max(1,Number(slideViewerState.pageCount||1));
        container.innerHTML=Array.from({length:total},(_,i)=>`<button class="slide-page-btn ${i===slideViewerState.index?'active':''}" onclick="goToSlidePage(${i})" aria-label="跳到第 ${i+1} 頁">${i+1}</button>`).join('');
        return;
    }
    container.innerHTML = slideViewerState.images.map((src, i) => `
        <button class="slide-thumb-card ${i===slideViewerState.index?'active':''}" onclick="goToSlidePage(${i})" aria-label="跳到第 ${i + 1} 頁">
            <img src="${src}" class="w-full aspect-video object-contain bg-white" alt="第 ${i + 1} 頁縮圖" loading="lazy">
            <span class="hidden md:block text-[10px] text-slate-500 text-center py-1 bg-white">第 ${i + 1} 頁</span>
        </button>`).join('');
}

function goToSlidePage(i) { const total=slideViewerState.mode==='pdf'?Number(slideViewerState.pageCount||0):slideViewerState.images.length; if (i < 0 || i >= total) return; slideViewerState.index = i; slideViewerState.zoom = 1; if(slideViewerState.mode==='pdf')updateSlideViewerPdf();else updateSlideViewerImage(); }
function slideViewerPrev() { goToSlidePage(slideViewerState.index - 1); }
function slideViewerNext() { goToSlidePage(slideViewerState.index + 1); }
function closeSlideViewer() { const pdf=document.getElementById('slide-viewer-pdf'); if(pdf){pdf.removeAttribute('src');pdf.dataset.src='';} document.getElementById('slide-viewer-modal').classList.add('hidden'); document.body.style.overflow = ''; if (document.fullscreenElement) document.exitFullscreen?.(); }

// 鍵盤左右鍵切換頁面、ESC 關閉
document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('slide-viewer-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    if (e.key === 'ArrowLeft') slideViewerPrev();
    else if (e.key === 'ArrowRight') slideViewerNext();
    else if (e.key === 'Escape') closeSlideViewer();
});
document.addEventListener('keydown',(e)=>{const m=document.getElementById('atlas-modal');if(!m||m.classList.contains('hidden'))return;if(e.key==='Escape')closeAtlas();else if(e.key==='+'||e.key==='=')atlasZoom(.25);else if(e.key==='-')atlasZoom(-.25);});

// 教材新增/刪除已移至管理者後台。

// --- 舊呼叫相容：V5.3.20 改由六大學習模組控制 ---
function switchMainPanel(panel) {
    if(panel==='exam') return switchLearningModule('exam');
    if(panel==='progress') return switchLearningModule('progress');
    return switchLearningModule('materials');
}

// 由簡報卡片或對照手冊點擊「前往對應考題作答」時呼叫
function goToExamModule(categoryKey, groupKey) {
    toggleSopModal(false);
    groupKey = groupKey || 'grpBio';
    if (groupKey !== currentGroupKey) switchGroup(groupKey);
    switchMainPanel('exam');
    switchDynamicCategory(categoryKey);
}


function courseMaterialMeta(m){
    const type=m.materialType||'standard', mode=m.viewerMode||'';
    if(type==='atlas') return {key:'atlas',icon:'🔬',label:'Atlas / 圖譜',tone:'text-teal-700 bg-teal-50'};
    if(type==='video'||['video','audio'].includes(mode)) return {key:'media',icon:mode==='audio'?'🎧':'🎬',label:'影音教材',tone:'text-indigo-700 bg-indigo-50'};
    if(type==='troubleshooting'||type==='case') return {key:'troubleshooting',icon:type==='case'?'🩸':'🧰',label:type==='case'?'案例分析':'Troubleshooting',tone:'text-amber-700 bg-amber-50'};
    if(type==='sop') return {key:'sop',icon:'📑',label:'SOP',tone:'text-sky-700 bg-sky-50'};
    if(type==='infographic') return {key:'materials',icon:'📊',label:'資訊圖表',tone:'text-violet-700 bg-violet-50'};
    return {key:'materials',icon:'📚',label:'核心教材',tone:'text-slate-700 bg-slate-100'};
}
function buildCourseMaterialRow(m){
    const meta=courseMaterialMeta(m), done=!!myCompletedMaterials[m.id];
    const detail=[m.pageCount?`${m.pageCount} 頁`:'',m.dateAdded?`上傳 ${m.dateAdded}`:''].filter(Boolean).join(' · ');
    return `<div class="course-material-row"><span class="course-type-icon">${meta.icon}</span><div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="font-bold text-sm text-slate-800 break-words">${escapeHtml(m.title||m.filename||'未命名教材')}</span><span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${meta.tone}">${escapeHtml(meta.label)}</span>${done?'<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">✓ 已完成</span>':''}</div><p class="text-[11px] text-slate-400 mt-1">${escapeHtml(detail||m.description||'')}</p></div><div class="course-row-actions flex items-center gap-2"><button onclick="openMaterial('${escapeHtml(m.id)}')" class="px-3 py-2 rounded-lg bg-[#006b64] hover:bg-[#005a54] text-white text-xs font-bold">${meta.key==='media'?'▶ 播放':'📖 閱讀'}</button>${m.isBuiltin?'':`<button onclick="markMaterialComplete('${escapeHtml(m.id)}')" class="px-3 py-2 rounded-lg border ${done?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'} text-xs font-bold">${done?'✓ 已完成':'完成標記'}</button>`}</div></div>`;
}
function buildCourseExamRow(q){
    const bank=examBankCount(q),actual=examActualCount(q),draft=hasExamDraft(q.id);
    return `<div class="course-material-row"><span class="course-type-icon">📝</span><div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="font-bold text-sm text-slate-800">${escapeHtml(q.title||'課後評量')}</span>${q.blindMode?'<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-900 text-white">導師盲測</span>':''}${draft?'<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">進行中</span>':''}</div><div class="flex flex-wrap gap-1.5 mt-1.5 text-[10px]"><span class="course-stat-chip">👤 ${escapeHtml(examAudienceLabel(q))}</span><span class="course-stat-chip">🧠 題庫 ${bank} 題</span><span class="course-stat-chip">📋 ${escapeHtml(examDrawLabel(q))}</span><span class="course-stat-chip">🎯 及格 ${Number(q.passingScore||80)} 分</span></div>${q.desc?`<p class="text-[11px] text-slate-400 mt-1">${escapeHtml(q.desc)}</p>`:''}</div><div class="course-row-actions"><button onclick="openCourseExam('${escapeHtml(q.id)}')" class="px-3 py-2 rounded-lg ${draft?'bg-amber-600 hover:bg-amber-500':'bg-indigo-600 hover:bg-indigo-500'} text-white text-xs font-bold">${draft?'繼續作答 →':'開始考核 →'}</button></div></div>`;
}
async function openCourseExam(catId){
    switchLearningModule('exam');
    const cacheKey=`${currentTrainingArea}:${currentGroupKey}`;
    if(!dynamicCategoriesCache[cacheKey]?.length) await renderDynamicExamTabs();
    await switchDynamicCategory(catId);
    document.getElementById('panel-exam')?.scrollIntoView({behavior:'smooth',block:'start'});
}
function renderCourseOverview() {
    const box=document.getElementById('course-overview'),grid=document.getElementById('course-overview-grid');if(!box||!grid)return;
    const groupMaterials=cachedSlidesList.filter(m=>(m.group||'grpBio')===currentGroupKey),quizzes=(cachedQuizCategories||[]).filter(q=>(q.group||currentGroupKey)===currentGroupKey&&(q.area||currentTrainingArea)===currentTrainingArea),courses=(cachedCourses||[]).filter(c=>(c.group||c.groupKey||currentGroupKey)===currentGroupKey);
    const orphanMaterials=groupMaterials.filter(m=>!m.courseId||!courses.some(c=>c.id===m.courseId)),orphanQuizzes=quizzes.filter(q=>!q.courseId||!courses.some(c=>c.id===q.courseId));if(!courses.length&&!orphanMaterials.length&&!orphanQuizzes.length){box.classList.add('hidden');grid.innerHTML='';return;}box.classList.remove('hidden');
    const cc=document.getElementById('course-overview-course-count'),mc=document.getElementById('course-overview-material-count'),ec=document.getElementById('course-overview-exam-count');if(cc)cc.textContent=`課程 ${courses.length}`;if(mc)mc.textContent=`教材 ${groupMaterials.length}`;if(ec)ec.textContent=`考卷 ${quizzes.length}`;
    const renderCard=(c,index,isOrphan=false)=>{const mats=isOrphan?orphanMaterials:groupMaterials.filter(m=>m.courseId===c.id),exams=isOrphan?orphanQuizzes:quizzes.filter(q=>q.courseId===c.id),done=mats.filter(m=>myCompletedMaterials[m.id]).length,pct=mats.length?Math.round(done/mats.length*100):0,activeQuestions=exams.reduce((sum,q)=>sum+examBankCount(q),0);const desc=(!isOrphan&&c.desc&&c.desc.trim()!==c.title?.trim())?c.desc:(isOrphan?'未綁定課程的教材與考卷集中於此，管理者可於後台重新歸類。':'教材、題庫與考核集中在同一門課程中。');return `<details class="course-learning-card" ${index===0&&!isOrphan?'open':''}><summary class="course-learning-summary"><div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="text-lg font-black text-slate-900">${isOrphan?'📁 通用／未歸類資源':`📘 ${escapeHtml(c.title||'未命名課程')}`}</span>${isOrphan?'<span class="text-[10px] font-bold rounded-full px-2 py-0.5 bg-amber-50 text-amber-700">待整理</span>':'<span class="text-[10px] font-bold rounded-full px-2 py-0.5 bg-emerald-50 text-emerald-700">● 啟用中</span>'}</div><p class="text-xs text-slate-500 mt-1 leading-5">${escapeHtml(desc)}</p><div class="flex flex-wrap gap-1.5 mt-2"><span class="course-stat-chip">📚 教材 ${mats.length} 份</span><span class="course-stat-chip">📝 題庫 ${activeQuestions} 題</span><span class="course-stat-chip">📋 考卷 ${exams.length} 份</span><span class="course-stat-chip">✅ 教材完成 ${done}/${mats.length}</span></div>${mats.length?`<div class="flex items-center gap-2 mt-2 max-w-lg"><div class="course-progress-mini flex-1"><span style="width:${pct}%"></span></div><span class="text-[10px] font-bold text-slate-500">${pct}%</span></div>`:''}</div><span class="course-learning-chevron">⌄</span></summary><div class="course-material-group space-y-4"><div><div class="flex items-center justify-between gap-2 mb-2"><h4 class="text-xs font-black tracking-wide text-slate-600">📚 學習教材</h4><span class="text-[11px] text-slate-400">教材 ${mats.length} 份</span></div><div class="space-y-2">${mats.length?mats.map(buildCourseMaterialRow).join(''):'<div class="course-empty-row">此課程尚未放置教材。</div>'}</div></div><div><div class="flex items-center justify-between gap-2 mb-2"><h4 class="text-xs font-black tracking-wide text-slate-600">📋 課後考核</h4><span class="text-[11px] text-slate-400">考卷 ${exams.length} 份</span></div><div class="space-y-2">${exams.length?exams.map(buildCourseExamRow).join(''):'<div class="course-empty-row">此課程尚未建立考卷。</div>'}</div></div></div></details>`;};
    let html=courses.map((c,i)=>renderCard(c,i,false)).join('');if(orphanMaterials.length||orphanQuizzes.length)html+=renderCard({id:'',title:'通用／未歸類資源',desc:''},courses.length,true);grid.innerHTML=html;
}

async function markMaterialComplete(materialId){
    const name=(document.getElementById('examinee-name')?.value || document.getElementById('progress-name')?.value || '').trim();
    const empId=(document.getElementById('examinee-id')?.value || document.getElementById('progress-empid')?.value || '').trim();
    if(!name||!empId){alert('請先回首頁設定姓名與工號；內頁會自動連動，不需要重複輸入。'); return;}
    const res=await fetch('/api/material-progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,empId,materialId})});
    const data=await res.json().catch(()=>({})); if(!res.ok){alert(data.error||'儲存失敗');return;}
    myCompletedMaterials[materialId]=data.completedAt||true;
    if(currentMaterialView==='materials') renderCourseOverview(); else await renderSlidesGrid();
}

async function loadMyProgress(){
    const name=document.getElementById('progress-name').value.trim(), empId=document.getElementById('progress-empid').value.trim();
    if(!name||!empId){alert('請先回首頁設定姓名與工號。');return;}
    rememberLearnerFields();
    const res=await fetch(`/api/my-progress?name=${encodeURIComponent(name)}&empId=${encodeURIComponent(empId)}&area=${currentTrainingArea}&group=${currentGroupKey}`);
    const data=await res.json().catch(()=>({})); if(!res.ok){alert(data.error||'查詢失敗');return;}
    myCompletedMaterials=data.materialsCompleted||{};
    document.getElementById('progress-summary').classList.remove('hidden');
    const cards=document.getElementById('progress-course-cards');
    cards.innerHTML=(data.courses||[]).length ? data.courses.map(c=>`<div class="bg-white border ${c.completed?'border-emerald-300':'border-slate-200'} rounded-2xl p-4 shadow-sm"><div class="flex justify-between gap-2"><h3 class="font-bold text-slate-800">${escapeHtml(c.title)}</h3><span class="text-xs font-bold ${c.completed?'text-emerald-700':'text-amber-700'}">${c.completed?'✅ 完成':'進行中'}</span></div><p class="text-xs text-slate-500 mt-1">${escapeHtml(c.desc||'')}</p><div class="mt-3 text-xs space-y-1"><div>教材：${c.materialsCompleted} / ${c.materialsTotal}</div><div>考試：${c.examRequired?(c.examPassed?'✅ 已通過':'⏳ 尚未通過'):'不要求'}</div></div></div>`).join('') : '<div class="text-sm text-slate-400">目前組別尚未建立課程。</div>';
    const hist=document.getElementById('progress-exam-history');
    hist.innerHTML=(data.records||[]).length ? data.records.map(r=>`<div class="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2"><div><div class="font-semibold text-slate-800">${escapeHtml(r.quizTitle||'')}</div><div class="text-xs text-slate-400">${escapeHtml(r.timestamp||'')}</div></div><div class="text-right"><div class="font-bold ${r.reviewStatus==='pending'?'text-amber-600':(Number(r.score)>=80?'text-emerald-600':'text-rose-600')}">${r.reviewStatus==='pending'?'待人工批改':`${Number(r.score)||0} 分`}</div><div class="text-xs text-slate-500">${escapeHtml(r.status||'')}</div></div></div>`).join('') : '<div class="p-5 text-sm text-slate-400">尚無考試紀錄。</div>';
}
