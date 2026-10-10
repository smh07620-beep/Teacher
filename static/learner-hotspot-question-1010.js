/* Learner exam: "click the structure" (atlas_hotspot) question.
 *
 * Owner of: rendering one hotspot question's image + pin and turning a click
 * into a normalised answer {x,y} (fractions 0..1 of the image).  Grading is
 * server-side only; the learner payload contains just the image URL and the
 * question text (no mark names, no correct region).
 *
 * system-exam.js (canonical exam runtime) calls render() from
 * renderQuestionMedia() and exposes setHotspotAnswer() for the answer store.
 * Clicks arrive through the CSP delegate (data-csp-click -> atlasHotspotPick).
 */
(function (root) {
  'use strict';

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function clamp01(v) { return Math.min(1, Math.max(0, v)); }
  function round4(v) { return Math.round(v * 10000) / 10000; }

  // Click position relative to the image rectangle -> fractions.
  function pointFromClick(clientX, clientY, rect) {
    if (!rect || !rect.width || !rect.height) return null;
    return { x: round4(clamp01((clientX - rect.left) / rect.width)), y: round4(clamp01((clientY - rect.top) / rect.height)) };
  }

  function pinHtml(ans) {
    if (!ans || typeof ans !== 'object' || !isFinite(ans.x) || !isFinite(ans.y)) return '';
    return '<span class="aa-pin" aria-hidden="true" style="position:absolute;left:' + (clamp01(+ans.x) * 100) + '%;top:' + (clamp01(+ans.y) * 100) +
      '%;width:22px;height:22px;margin:-11px 0 0 -11px;border:3px solid #f59e0b;border-radius:50%;background:rgba(245,158,11,.25);box-shadow:0 0 0 2px #fff;pointer-events:none"></span>';
  }

  function render(q, i, submitted, ans) {
    var url = String(q && q.imageUrl || '');
    if (!url) return '<p class="text-sm text-rose-600">這題的圖片不見了，請通知老師。</p>';
    var hint = submitted ? '你點選的位置以橘色圓圈標示。' : '請在圖片上點選你認為正確的位置；再點一次可以更改。圖片太小可先按「＋」放大。';
    var tools = submitted ? '' :
      '<div class="mb-2 flex items-center gap-2 text-xs">' +
      '<button type="button" data-csp-click="atlasHotspotZoom(' + i + ',-1)" class="rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-bold">－</button>' +
      '<span id="aa-hotspot-zoom-' + i + '" class="w-12 text-center font-bold text-slate-600">100%</span>' +
      '<button type="button" data-csp-click="atlasHotspotZoom(' + i + ',1)" class="rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-bold">＋</button>' +
      '</div>';
    return '<div class="question-media aa-hotspot" data-hotspot-index="' + i + '">' + tools +
      '<div class="aa-hotspot-scroll" style="overflow:auto;max-height:70vh;border-radius:12px;border:1px solid #cbd5e1;background:#0f172a">' +
      '<div class="aa-hotspot-canvas" ' + (submitted ? '' : 'data-csp-click="atlasHotspotPick(event,' + i + ')" ') +
      'style="position:relative;display:inline-block;width:100%;line-height:0;cursor:' + (submitted ? 'default' : 'crosshair') + '">' +
      '<img src="' + esc(url) + '" alt="題目影像" draggable="false" style="display:block;width:100%;height:auto;user-select:none;-webkit-user-drag:none">' +
      pinHtml(ans) + '</div></div>' +
      '<p class="mt-2 text-xs text-slate-500">' + hint + '</p></div>';
  }

  function cardImage(i) {
    var host = document.querySelector('#quiz-questions-list .aa-hotspot[data-hotspot-index="' + i + '"]');
    return host ? { host: host, canvas: host.querySelector('.aa-hotspot-canvas'), img: host.querySelector('img') } : null;
  }

  // Called by the CSP delegate on click.
  function pick(event, i) {
    var c = cardImage(i);
    if (!c || !c.img || !event) return;
    var p = pointFromClick(event.clientX, event.clientY, c.img.getBoundingClientRect());
    if (!p) return;
    if (typeof root.setHotspotAnswer === 'function') root.setHotspotAnswer(i, p);
    var old = c.canvas.querySelector('.aa-pin');
    if (old) old.remove();
    c.canvas.insertAdjacentHTML('beforeend', pinHtml(p));
  }

  var zoomLevels = [1, 1.5, 2, 3, 4];
  function zoom(i, dir) {
    var c = cardImage(i);
    if (!c) return;
    var cur = Number(c.canvas.dataset.zoom || 0);
    var next = Math.min(zoomLevels.length - 1, Math.max(0, cur + (dir > 0 ? 1 : -1)));
    c.canvas.dataset.zoom = String(next);
    c.canvas.style.width = zoomLevels[next] * 100 + '%';
    var label = document.getElementById('aa-hotspot-zoom-' + i);
    if (label) label.textContent = Math.round(zoomLevels[next] * 100) + '%';
  }

  var api = { render: render, pick: pick, zoom: zoom, _pointFromClick: pointFromClick };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.AtlasHotspotQuestion = api;
    root.atlasHotspotPick = pick;
    root.atlasHotspotZoom = zoom;
  }
})(typeof window !== 'undefined' ? window : globalThis);
