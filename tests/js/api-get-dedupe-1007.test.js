// Behaviour tests for static/api-get-dedupe-1007.js, run with `node --test`.
// They load the REAL api-client.js (the middleware pipeline) and the real
// dedupe script into a sandbox that has a fake network.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const STATIC = path.join(__dirname, '..', '..', 'static');
const read = name => fs.readFileSync(path.join(STATIC, name), 'utf8');

function boot(handler) {
  const clock = {t: 1000};
  const calls = [];
  const window = {location: new URL('https://teacher.test/system')};
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    const method = String(init.method || 'GET').toUpperCase();
    calls.push(`${method} ${url}`);
    await new Promise(resolve => setImmediate(resolve));
    return handler({url, method, init, count: calls.length});
  };
  const sandbox = {
    window, Response, Request, Headers, URL, console,
    Date: {now: () => clock.t},
    setTimeout, clearTimeout, setImmediate,
  };
  vm.createContext(sandbox);
  vm.runInContext(read('api-client.js'), sandbox);
  vm.runInContext(read('api-get-dedupe-1007.js'), sandbox);
  return {window, calls, clock, fetch: (...args) => window.fetch(...args), dedupe: window.AppApiGetDedupe};
}

// Values created inside the vm sandbox belong to another realm; compare plain copies.
const plain = value => JSON.parse(JSON.stringify(value));
const json = body => new Response(JSON.stringify(body), {status: 200, headers: {'content-type': 'application/json'}});

test('concurrent identical GETs make one network call and every caller can read the body', async () => {
  const app = boot(() => json({ok: true}));
  const replies = await Promise.all([1, 2, 3, 4].map(() => app.fetch('/api/courses?area=internal&group=grpBio')));
  assert.equal(app.calls.length, 1);
  for (const reply of replies) assert.deepEqual(await reply.json(), {ok: true});
  assert.deepEqual(plain(app.dedupe.stats()), {network: 1, shared: 3, cleared: 0, size: 1});
});

test('query order does not matter but different queries are separate requests', async () => {
  const app = boot(() => json([]));
  await Promise.all([
    app.fetch('/api/courses?area=internal&group=grpBio'),
    app.fetch('/api/courses?group=grpBio&area=internal'),
    app.fetch('/api/courses?area=internal&group=grpHema'),
  ]);
  assert.equal(app.calls.length, 2);
});

test('a finished answer is reused for a few seconds, then fetched again', async () => {
  const app = boot(() => json({n: 1}));
  await app.fetch('/api/learning-progress');
  await app.fetch('/api/learning-progress');
  assert.equal(app.calls.length, 1);
  app.clock.t += 2999;
  await app.fetch('/api/learning-progress');
  assert.equal(app.calls.length, 1);
  app.clock.t += 2;
  await app.fetch('/api/learning-progress');
  assert.equal(app.calls.length, 2);
});

test('any API write clears the shared answers so nothing stale is shown', async () => {
  let version = 1;
  const app = boot(({method}) => (method === 'GET' ? json({version}) : json({saved: true})));
  assert.deepEqual(await (await app.fetch('/api/courses?area=internal')).json(), {version: 1});
  version = 2;
  await app.fetch('/api/courses', {method: 'POST', body: '{}'});
  assert.deepEqual(await (await app.fetch('/api/courses?area=internal')).json(), {version: 2});
  assert.equal(app.calls.filter(call => call.startsWith('GET')).length, 2);
});

test('a failed write also clears (the change may have partly happened)', async () => {
  const app = boot(({method}) => (method === 'GET' ? json({}) : new Response('{}', {status: 500})));
  await app.fetch('/api/slides?area=internal');
  await app.fetch('/api/slides/x', {method: 'PUT'});
  await app.fetch('/api/slides?area=internal');
  assert.equal(app.calls.filter(call => call.startsWith('GET')).length, 2);
});

test('endpoints outside the allow-list are never shared', async () => {
  const app = boot(() => json({}));
  await Promise.all([app.fetch('/api/users'), app.fetch('/api/users'), app.fetch('/api/materials/jobs/1'), app.fetch('/api/materials/jobs/1')]);
  assert.equal(app.calls.length, 4);
});

test('callers that ask for fresh data (no-store) share a request that is in flight right now', async () => {
  const app = boot(() => json({}));
  await Promise.all([1, 2, 3].map(() => app.fetch('/api/training-command-center/progress', {cache: 'no-store'})));
  assert.equal(app.calls.length, 1);
});

test('a no-store caller never gets an answer that already finished (refresh buttons stay honest)', async () => {
  const app = boot(() => json({}));
  await app.fetch('/api/courses', {cache: 'no-store'});
  await app.fetch('/api/courses', {cache: 'no-store'});
  assert.equal(app.calls.length, 2);
  // ...but an ordinary caller may still reuse the answer a no-store caller just fetched.
  await app.fetch('/api/courses');
  assert.equal(app.calls.length, 2);
});

test('a caller with an AbortSignal is never shared, so cancelling one cannot break another', async () => {
  const app = boot(() => json({}));
  const controller = new AbortController();
  await Promise.all([app.fetch('/api/courses', {signal: controller.signal}), app.fetch('/api/courses')]);
  assert.equal(app.calls.length, 2);
});

test('errors are shared with callers already waiting but never kept for later', async () => {
  let fail = true;
  const app = boot(() => (fail ? new Response('{"error":"x"}', {status: 500}) : json({ok: true})));
  const first = await Promise.all([app.fetch('/api/auth/me'), app.fetch('/api/auth/me')]);
  assert.deepEqual(first.map(reply => reply.status), [500, 500]);
  assert.equal(app.calls.length, 1);
  fail = false;
  const retry = await app.fetch('/api/auth/me');
  assert.equal(retry.status, 200);
  assert.equal(app.calls.length, 2);
});

test('a network failure is not remembered', async () => {
  let down = true;
  const app = boot(() => {
    if (down) throw new Error('offline');
    return json({ok: true});
  });
  await assert.rejects(app.fetch('/api/auth/profile'), /offline/);
  down = false;
  assert.equal((await app.fetch('/api/auth/profile')).status, 200);
  assert.equal(app.calls.length, 2);
});

test('cross-origin requests are left alone', async () => {
  const app = boot(() => json({}));
  await app.fetch('https://other.test/api/courses');
  await app.fetch('https://other.test/api/courses');
  assert.equal(app.calls.length, 2);
});

test('empty-body answers (204) still work for every sharer', async () => {
  const app = boot(() => new Response(null, {status: 204}));
  const replies = await Promise.all([app.fetch('/api/learning-progress'), app.fetch('/api/learning-progress')]);
  assert.deepEqual(replies.map(reply => reply.status), [204, 204]);
  assert.equal(app.calls.length, 1);
});

test('registers as middleware before the other features and never reassigns window.fetch itself', () => {
  const app = boot(() => json({}));
  assert.deepEqual(plain(app.window.AppApiClient.middlewareNames()), ['api-get-dedupe-1007']);
  assert.doesNotMatch(read('api-get-dedupe-1007.js').replace(/\s/g, ''), /window\.fetch=|global\.fetch=/);
});
