/* Atlas annotations: teacher box-drawing editor + learner click-to-zoom viewer.
 *
 * Owner of: marking cells/structures on an Atlas image (editor) and the
 * interactive zoom/explanation overlay inside the existing #atlas-modal
 * (viewer).  Data lives in atlas item `annotationJson` =
 *   {version:1, marks:[{id,label,detail,x,y,w,h}]}   (x,y,w,h are 0..1 fractions)
 * Persistence and validation are server-side (teacher_app/atlas/annotations.py).
 *
 * Called from the canonical owners (no wrapper chains):
 *   atlas-70.js          -> attachEditor / collect (edit form), attachViewer (open item)
 *   system-learner.js    -> active / zoomBy / reset (+/- buttons), detachViewer (close)
 * Learners never get an editor; everything is added with addEventListener and
 * textContent (CSP-safe, no inline handlers, no HTML strings built from user text).
 */
(function (root) {
  'use strict';

  var MIN_DRAW = 0.01;       // ignore accidental clicks: a box must be >= 1% of the image
  var MAX_SCALE = 8;

  /* ---------- pure geometry (unit-tested in tests/js) ---------- */
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function round5(v) { return Math.round(v * 100000) / 100000; }

  // Two corner points (fractions) -> normalised box, or null when too small.
  function rectFromPoints(a, b) {
    var x1 = clamp(Math.min(a.x, b.x), 0, 1), y1 = clamp(Math.min(a.y, b.y), 0, 1);
    var x2 = clamp(Math.max(a.x, b.x), 0, 1), y2 = clamp(Math.max(a.y, b.y), 0, 1);
    var w = x2 - x1, h = y2 - y1;
    if (w < MIN_DRAW || h < MIN_DRAW) return null;
    return { x: round5(x1), y: round5(y1), w: round5(w), h: round5(h) };
  }

  // Keep a scaled image covering the stage (or centred when smaller).
  function clampTranslate(view, stage, world) {
    var sw = world.w * view.s, sh = world.h * view.s;
    var tx = sw <= stage.w ? (stage.w - sw) / 2 : clamp(view.tx, stage.w - sw, 0);
    var ty = sh <= stage.h ? (stage.h - sh) / 2 : clamp(view.ty, stage.h - sh, 0);
    return { s: view.s, tx: tx, ty: ty };
  }

  // View that puts `mark` (fractions) in the middle of the stage, filling ~`fill` of it.
  function focusView(mark, stage, world, fill) {
    fill = fill || 0.4;
    var s = Math.min(fill * stage.w / (mark.w * world.w), fill * stage.h / (mark.h * world.h));
    s = clamp(s, 1.5, MAX_SCALE);
    var cx = (mark.x + mark.w / 2) * world.w * s, cy = (mark.y + mark.h / 2) * world.h * s;
    return clampTranslate({ s: s, tx: stage.w / 2 - cx, ty: stage.h / 2 - cy }, stage, world);
  }

  // Zoom by `factor` keeping the point (px,py) (stage pixels) fixed.
  function zoomAbout(view, factor, px, py, stage, world) {
    var s = clamp(view.s * factor, 1, MAX_SCALE);
    var k = s / view.s;
    return clampTranslate({ s: s, tx: px - (px - view.tx) * k, ty: py - (py - view.ty) * k }, stage, world);
  }

  function fitWorld(stage, nat) {
    var base = Math.min(stage.w / nat.w, stage.h / nat.h);
    return { w: nat.w * base, h: nat.h * base };
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* ---------- teacher editor ---------- */
  var editors = new WeakMap();

  function newId() { return 'm' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

  function attachEditor(form, item) {
    if (!form || !item || !item.imageUrl) return false;
    var marks = (item.annotationJson && Array.isArray(item.annotationJson.marks) ? item.annotationJson.marks : [])
      .map(function (m) { return { id: String(m.id), label: String(m.label || ''), detail: String(m.detail || ''), x: +m.x, y: +m.y, w: +m.w, h: +m.h }; });
    var state = { marks: marks, selected: null };

    var box = el('section', 'rounded-xl border border-indigo-200 bg-indigo-50/40 p-3 space-y-2');
    box.setAttribute('data-aa-editor', '1');
    box.appendChild(el('div', 'font-black text-sm', '🔬 標記細胞／構造（選填）'));
    box.appendChild(el('p', 'text-xs text-slate-600',
      '在圖上按住滑鼠（或手指）拖曳，框出一顆細胞或構造，放開後在下方填名稱與詳解。學員點到框就會放大並看到你寫的詳解；也能拿來出「點選圖片題」。'));
    var canvas = el('div', 'aa-edit-canvas');
    canvas.style.cssText = 'position:relative;display:inline-block;max-width:100%;touch-action:none;cursor:crosshair;user-select:none;line-height:0';
    var img = document.createElement('img');
    img.src = item.imageUrl; img.alt = '圖譜'; img.draggable = false;
    img.style.cssText = 'max-width:100%;max-height:60vh;display:block;border-radius:8px';
    canvas.appendChild(img);
    var draft = el('div'); draft.style.cssText = 'position:absolute;border:2px dashed #f59e0b;background:rgba(245,158,11,.15);display:none;pointer-events:none';
    canvas.appendChild(draft);
    var list = el('div', 'space-y-2');
    box.appendChild(canvas); box.appendChild(list);
    var anchor = form.lastElementChild;
    form.insertBefore(box, anchor);

    function placeBox(node, m) {
      node.style.left = m.x * 100 + '%'; node.style.top = m.y * 100 + '%';
      node.style.width = m.w * 100 + '%'; node.style.height = m.h * 100 + '%';
    }

    function paint() {
      Array.prototype.slice.call(canvas.querySelectorAll('[data-aa-box]')).forEach(function (n) { n.remove(); });
      state.marks.forEach(function (m, i) {
        var b = el('div');
        b.setAttribute('data-aa-box', m.id);
        b.style.cssText = 'position:absolute;border:2px solid ' + (m.id === state.selected ? '#f59e0b' : '#0d9488') + ';background:rgba(13,148,136,.12);pointer-events:none';
        placeBox(b, m);
        var tag = el('span', null, String(i + 1));
        tag.style.cssText = 'position:absolute;left:-2px;top:-18px;background:#0d9488;color:#fff;font-size:11px;font-weight:700;line-height:1;padding:3px 5px;border-radius:4px';
        b.appendChild(tag);
        canvas.appendChild(b);
      });
      list.textContent = '';
      if (!state.marks.length) list.appendChild(el('p', 'text-xs text-slate-500', '尚未標記。直接在圖上拖曳框選即可。'));
      state.marks.forEach(function (m, i) {
        var card = el('div', 'rounded-lg border bg-white p-2 space-y-1 ' + (m.id === state.selected ? 'border-amber-400' : 'border-slate-200'));
        var head = el('div', 'flex items-center gap-2');
        head.appendChild(el('span', 'text-xs font-black text-teal-700', '#' + (i + 1)));
        var label = document.createElement('input');
        label.type = 'text'; label.value = m.label; label.maxLength = 80; label.placeholder = '名稱（必填，例如：嗜中性球）';
        label.className = 'flex-1 border rounded-lg p-1.5 text-sm';
        label.setAttribute('data-aa-label', m.id);
        label.addEventListener('input', function () { m.label = label.value; });
        label.addEventListener('focus', function () { state.selected = m.id; markSelected(); });
        var del = el('button', 'text-xs text-rose-600 font-bold', '刪除'); del.type = 'button';
        del.addEventListener('click', function () {
          state.marks = state.marks.filter(function (x) { return x.id !== m.id; });
          paint();
        });
        head.appendChild(label); head.appendChild(del);
        var detail = document.createElement('textarea');
        detail.value = m.detail; detail.maxLength = 2000; detail.rows = 2;
        detail.placeholder = '詳解／鑑別重點（選填，學員點到這顆時會看到）';
        detail.className = 'w-full border rounded-lg p-1.5 text-xs';
        detail.addEventListener('input', function () { m.detail = detail.value; });
        detail.addEventListener('focus', function () { state.selected = m.id; markSelected(); });
        card.appendChild(head); card.appendChild(detail);
        list.appendChild(card);
      });
    }
    function markSelected() {
      Array.prototype.slice.call(canvas.querySelectorAll('[data-aa-box]')).forEach(function (b) {
        b.style.borderColor = b.getAttribute('data-aa-box') === state.selected ? '#f59e0b' : '#0d9488';
      });
    }

    var start = null;
    function point(ev) {
      var r = img.getBoundingClientRect();
      return { x: clamp((ev.clientX - r.left) / r.width, 0, 1), y: clamp((ev.clientY - r.top) / r.height, 0, 1) };
    }
    canvas.addEventListener('pointerdown', function (ev) {
      if (ev.button !== undefined && ev.button !== 0) return;
      if (state.marks.length >= 30) { alert('每張圖譜最多 30 個標記。'); return; }
      start = point(ev);
      try { canvas.setPointerCapture(ev.pointerId); } catch (_) {}
      ev.preventDefault();
    });
    canvas.addEventListener('pointermove', function (ev) {
      if (!start) return;
      var p = point(ev);
      var r = { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) };
      draft.style.display = 'block'; placeBox(draft, r);
    });
    function finish(ev, cancel) {
      if (!start) return;
      var p = point(ev), a = start; start = null; draft.style.display = 'none';
      if (cancel) return;
      var r = rectFromPoints(a, p);
      if (!r) return;
      var m = { id: newId(), label: '', detail: '', x: r.x, y: r.y, w: r.w, h: r.h };
      state.marks.push(m); state.selected = m.id; paint();
      var input = list.querySelector('[data-aa-label="' + m.id + '"]');
      if (input) input.focus();
    }
    canvas.addEventListener('pointerup', function (ev) { finish(ev, false); });
    canvas.addEventListener('pointercancel', function (ev) { finish(ev, true); });

    paint();
    editors.set(form, state);
    return true;
  }

  // Returns the object to send as annotationJson, `undefined` when no editor is
  // attached (caller must then leave the stored annotation untouched), or `null`
  // when the teacher still has to fix something (an alert was shown).
  function collect(form) {
    var state = editors.get(form);
    if (!state) return undefined;
    for (var i = 0; i < state.marks.length; i++) {
      if (!String(state.marks[i].label || '').trim()) {
        alert('第 ' + (i + 1) + ' 個標記還沒有填名稱。');
        return null;
      }
    }
    return state.marks.length
      ? { version: 1, marks: state.marks.map(function (m) { return { id: m.id, label: m.label.trim(), detail: m.detail.trim(), x: m.x, y: m.y, w: m.w, h: m.h }; }) }
      : {};
  }

  /* ---------- learner viewer ---------- */
  var viewer = null;

  function detachViewer() {
    if (!viewer) return;
    try { viewer.stage.remove(); } catch (_) {}
    var original = document.getElementById('atlas-modal-image');
    if (original) original.style.display = '';
    var zoomText = document.getElementById('atlas-zoom-text');
    if (zoomText) zoomText.textContent = '100%';
    viewer = null;
  }

  function attachViewer(item) {
    detachViewer();
    var marks = item && item.annotationJson && Array.isArray(item.annotationJson.marks) ? item.annotationJson.marks : [];
    var host = document.getElementById('atlas-stage');
    if (!marks.length || !host || !item.imageUrl) return false;
    var original = document.getElementById('atlas-modal-image');
    if (original) original.style.display = 'none';

    var stageEl = el('div'); stageEl.id = 'aa-stage';
    stageEl.style.cssText = 'position:absolute;inset:0;overflow:hidden;touch-action:none;cursor:grab;user-select:none';
    var worldEl = el('div'); worldEl.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform';
    var img = document.createElement('img');
    img.src = item.imageUrl; img.alt = String(item.title || 'Atlas'); img.draggable = false;
    img.style.cssText = 'display:block;width:100%;height:100%;pointer-events:none';
    worldEl.appendChild(img);

    var boxes = {};
    marks.forEach(function (m, i) {
      var b = document.createElement('button'); b.type = 'button';
      b.setAttribute('aria-label', String(m.label || '標記 ' + (i + 1)));
      b.style.cssText = 'position:absolute;border:2px solid rgba(45,212,191,.9);background:rgba(45,212,191,.10);border-radius:4px;cursor:pointer;padding:0';
      b.style.left = m.x * 100 + '%'; b.style.top = m.y * 100 + '%'; b.style.width = m.w * 100 + '%'; b.style.height = m.h * 100 + '%';
      b.addEventListener('click', function () { if (!viewer || viewer.moved) return; focusOn(m.id); });
      worldEl.appendChild(b); boxes[m.id] = b;
    });
    stageEl.appendChild(worldEl);

    // legend (tap names on phones) + detail panel
    var legend = el('div'); legend.style.cssText = 'position:absolute;left:8px;right:8px;top:8px;display:flex;gap:6px;flex-wrap:wrap;pointer-events:none';
    marks.forEach(function (m, i) {
      var chip = el('button', null, (i + 1) + '. ' + m.label); chip.type = 'button';
      chip.style.cssText = 'pointer-events:auto;background:rgba(15,23,42,.8);color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:999px;padding:4px 10px;font-size:12px;cursor:pointer';
      chip.addEventListener('click', function (ev) { ev.stopPropagation(); focusOn(m.id); });
      legend.appendChild(chip);
    });
    var toggle = el('button', null, '隱藏標記框'); toggle.type = 'button';
    toggle.style.cssText = 'pointer-events:auto;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:4px 10px;font-size:12px;cursor:pointer';
    legend.appendChild(toggle);
    stageEl.appendChild(legend);

    var panel = el('div'); panel.style.cssText = 'position:absolute;left:8px;right:8px;bottom:44px;max-height:42%;overflow:auto;background:rgba(15,23,42,.92);color:#fff;border:1px solid rgba(255,255,255,.2);border-radius:12px;padding:10px 12px;display:none;cursor:auto';
    var pTitle = el('div'); pTitle.style.cssText = 'font-weight:800;font-size:15px';
    var pBody = el('div'); pBody.style.cssText = 'margin-top:4px;font-size:13px;line-height:1.6;white-space:pre-wrap';
    var pBar = el('div'); pBar.style.cssText = 'margin-top:8px;display:flex;gap:8px;flex-wrap:wrap';
    function btn(text, fn) {
      var b = el('button', null, text); b.type = 'button';
      b.style.cssText = 'background:#0d9488;color:#fff;border:0;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer';
      b.addEventListener('click', function (ev) { ev.stopPropagation(); fn(); });
      return b;
    }
    pBar.appendChild(btn('↩ 還原全圖', function () { reset(); }));
    pBar.appendChild(btn('‹ 上一個', function () { step(-1); }));
    pBar.appendChild(btn('下一個 ›', function () { step(1); }));
    panel.appendChild(pTitle); panel.appendChild(pBody); panel.appendChild(pBar);
    panel.addEventListener('pointerdown', function (ev) { ev.stopPropagation(); });
    panel.addEventListener('wheel', function (ev) { ev.stopPropagation(); });
    stageEl.appendChild(panel);
    host.appendChild(stageEl);

    viewer = { stage: stageEl, world: worldEl, img: img, marks: marks, boxes: boxes, current: null, view: { s: 1, tx: 0, ty: 0 },
      nat: { w: 0, h: 0 }, size: { w: 0, h: 0 }, moved: false, panel: panel, pTitle: pTitle, pBody: pBody, toggle: toggle, boxesVisible: true };

    toggle.addEventListener('click', function (ev) {
      ev.stopPropagation();
      viewer.boxesVisible = !viewer.boxesVisible;
      Object.keys(viewer.boxes).forEach(function (id) { viewer.boxes[id].style.display = viewer.boxesVisible ? '' : 'none'; });
      toggle.textContent = viewer.boxesVisible ? '隱藏標記框' : '顯示標記框';
    });

    function layout() {
      if (!viewer || !viewer.nat.w) return;
      var st = { w: stageEl.clientWidth, h: stageEl.clientHeight };
      viewer.stageSize = st;
      viewer.size = fitWorld(st, viewer.nat);
      worldEl.style.width = viewer.size.w + 'px'; worldEl.style.height = viewer.size.h + 'px';
      apply(clampTranslate(viewer.view, st, viewer.size), false);
    }
    function onLoad() { viewer.nat = { w: img.naturalWidth || 1, h: img.naturalHeight || 1 }; viewer.view = { s: 1, tx: 0, ty: 0 }; layout(); }
    if (img.complete && img.naturalWidth) onLoad(); else img.addEventListener('load', function () { if (viewer && viewer.img === img) onLoad(); });
    if (typeof ResizeObserver !== 'undefined') { var ro = new ResizeObserver(function () { layout(); }); ro.observe(stageEl); viewer.ro = ro; }

    bindPointer(stageEl);
    return true;
  }

  function apply(view, animate) {
    if (!viewer) return;
    viewer.view = view;
    viewer.world.style.transition = animate ? 'transform .35s ease' : 'none';
    viewer.world.style.transform = 'translate(' + view.tx + 'px,' + view.ty + 'px) scale(' + view.s + ')';
    var zt = document.getElementById('atlas-zoom-text');
    if (zt) zt.textContent = Math.round(view.s * 100) + '%';
  }

  function stageBox() { return viewer && viewer.stageSize ? viewer.stageSize : { w: 1, h: 1 }; }

  function focusOn(id) {
    if (!viewer || !viewer.nat.w) return;
    var m = viewer.marks.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!m) return;
    viewer.current = m.id;
    var st = stageBox();
    // leave room for the detail panel at the bottom: aim the box at the upper part of the stage
    var target = focusView(m, { w: st.w, h: st.h * 0.62 }, viewer.size, 0.5);
    apply(clampTranslate(target, st, viewer.size), true);
    Object.keys(viewer.boxes).forEach(function (k) {
      viewer.boxes[k].style.borderColor = String(k) === String(m.id) ? '#fbbf24' : 'rgba(45,212,191,.9)';
    });
    viewer.pTitle.textContent = m.label;
    viewer.pBody.textContent = m.detail || '（老師尚未填寫詳解）';
    viewer.panel.style.display = 'block';
  }

  function step(dir) {
    if (!viewer || !viewer.marks.length) return;
    var idx = viewer.marks.findIndex(function (m) { return String(m.id) === String(viewer.current); });
    idx = idx < 0 ? (dir > 0 ? 0 : viewer.marks.length - 1) : (idx + dir + viewer.marks.length) % viewer.marks.length;
    focusOn(viewer.marks[idx].id);
  }

  function reset() {
    if (!viewer) return false;
    viewer.current = null;
    viewer.panel.style.display = 'none';
    Object.keys(viewer.boxes).forEach(function (k) { viewer.boxes[k].style.borderColor = 'rgba(45,212,191,.9)'; });
    apply(clampTranslate({ s: 1, tx: 0, ty: 0 }, stageBox(), viewer.size), true);
    return true;
  }

  function zoomBy(delta) {
    if (!viewer) return false;
    var st = stageBox();
    apply(zoomAbout(viewer.view, 1 + delta, st.w / 2, st.h / 2, st, viewer.size), true);
    return true;
  }

  function bindPointer(stageEl) {
    var pointers = {}, last = null, pinch = null;
    function pos(ev) { var r = stageEl.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }
    stageEl.addEventListener('pointerdown', function (ev) {
      if (!viewer) return;
      pointers[ev.pointerId] = pos(ev);
      viewer.moved = false;
      var ids = Object.keys(pointers);
      if (ids.length === 1) { last = pos(ev); stageEl.style.cursor = 'grabbing'; }
      if (ids.length === 2) { var a = pointers[ids[0]], b = pointers[ids[1]]; pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1 }; }
    });
    stageEl.addEventListener('pointermove', function (ev) {
      if (!viewer || !pointers[ev.pointerId]) return;
      var p = pos(ev); pointers[ev.pointerId] = p;
      var ids = Object.keys(pointers), st = stageBox();
      if (ids.length >= 2 && pinch) {
        var a = pointers[ids[0]], b = pointers[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
        apply(zoomAbout(viewer.view, d / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2, st, viewer.size), false);
        pinch.d = d; viewer.moved = true; return;
      }
      if (last) {
        var dx = p.x - last.x, dy = p.y - last.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) viewer.moved = true;
        if (viewer.moved) { apply(clampTranslate({ s: viewer.view.s, tx: viewer.view.tx + dx, ty: viewer.view.ty + dy }, st, viewer.size), false); last = p; }
      }
    });
    function up(ev) {
      delete pointers[ev.pointerId];
      if (!Object.keys(pointers).length) { last = null; pinch = null; stageEl.style.cursor = 'grab'; setTimeout(function () { if (viewer) viewer.moved = false; }, 0); }
      else { pinch = null; var rest = pointers[Object.keys(pointers)[0]]; last = rest; }
    }
    stageEl.addEventListener('pointerup', up);
    stageEl.addEventListener('pointercancel', up);
    stageEl.addEventListener('wheel', function (ev) {
      if (!viewer) return;
      ev.preventDefault();
      var p = pos(ev), st = stageBox();
      apply(zoomAbout(viewer.view, ev.deltaY < 0 ? 1.2 : 1 / 1.2, p.x, p.y, st, viewer.size), false);
    }, { passive: false });
  }

  var api = {
    attachEditor: attachEditor, collect: collect,
    attachViewer: attachViewer, detachViewer: detachViewer,
    active: function () { return !!viewer; }, zoomBy: zoomBy, reset: reset,
    _geometry: { clamp: clamp, rectFromPoints: rectFromPoints, clampTranslate: clampTranslate, focusView: focusView, zoomAbout: zoomAbout, fitWorld: fitWorld, MIN_DRAW: MIN_DRAW, MAX_SCALE: MAX_SCALE }
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AtlasAnnotations = api;
})(typeof window !== 'undefined' ? window : globalThis);
