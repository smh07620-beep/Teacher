/* Node-only behavior harness: exercises the loaded smart-learning script without a browser. */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

function element(id = '') {
  const listeners = {};
  return {
    id, dataset: {}, className: '', style: {}, readyState: 1, currentTime: 0, duration: 200,
    classList: { add() {}, remove() {} }, addEventListener(name, fn) { (listeners[name] ||= []).push(fn); },
    emit(name) { (listeners[name] || []).forEach(fn => fn({ target: this })); }, listenerCount(name) { return (listeners[name] || []).length; },
    removeAttribute(name) { if (name === 'src') this.src = ''; }, pause() {}, insertAdjacentElement(_where, child) { this.after = child; },
  };
}
function harness({ external = null, externalError = false } = {}) {
  const ids = {};
  const make = id => ids[id] ||= element(id);
  ['media-viewer-modal', 'media-video', 'media-audio', 'media-image', 'media-audio-wrap', 'media-viewer-title'].forEach(make);
  const windowListeners = {};
  const calls = [], progress = new Map(), posts = [];
  let jsonCalls = 0;
  const response = (ok, body) => ({ ok, json: async () => { jsonCalls += 1; return body; } });
  let fallback = 0;
  const window = {
    cachedSlidesList: [
      { id: 'youtube-a', title: 'A', viewerMode: 'video' }, { id: 'youtube-b', title: 'B', viewerMode: 'video' },
      { id: 'youtube-x', title: 'X', viewerMode: 'video' }, { id: 'direct-x', title: 'D', viewerMode: 'video' },
      { id: 'direct-a', title: 'Direct A', viewerMode: 'video' }, { id: 'direct-b', title: 'Direct B', viewerMode: 'video' },
      { id: 'uploaded-video-a', title: 'Upload video A', viewerMode: 'video' }, { id: 'uploaded-video-b', title: 'Upload video B', viewerMode: 'video' },
      { id: 'uploaded-audio-a', title: 'Upload audio A', viewerMode: 'audio' }, { id: 'uploaded-audio-b', title: 'Upload audio B', viewerMode: 'audio' },
      { id: 'fallback-x', title: 'F', viewerMode: 'video' },
    ],
    addEventListener(name, fn) { (windowListeners[name] ||= []).push(fn); },
    openMaterial: async () => { fallback += 1; }, closeSlideViewer() {}, closeMediaViewer() {}, goToSlidePage() {},
    console: { warn() {} },
  };
  const document = {
    body: { style: {} }, getElementById: id => ids[id] || null,
    createElement: tag => { const node = element(); let assigned = ''; Object.defineProperty(node, 'id', { get: () => assigned, set: value => { assigned = value; ids[value] = node; } }); node.tagName = tag; if (tag === 'iframe') node.contentWindow = { postMessage: (message, origin) => posts.push({ message: JSON.parse(message), origin }) }; return node; },
  };
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.includes('/external-media')) return externalError ? response(false, { error: 'missing' }) : response(true, { externalMedia: external });
    const match = url.match(/\/api\/learning-progress\/([^/?]+)/);
    if (match && options.method === 'PUT') { const body = JSON.parse(options.body); progress.set(match[1], body); return response(true, { ok: true }); }
    if (match) return response(true, progress.get(match[1]) || { position: {}, lastPositionSeconds: 0, watchedBuckets: [], duration: 0 });
    throw new Error('unexpected fetch ' + url);
  };
  const context = vm.createContext({ window, document, fetch, console: window.console, location: { origin: 'https://teacher.example' }, JSON, Set, Number, Math, Date, Error, encodeURIComponent, setTimeout: fn => fn() });
  vm.runInContext(fs.readFileSync('static/smart-learning-67.js', 'utf8'), context);
  const frame = () => ids['external-media-frame'];
  return {
    window, calls, progress, posts, frame, fallback: () => fallback, jsonCalls: () => jsonCalls,
    sendYoutube(info) { (windowListeners.message || []).forEach(fn => fn({ source: frame().contentWindow, origin: 'https://www.youtube-nocookie.com', data: JSON.stringify({ info }) })); },
    sendYoutubeEvent(event) { (windowListeners.message || []).forEach(fn => fn({ source: frame().contentWindow, origin: 'https://www.youtube-nocookie.com', data: JSON.stringify(event) })); },
    video: make('media-video'), audio: make('media-audio'),
  };
}
async function tick() { await Promise.resolve(); await Promise.resolve(); }

