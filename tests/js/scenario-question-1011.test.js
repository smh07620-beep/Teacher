const test = require('node:test');
const assert = require('node:assert/strict');
const mod = require('../../static/learner-scenario-question-1011.js');

const q = { answerConfig: { steps: [
  { prompt: 'Q1 <b>', options: ['a', 'b<script>'] },
  { prompt: 'Q2', options: ['x', 'y', 'z'] },
] } };

test('renders every step with escaped text and csp actions only', () => {
  const html = mod.render(q, 3, false, [1, null]);
  assert.match(html, /scenarioPick\(3,0,1\)/);
  assert.match(html, /scenarioPick\(3,1,2\)/);
  assert.ok(!html.includes('<script>') && !html.includes('<b>'));
  assert.ok(!/\son[a-z]+=/i.test(html));
  assert.match(html, /name="scenario-3-0"[^>]* checked/);
  assert.match(html, /已作答 1 \/ 2/);
});

test('submitted view is read-only and keeps the choice', () => {
  const html = mod.render(q, 0, true, [0, 2]);
  assert.ok(!html.includes('scenarioPick('.concat('0,0,0)') + '"') || html.includes('disabled'));
  assert.equal((html.match(/disabled/g) || []).length, 5);
});

test('missing steps shows a teacher-facing notice, not a crash', () => {
  assert.match(mod.render({ answerConfig: {} }, 0, false, null), /小問題不見了/);
});

test('answered count ignores nulls and non-arrays', () => {
  assert.equal(mod._answeredCount([0, null, 2], 3), 2);
  assert.equal(mod._answeredCount(null, 3), 0);
});
