/* Final convergence compatibility shell: shared admin caches only. */
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

const adminQuizQuestionCache = {};

let adminRecords = [];
