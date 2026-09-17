/* Final convergence compatibility shell: shared state + DOCX fallback only. */
let currentReviewRecordIndex=null;
async function getAdminKey() {
    // Compatibility header only.  Server-side session RBAC authorizes every
    // request; no ADMIN_KEY is prompted for or persisted in this browser.
    return 'rbac-session';
}

const ADMIN_CACHE_MS = 30000;
const ADMIN_QUIZ_CACHE_MS = 60000;
const ADMIN_COURSE_CACHE_MS = 60000;
let adminMaterialsCache = { data: null, at: 0 };
const adminQuizCategoriesCache = new Map();
const adminCoursesCache = new Map();
function adminScopeKey(area, group){ return `${area || 'internal'}::${group || 'grpBio'}`; }
// ==================================================================
// 管理者後台：組別選單、教材分類選單、考題頁籤與題庫管理
// ==================================================================

const aiMaterialCatalog = {};
const aiMaterialPickerState = {};

const adminQuizQuestionCache = {};



document.addEventListener('input',e=>{if(e.target?.id?.startsWith('exam-quota-'))updateExamQuotaTotal();});


// ==================================================================

// ==================================================================
// 管理者後台：各組別 Word 匯出範本 (doc_templates) 管理
// 六組皆可由後台上傳 Word 匯出範本；生化組也納入統一管理。
// ==================================================================
let pendingDocTemplateUploadGroup = null;

document.getElementById('admin-doc-template-upload-input').addEventListener('change', async function (e) {
    const file = e.target.files[0];
    e.target.value = '';
    const groupKey = pendingDocTemplateUploadGroup;
    pendingDocTemplateUploadGroup = null;
    if (!file || !groupKey) return;
    const key = await getAdminKey();
    if (!key) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch(`/api/doc-templates/${groupKey}`, { method: 'POST', headers: { 'X-Admin-Key': key }, body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '上傳失敗');
        alert(`✅ Word 範本格式檢查通過並已上傳（${Math.round((data.validation?.sizeBytes||0)/1024)} KB）`);
        await renderAdminDocTemplates();
    } catch (err) {
        alert(`❌ ${err.message}`);
    }
});



let adminResultsPage = 1;
// --- 附件1 匯出功能 (支援後台直接匯出或目前頁籤即時匯出) ---
// 生化組：沿用原本「匯出時於瀏覽器選一次附件1.docx，之後快取沿用」的方式。
// 六組皆優先使用管理者已上傳到伺服器的該組別空白範本，自動抓取並直接填入匯出，
// 不需要每次匯出都手動選檔。
let cachedTemplateBuffer = null;
let adminRecords = [];
let adminKey = '';
let pendingExportRecordIndex = null;
let isExportingCurrentTab = false;

// 組出目前頁籤（作答中）的匯出資料與檔名
// 組出後台某一筆已存檔成績的匯出資料與檔名
// 用給定的範本二進位內容 (ArrayBuffer) 填入資料並下載，成功回傳 true
// 依組別代碼向伺服器抓取該組已上傳的空白範本並直接匯出

function generateCurrentTabWord() {
    const { payload, filenamePart } = buildCurrentTabDocPayload();
    if (!renderDocxFromBuffer(cachedTemplateBuffer, payload, filenamePart)) {
        cachedTemplateBuffer = null;
    }
}

async function exportRecordToWord(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const groupKey = rec.groupKey || 'grpBio';
    const { payload, filenamePart } = buildRecordDocPayload(rec);
    const ok = await exportWithServerTemplate(groupKey, payload, filenamePart, groupKey === 'grpBio');
    if (!ok && groupKey === 'grpBio') {
        isExportingCurrentTab = false; pendingExportRecordIndex = recordIndex;
        if (cachedTemplateBuffer) generateWordFromTemplate(recordIndex);
        else { alert('後台尚未上傳生化組 Word 範本。可暫時選擇本機「附件1.docx」匯出。'); document.getElementById('docx-template-input').click(); }
    }
}

function generateWordFromTemplate(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const { payload, filenamePart } = buildRecordDocPayload(rec);
    if (!renderDocxFromBuffer(cachedTemplateBuffer, payload, filenamePart)) {
        cachedTemplateBuffer = null;
    }
}

document.getElementById('docx-template-input').addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (evt) {
        cachedTemplateBuffer = evt.target.result;
        if (isExportingCurrentTab) {
            generateCurrentTabWord();
        } else if (pendingExportRecordIndex !== null) {
            const idx = pendingExportRecordIndex;
            pendingExportRecordIndex = null;
            generateWordFromTemplate(idx);
        }
    };
    reader.onerror = function () {
        alert('讀取範本檔案失敗。');
    };
    reader.readAsArrayBuffer(file);
    e.target.value = '';
});
