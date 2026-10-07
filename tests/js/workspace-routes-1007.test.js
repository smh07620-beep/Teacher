const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(extra = {}) {
  const window = {...extra};
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'workspace-routes-1007.js'), 'utf8'),
    {window},
  );
  return {window, R: window.AppWorkspaceRoutes};
}

test('aliases normalise and unknown names are rejected', () => {
  const {R} = load();
  assert.equal(R.normalize('questions'), 'assessment');
  assert.equal(R.normalize('pgy'), 'teacher');
  assert.equal(R.normalize('people'), 'people');
  assert.equal(R.has('exams'), true);
  assert.equal(R.has('nope'), false);
  assert.throws(() => R.url('nope'), /Unknown workspace/);
});

test('every workspace belongs to one of the product areas', () => {
  const {R} = load();
  for (const [key, meta] of Object.entries(R.WORKSPACES)) {
    assert.ok(R.AREAS[meta.area], key);
    assert.ok(meta.title && meta.summary && meta.icon, key);
  }
  assert.equal(R.areaLabel('word'), '教學');
  assert.equal(R.areaLabel('compliance'), '評量');
  assert.equal(R.areaLabel('worker'), '系統管理');
  assert.deepEqual([...R.systemNames()].sort(), ['audit', 'maintenance', 'people', 'system', 'worker']);
});

test('url keeps the legacy shape and adds persona only where needed', () => {
  const {R} = load();
  assert.equal(R.url('worker', {from: 'incident'}), '/system?admin=1&workspace=worker&persona=system&from=incident');
  assert.equal(
    R.url('assessment', {persona: 'teacher', from: 'incident', params: {focus: 'ai-question'}}),
    '/system?admin=1&workspace=assessment&persona=teacher&from=incident&focus=ai-question',
  );
  assert.equal(R.url('questions', {area: 'internal', group: 'grpBio'}), '/system?area=internal&group=grpBio&admin=1&workspace=questions');
});

test('open and show delegate to the shell and tolerate its absence', async () => {
  const calls = [];
  const {R} = load({
    openAdminWorkspace: name => { calls.push(['open', name]); return Promise.resolve('o'); },
    switchAdminWorkspace: (name, force) => { calls.push(['show', name, force]); return Promise.resolve('s'); },
  });
  assert.equal(await R.open('assessment'), 'o');
  assert.equal(await R.show('course-materials', true), 's');
  assert.deepEqual(calls, [['open', 'assessment'], ['show', 'course-materials', true]]);
  assert.throws(() => R.open('typo'), /Unknown workspace/);
  assert.equal(await load().R.open('assessment'), true);
});
