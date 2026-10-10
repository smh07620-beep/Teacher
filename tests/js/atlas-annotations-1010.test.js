const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(file, extra = {}) {
  const window = {...extra};
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static', file), 'utf8'),
    {window, isFinite, Math},
  );
  return window;
}

// Objects created inside the vm context have a different Object.prototype, so
// compare plain copies.
const plain = (v) => JSON.parse(JSON.stringify(v));

const A = load('atlas-annotations-1010.js').AtlasAnnotations;
const G = A._geometry;

test('rectFromPoints normalises corner order and rounds', () => {
  const r = G.rectFromPoints({x: 0.5, y: 0.6}, {x: 0.3, y: 0.2});
  assert.deepEqual(plain(r), {x: 0.3, y: 0.2, w: 0.2, h: 0.4});
});

test('rectFromPoints rejects accidental clicks and clamps to the image', () => {
  assert.equal(G.rectFromPoints({x: 0.5, y: 0.5}, {x: 0.505, y: 0.7}), null);
  assert.equal(G.rectFromPoints({x: 0.5, y: 0.5}, {x: 0.5, y: 0.5}), null);
  const r = G.rectFromPoints({x: -0.2, y: 0.9}, {x: 0.3, y: 1.4});
  assert.deepEqual(plain(r), {x: 0, y: 0.9, w: 0.3, h: 0.1});
});

const stage = {w: 800, h: 600};
const world = {w: 800, h: 600};

test('fitWorld keeps the aspect ratio inside the stage', () => {
  assert.deepEqual(plain(G.fitWorld({w: 800, h: 600}, {w: 4000, h: 1000})), {w: 800, h: 200});
  assert.deepEqual(plain(G.fitWorld({w: 800, h: 600}, {w: 1000, h: 4000})), {w: 150, h: 600});
});

test('clampTranslate centres small images and never exposes empty space when zoomed', () => {
  const small = G.clampTranslate({s: 1, tx: 500, ty: -500}, {w: 800, h: 600}, {w: 400, h: 300});
  assert.deepEqual(plain(small), {s: 1, tx: 200, ty: 150});
  const big = G.clampTranslate({s: 2, tx: 100, ty: 100}, stage, world);
  assert.equal(big.tx, 0); assert.equal(big.ty, 0);
  const far = G.clampTranslate({s: 2, tx: -5000, ty: -5000}, stage, world);
  assert.equal(far.tx, 800 - 1600); assert.equal(far.ty, 600 - 1200);
});

test('focusView centres the mark and zooms in, within limits', () => {
  const v = G.focusView({x: 0.4, y: 0.4, w: 0.1, h: 0.1}, stage, world, 0.4);
  assert.ok(v.s > 1.5 && v.s <= G.MAX_SCALE);
  const cx = (0.45 * world.w) * v.s + v.tx, cy = (0.45 * world.h) * v.s + v.ty;
  assert.ok(Math.abs(cx - stage.w / 2) < 1 && Math.abs(cy - stage.h / 2) < 1);
  // a huge box never zooms out below 1.5x, a tiny one never beyond MAX_SCALE
  assert.equal(G.focusView({x: 0, y: 0, w: 1, h: 1}, stage, world, 0.4).s, 1.5);
  assert.equal(G.focusView({x: 0.5, y: 0.5, w: 0.0051, h: 0.0051}, stage, world, 0.4).s, G.MAX_SCALE);
});

test('a mark at the image edge stays fully visible (translate clamped)', () => {
  const v = G.focusView({x: 0.0, y: 0.0, w: 0.1, h: 0.1}, stage, world, 0.4);
  assert.equal(v.tx, 0); assert.equal(v.ty, 0);
});

test('zoomAbout keeps the pointed spot fixed and stays within [1, MAX]', () => {
  const v0 = {s: 1, tx: 0, ty: 0};
  const v1 = G.zoomAbout(v0, 2, 400, 300, stage, world);
  assert.equal(v1.s, 2);
  // the stage point (400,300) maps to the same world point before and after
  assert.equal((400 - v0.tx) / v0.s, (400 - v1.tx) / v1.s);
  assert.equal(G.zoomAbout(v0, 0.1, 400, 300, stage, world).s, 1);
  assert.equal(G.zoomAbout({s: 7, tx: -100, ty: -100}, 10, 400, 300, stage, world).s, G.MAX_SCALE);
});

test('collect/attachEditor are inert without a DOM editor (viewer-only learners)', () => {
  assert.equal(A.collect({}), undefined);
  assert.equal(A.active(), false);
  assert.equal(A.zoomBy(0.25), false);
  assert.equal(A.reset(), false);
  assert.equal(A.attachEditor(null, {}), false);
});

// ---- learner hotspot question ----
function hotspot(extraDoc) {
  const w = load('learner-hotspot-question-1010.js', {});
  return w;
}

test('render: image, CSP click action, no inline handlers, escaped url', () => {
  const w = hotspot();
  const html = w.AtlasHotspotQuestion.render({imageUrl: '/api/atlas/images/a"b.jpg'}, 3, false, null);
  assert.match(html, /data-csp-click="atlasHotspotPick\(event,3\)"/);
  assert.match(html, /data-csp-click="atlasHotspotZoom\(3,1\)"/);
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i);
  assert.doesNotMatch(html, /a"b/);
  assert.match(html, /a&quot;b/);
});

test('render: submitted state is read-only and shows the learner pin', () => {
  const w = hotspot();
  const html = w.AtlasHotspotQuestion.render({imageUrl: '/x.jpg'}, 0, true, {x: 0.25, y: 0.5});
  assert.doesNotMatch(html, /atlasHotspotPick/);
  assert.doesNotMatch(html, /atlasHotspotZoom/);
  assert.match(html, /aa-pin/);
  assert.match(html, /left:25%/);
  assert.match(html, /top:50%/);
});

test('render: no image or hostile answers do not break or inject', () => {
  const w = hotspot();
  assert.match(w.AtlasHotspotQuestion.render({}, 0, false, null), /圖片不見了/);
  const html = w.AtlasHotspotQuestion.render({imageUrl: '/x.jpg'}, 0, false, {x: '"><script>', y: 'NaN'});
  assert.doesNotMatch(html, /<script/);
  assert.doesNotMatch(html, /aa-pin/);
});

test('pointFromClick converts a click to clamped fractions', () => {
  const w = hotspot();
  const rect = {left: 100, top: 50, width: 400, height: 200};
  assert.deepEqual(plain(w.AtlasHotspotQuestion._pointFromClick(300, 150, rect)), {x: 0.5, y: 0.5});
  assert.deepEqual(plain(w.AtlasHotspotQuestion._pointFromClick(0, 9999, rect)), {x: 0, y: 1});
  assert.equal(w.AtlasHotspotQuestion._pointFromClick(1, 1, {left: 0, top: 0, width: 0, height: 0}), null);
});

test('the module registers exactly the CSP actions the page allow-list expects', () => {
  const w = hotspot();
  assert.equal(typeof w.atlasHotspotPick, 'function');
  assert.equal(typeof w.atlasHotspotZoom, 'function');
});
