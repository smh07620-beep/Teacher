// Teacher 網站壓力測試（k6）
//
// 目的：模擬「很多同仁同時登入、看頁面」的情況，量出網站在多少人同時使用時開始變慢。
//
// 安全設計：
//   * 只做「讀取」（GET）。唯一的 POST 是 setup() 登入一次（只有提供監控帳號時才會登入）。
//   * 登入只做一次，所有虛擬使用者共用這個登入狀態，所以不會觸發網站的登入次數限制，
//     也不會對正式站寫入任何資料。
//   * 帳號密碼只從環境變數讀取，不會印在畫面或報告裡。
//
// 用法請看 docs/LOAD_TEST.md。

import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE = String(__ENV.BASE_URL || '').replace(/\/+$/, '');
if (!/^https?:\/\//.test(BASE)) {
  throw new Error('請先設定 BASE_URL，例如 https://teacher-j3id.onrender.com');
}

const PROFILE = String(__ENV.PROFILE || 'smoke');
const USERNAME = __ENV.TEACHER_LOAD_USERNAME || '';
const PASSWORD = __ENV.TEACHER_LOAD_PASSWORD || '';
// 登入後預設要測的「唯讀」頁面資料：學員平常打開首頁會讀到的內容。
const DEFAULT_PATHS = [
  '/api/dashboard/me',
  '/api/courses',
  '/api/announcements',
  '/api/learning-assignments/mine',
  '/api/my-progress',
];
// 另外想加的「唯讀」路徑，用逗號分隔（只放 GET 讀取用的路徑）。
const EXTRA_PATHS = String(__ENV.K6_EXTRA_PATHS || '')
  .split(',')
  .map((s) => s.trim())
  .filter((s) => s.startsWith('/'));
const CANDIDATE_PATHS = DEFAULT_PATHS.concat(EXTRA_PATHS).filter((p, i, a) => a.indexOf(p) === i);

// 測試強度：數字是「同時在線的虛擬使用者」。
const PROFILES = {
  // 冒煙測試：1 人、30 秒，確認腳本和網站都正常。
  smoke: [{ duration: '30s', target: 1 }],
  // 約 10 人同時使用（平常上班時段）。
  staff10: [
    { duration: '30s', target: 10 },
    { duration: '2m', target: 10 },
    { duration: '20s', target: 0 },
  ],
  // 約 30 人同時使用（上線第一天多人同時登入）。
  peak30: [
    { duration: '1m', target: 30 },
    { duration: '3m', target: 30 },
    { duration: '30s', target: 0 },
  ],
  // 找出極限（只建議在自己電腦或測試站跑，不要對正式站跑）。
  stress60: [
    { duration: '1m', target: 20 },
    { duration: '1m', target: 40 },
    { duration: '1m', target: 60 },
    { duration: '30s', target: 0 },
  ],
};

if (!PROFILES[PROFILE]) {
  throw new Error(`PROFILE 只能是：${Object.keys(PROFILES).join('、')}（目前是 ${PROFILE}）`);
}

export const options = {
  scenarios: {
    staff: {
      executor: 'ramping-vus',
      // 冒煙測試一開始就要有 1 人，否則 30 秒內來不及跑完一輪。
      startVUs: PROFILE === 'smoke' ? 1 : 0,
      stages: PROFILES[PROFILE],
      gracefulRampDown: '15s',
    },
  },
  // 通過標準：失敗率低於 2%；一般頁面 95% 在 3 秒內；API 95% 在 2 秒內。
  thresholds: {
    http_req_failed: ['rate<0.02'],
    'http_req_duration{kind:page}': ['p(95)<3000'],
    'http_req_duration{kind:api}': ['p(95)<2000'],
    'http_req_duration{kind:static}': ['p(95)<3000'],
    checks: ['rate>0.98'],
  },
  userAgent: 'TeacherLoadTest/1.0',
  discardResponseBodies: false,
};

function originHeaders() {
  // 網站會擋沒有 Origin/Referer 的寫入請求（CSRF 防護），登入時要像瀏覽器一樣帶上。
  return { Origin: BASE, Referer: `${BASE}/`, 'Content-Type': 'application/json' };
}

export function setup() {
  if (!USERNAME || !PASSWORD) {
    console.log('未提供 TEACHER_LOAD_USERNAME / TEACHER_LOAD_PASSWORD：只測試未登入可看到的頁面。');
    return { cookie: '', paths: [] };
  }
  const res = http.post(
    `${BASE}/api/auth/login`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    { headers: originHeaders(), tags: { kind: 'setup' } },
  );
  if (res.status !== 200) {
    // 不印出帳密；直接停止，避免大家以為有登入其實沒有。
    throw new Error(`壓力測試帳號登入失敗（HTTP ${res.status}）。請確認帳號密碼，或先不要提供帳密只測公開頁面。`);
  }
  const jar = res.cookies || {};
  const cookie = Object.keys(jar)
    .map((name) => `${name}=${jar[name][0].value}`)
    .join('; ');
  if (!cookie) {
    throw new Error('登入成功但沒有取得登入狀態（cookie），無法繼續。');
  }
  console.log('壓力測試帳號登入成功（登入狀態將由所有虛擬使用者共用，只讀取資料）。');

  // 先各試一次：這個帳號讀不到的路徑（例如權限不同）就略過，並明確告知，
  // 避免整個測試因為帳號權限而誤判失敗。
  const paths = [];
  const skipped = [];
  CANDIDATE_PATHS.forEach((path) => {
    const r = http.get(`${BASE}${path}`, {
      headers: { Cookie: cookie },
      tags: { kind: 'setup' },
      // 前置探測不算進使用者的失敗率。
      responseCallback: http.expectedStatuses({ min: 200, max: 499 }),
    });
    if (r.status === 200) paths.push(path);
    else skipped.push(`${path}（HTTP ${r.status}）`);
  });
  if (skipped.length) {
    console.warn(`這個帳號讀不到、已略過的路徑：${skipped.join('、')}`);
  }
  if (!paths.length) {
    console.warn('沒有任何登入後的資料路徑可測，只會測試首頁與登入狀態。');
  }
  return { cookie, paths };
}

