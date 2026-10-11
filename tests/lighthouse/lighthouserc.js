// Lighthouse CI 設定（網頁速度、無障礙、最佳實務檢測）。
//
// 由 .github/workflows/lighthouse.yml 使用；說明請看 docs/LIGHTHOUSE.md。
// 全部標準都是「警告」等級：目的是持續追蹤、發現退步，不是讓上線流程被擋住。
//
// 環境變數：
//   LH_PRESET     desktop 或 mobile（預設 mobile）
//   LH_USERNAME / LH_PASSWORD
//                 有提供就先登入再檢測（看到的是同仁登入後的畫面）；沒提供只測公開頁面
//   CHROME_PATH   Chrome 執行檔位置
const path = require('path');

const hasLogin = Boolean(process.env.LH_USERNAME && process.env.LH_PASSWORD);
const preset = process.env.LH_PRESET === 'desktop' ? 'desktop' : 'mobile';
const chromeArgs = ['--no-sandbox', '--headless=new', '--disable-gpu', '--disable-dev-shm-usage'];

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 3,
      // lhci 會把這個路徑當成「相對於目前資料夾」，所以要轉成相對路徑，不論從哪裡執行都找得到。
      ...(hasLogin
        ? { puppeteerScript: path.relative(process.cwd(), path.join(__dirname, 'login-script.js')) }
        : {}),
      // 有登入腳本時，Chrome 由 puppeteer 啟動，要用這組參數；沒有時用 settings.chromeFlags。
      puppeteerLaunchOptions: {
        executablePath: process.env.CHROME_PATH || undefined,
        args: chromeArgs,
        headless: true,
      },
      settings: {
        ...(preset === 'desktop' ? { preset: 'desktop' } : {}),
        // 有登入腳本時由 puppeteer 啟動 Chrome，chromeFlags 會被忽略（並印出警告），所以只在沒登入時設定。
        ...(hasLogin ? {} : { chromeFlags: chromeArgs.join(' ') }),
      },
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.6 }],
        'categories:accessibility': ['warn', { minScore: 0.9 }],
        'categories:best-practices': ['warn', { minScore: 0.9 }],
        'largest-contentful-paint': ['warn', { maxNumericValue: 4000 }],
        'cumulative-layout-shift': ['warn', { maxNumericValue: 0.1 }],
        'total-blocking-time': ['warn', { maxNumericValue: 600 }],
      },
    },
    upload: {
      target: 'filesystem',
      outputDir: '.lighthouseci/reports',
    },
  },
};
