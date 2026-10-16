# 重新產生 static/tailwind.css

`/system` 不再載入 cdn.tailwindcss.com，而是用事先編譯好的 `static/tailwind.css`。
新增或修改了 Tailwind class 之後，需要重新產生：

1. 用 `python tools/tailwind_build/make_tokens.py` 掃描 `static/*.html`、`static/*.js` 產生 `tokens.json`（放在本資料夾）。
2. `python tools/tailwind_build/server.py`（開在 127.0.0.1:5056，只有本機能連）。
3. 用瀏覽器開 http://127.0.0.1:5056/ ，等標題變成「done …」。
4. 結果在本資料夾的 `out.css`，複製成 `static/tailwind.css`，並把 `system.html` 裡 `/tailwind.css?v=` 的數字加 1。

動態組出來的 class（例如 `bg-${color}-100`）掃不到，請在程式裡寫出完整 class 名稱。
