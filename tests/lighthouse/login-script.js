// Lighthouse 檢測前先登入（由 lighthouserc.js 在有帳密時載入）。
//
// 直接在瀏覽器裡呼叫網站的登入 API，不依賴登入表單的版面，
// 登入狀態（cookie）會留在這個瀏覽器，之後 Lighthouse 量測的頁面就是登入後的畫面。
// 帳號密碼只從環境變數讀取，不會輸出到畫面。
module.exports = async (browser, context) => {
  const username = process.env.LH_USERNAME;
  const password = process.env.LH_PASSWORD;
  if (!username || !password) return;

  const origin = new URL(context.url).origin;
  const page = await browser.newPage();
  try {
    // 先開一個同網站的頁面，讓登入請求帶有正確的 Origin（網站會檢查，防止跨站請求）。
    await page.goto(`${origin}/live`, { waitUntil: 'domcontentloaded' });
    const status = await page.evaluate(
      async (u, p) => {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ username: u, password: p }),
        });
        return res.status;
      },
      username,
      password,
    );
    if (status !== 200) {
      throw new Error(`Lighthouse 檢測帳號登入失敗（HTTP ${status}），請確認帳號密碼。`);
    }
  } finally {
    await page.close();
  }
};