(async () => {
  const youtube = { provider: 'youtube', videoId: 'dQw4w9WgXcQ' };
  let h = harness({ external: youtube });
  await h.window.openMaterial('youtube-x');
  assert(h.calls.some(c => c.url.endsWith('/api/materials/youtube-x/external-media')), 'external metadata fetch occurs');
  assert(h.jsonCalls() > 0, 'external response is parsed with response.json()');
  assert(h.frame().src.includes('youtube-nocookie.com/embed/dQw4w9WgXcQ'), 'validated YouTube player opens');
  assert.equal(h.fallback(), 0, 'external player does not call legacy reader');

  h = harness({ external: youtube });
  await h.window.openMaterial('youtube-a'); h.sendYoutube({ currentTime: 25, duration: 200 }); await tick();
  await h.window.openMaterial('youtube-b'); h.sendYoutube({ currentTime: 45, duration: 200 }); await tick();
  assert(h.progress.has('youtube-a') && h.progress.has('youtube-b'), 'A and B both receive independent progress');
  assert.deepEqual([...h.progress.get('youtube-b').watchedBuckets], [4], 'B does not inherit A buckets');
  await h.window.openMaterial('youtube-a'); h.sendYoutube({ currentTime: 35, duration: 200 }); await tick();
  assert.deepEqual([...h.progress.get('youtube-a').watchedBuckets], [2, 3], 'A restores and extends only A progress');
  assert.equal(h.progress.get('youtube-a').completed, false, 'client never marks YouTube complete');
  assert.equal(h.progress.get('youtube-a').completionThreshold, .9, 'server receives coverage threshold');

  h = harness({ external: youtube });
  await h.window.teacher681SeekReviewSource({ materialId: 'youtube-x', timeStart: 120 });
  h.sendYoutubeEvent({ event: 'onReady' });
  assert(h.posts.some(p => p.message.func === 'seekTo' && p.message.args[0] === 120 && p.origin === 'https://www.youtube-nocookie.com'), 'YouTube ReviewSource waits for ready then seeks');

  h = harness({ external: { provider: 'direct', canonicalUrl: 'https://media.example.edu/lesson.mp4' } });
  await h.window.teacher681SeekReviewSource({ materialId: 'direct-x', timeStart: 45 });
  assert.equal(h.video.currentTime, 45, 'direct MP4 uses HTML5 seek');

  const direct = { provider: 'direct', canonicalUrl: 'https://media.example.edu/lesson.mp4' };
  h = harness({ external: direct });
  await h.window.openMaterial('direct-a'); h.video.currentTime = 25; h.video.duration = 200; h.video.emit('timeupdate'); await tick();
  await h.window.openMaterial('direct-b'); h.video.currentTime = 45; h.video.duration = 100; h.video.emit('timeupdate'); await tick();
  assert.deepEqual([...h.progress.get('direct-b').watchedBuckets], [4], 'direct B does not inherit A buckets');
  assert.equal(h.progress.get('direct-b').completed, false, 'direct HTML5 client never marks completion');
  await h.window.openMaterial('direct-a'); h.video.currentTime = 35; h.video.duration = 200; h.video.emit('timeupdate'); await tick();
  assert.deepEqual([...h.progress.get('direct-a').watchedBuckets], [2, 3], 'direct A restores and extends saved buckets');
  assert.equal(h.video.listenerCount('timeupdate'), 1, 'the shared direct video element has one timeupdate listener');
  assert.equal(h.video.listenerCount('pause'), 1, 'the shared direct video element has one pause listener');

  h = harness();
  await h.window.openMaterial('uploaded-video-a'); h.video.currentTime = 15; h.video.duration = 200; h.video.emit('timeupdate'); await tick();
  await h.window.openMaterial('uploaded-video-b'); h.video.currentTime = 45; h.video.duration = 100; h.video.emit('timeupdate'); await tick();
  assert.deepEqual([...h.progress.get('uploaded-video-b').watchedBuckets], [4], 'uploaded video B does not inherit A buckets');

  h = harness();
  await h.window.openMaterial('uploaded-audio-a'); h.audio.currentTime = 12; h.audio.duration = 200; h.audio.emit('timeupdate'); await tick();
  await h.window.openMaterial('uploaded-audio-b'); h.audio.currentTime = 32; h.audio.duration = 100; h.audio.emit('timeupdate'); await tick();
  assert.deepEqual([...h.progress.get('uploaded-audio-b').watchedBuckets], [3], 'uploaded audio B does not inherit A buckets');

  h = harness({ external: direct });
  await h.window.openMaterial('direct-a'); h.video.currentTime = 33; h.video.duration = 200;
  await h.window.openMaterial('direct-b'); await tick();
  assert.equal(h.progress.get('direct-a').lastPositionSeconds, 33, 'switch flushes unsaved HTML5 progress');

  h = harness({ external: direct });
  await h.window.openMaterial('direct-a'); h.video.currentTime = 51; h.video.duration = 200;
  h.window.closeMediaViewer(); await tick();
  assert.equal(h.progress.get('direct-a').lastPositionSeconds, 51, 'close flushes unsaved HTML5 progress');

  h = harness({ externalError: true });
  await h.window.openMaterial('fallback-x');
  assert.equal(h.fallback(), 1, 'metadata errors fall back to legacy reader without throwing');

  h = harness();
  await h.window.openMaterial('fallback-x');
  assert.equal(h.fallback(), 1, 'missing external metadata falls back to legacy reader without throwing');
  process.stdout.write('external media behavior: 10 scenarios passed\n');
})().catch(error => { console.error(error); process.exitCode = 1; });