function staticAssets(html) {
  // 像瀏覽器第一次進站一樣，載入頁面引用的同網站 JS / CSS（最多 12 個）。
  const found = [];
  const re = /(?:src|href)=["']([^"']+\.(?:js|css)(?:\?[^"']*)?)["']/gi;
  let m;
  while ((m = re.exec(html)) !== null && found.length < 12) {
    const url = m[1];
    if (/^https?:\/\//i.test(url) || url.startsWith('//')) continue; // 外部資源不測
    found.push(url.startsWith('/') ? url : `/${url}`);
  }
  return found;
}

export default function (data) {
  const authed = Boolean(data && data.cookie);
  const auth = authed ? { Cookie: data.cookie } : {};

  group('進站（第一次載入）', () => {
    const login = http.get(`${BASE}/login`, { tags: { kind: 'page' } });
    check(login, { '登入頁 200': (r) => r.status === 200 });
    const assets = staticAssets(String(login.body || ''));
    if (assets.length) {
      const responses = http.batch(
        assets.map((p) => ['GET', `${BASE}${p}`, null, { tags: { kind: 'static' } }]),
      );
      responses.forEach((r) => check(r, { '靜態檔 200': (x) => x.status === 200 }));
    }
    const me = http.get(`${BASE}/api/auth/me`, { tags: { kind: 'api' } });
    check(me, { '/api/auth/me 200': (r) => r.status === 200 });
  });
  sleep(1 + Math.random() * 2);

  if (authed) {
    group('登入後瀏覽', () => {
      const home = http.get(`${BASE}/`, { headers: auth, tags: { kind: 'page' } });
      check(home, { '首頁 200': (r) => r.status === 200 });
      const me = http.get(`${BASE}/api/auth/me`, { headers: auth, tags: { kind: 'api' } });
      check(me, {
        // 未登入時網站也回 200，所以要看內容：authenticated 必須是 true。
        '登入狀態有效': (r) => {
          try {
            return r.status === 200 && r.json('authenticated') === true;
          } catch (e) {
            return false;
          }
        },
      });
      (data.paths || []).forEach((p) => {
        const r = http.get(`${BASE}${p}`, { headers: auth, tags: { kind: 'api' } });
        check(r, { [`${p} 200`]: (x) => x.status === 200 });
        sleep(0.5 + Math.random());
      });
    });
    sleep(1 + Math.random() * 2);
  }
}

function ms(value) {
  return value === undefined ? '—' : `${Math.round(value)} ms`;
}

function line(label, metric) {
  if (!metric || !metric.values) return `${label}：沒有資料`;
  const v = metric.values;
  const ok = !metric.thresholds || Object.values(metric.thresholds).every((t) => t.ok);
  return `${label}：中位數 ${ms(v.med)}，95% 在 ${ms(v['p(95)'])} 內，最慢 ${ms(v.max)} ${ok ? '✅' : '❌ 超過標準'}`;
}

export function handleSummary(data) {
  const m = data.metrics;
  const total = m.http_reqs ? m.http_reqs.values.count : 0;
  const rps = m.http_reqs ? m.http_reqs.values.rate.toFixed(1) : '0';
  const failRate = m.http_req_failed ? m.http_req_failed.values.rate : 0;
  const vus = m.vus_max ? m.vus_max.values.max : 0;
  const failed = Object.values(m).some(
    (x) => x.thresholds && Object.values(x.thresholds).some((t) => !t.ok),
  );
  // 一輪都沒跑完就不能說「通過」，避免誤判。
  const iterations = m.iterations ? m.iterations.values.count : 0;
  const text = [
    '',
    '========== Teacher 壓力測試結果 ==========',
    `測試強度：${PROFILE}（最多同時 ${vus} 位虛擬使用者）｜目標：${BASE}`,
    `登入狀態：${USERNAME ? '有登入（唯讀）' : '未登入（只測公開頁面）'}`,
    `總請求數：${total}（每秒約 ${rps} 個）｜失敗率：${(failRate * 100).toFixed(2)}%`,
    line('一般頁面', m['http_req_duration{kind:page}']),
    line('API       ', m['http_req_duration{kind:api}']),
    line('靜態檔案  ', m['http_req_duration{kind:static}']),
    iterations === 0
      ? '結論：⚠️ 沒有任何一輪完整跑完，無法判定。請拉長測試時間或確認網站是否能連上。'
      : failed
        ? '結論：❌ 未達標準，請看上面標 ❌ 的項目。'
        : '結論：✅ 在這個強度下，網站表現符合標準。',
    '==========================================',
    '',
  ].join('\n');
  return {
    stdout: text,
    'load-test-summary.json': JSON.stringify(data, null, 2),
    'load-test-summary.txt': text,
  };
}
