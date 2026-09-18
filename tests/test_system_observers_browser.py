import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class SystemObserverBrowserRegressionTests(unittest.TestCase):
    def test_convergence_observer_catches_in_place_rerender_and_coalesces(self):
        convergence = ROOT / 'static' / 'teacher-ux-convergence-72.js'
        harness = textwrap.dedent(
            r"""
            const fs = require('fs');
            const vm = require('vm');

            let observerCallback = null;
            let observedOptions = null;
            const rafQueue = [];
            let rafCalls = 0;

            function classList() {
              const values = new Set();
              return {
                contains(value) { return values.has(value); },
                add(...items) { items.forEach(item => values.add(item)); },
                remove(...items) { items.forEach(item => values.delete(item)); },
              };
            }

            function element(id = '') {
              return {
                nodeType: 1,
                id,
                dataset: {},
                textContent: '',
                tabIndex: 0,
                classList: classList(),
                parentElement: null,
                parentNode: null,
                getAttribute() { return ''; },
                setAttribute() {},
                removeAttribute() {},
                hasAttribute() { return false; },
                querySelector() { return null; },
                querySelectorAll() { return []; },
                matches() { return false; },
                closest() { return null; },
                appendChild() {},
                insertBefore() {},
              };
            }

            const courseWizardRoot = element('course-wizard-host');
            const pageBody = element('document-body');

            courseWizardRoot.matches = selector => selector.includes('[data-course-wizard-root]');

            global.window = global;
            global.document = {
              readyState: 'complete',
              body: pageBody,
              getElementById() { return null; },
              querySelector() { return null; },
              querySelectorAll() { return []; },
              createElement() { return element(); },
              addEventListener() {},
            };
            global.MutationObserver = class {
              constructor(callback) { observerCallback = callback; }
              observe(_target, options) { observedOptions = options; }
            };
            global.requestAnimationFrame = callback => {
              rafCalls += 1;
              rafQueue.push(callback);
              return rafCalls;
            };

            vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'), {
              filename: process.argv[1],
            });

            if (typeof observerCallback !== 'function') {
              throw new Error('convergence MutationObserver was not installed');
            }
            if (!observedOptions || observedOptions.childList !== true || observedOptions.subtree !== true) {
              throw new Error('convergence observer is not watching subtree child-list changes');
            }

            const unrelated = element('unrelated');
            observerCallback([{target: pageBody, addedNodes: [unrelated]}]);
            if (rafQueue.length !== 0) {
              throw new Error('unrelated DOM changes should not schedule convergence');
            }

            const rerenderedRow = element('rerendered-row');
            for (let i = 0; i < 100; i += 1) {
              observerCallback([{target: courseWizardRoot, addedNodes: [rerenderedRow]}]);
            }
            if (rafQueue.length !== 1 || rafCalls !== 1) {
              throw new Error(`expected one coalesced reconcile frame, got queue=${rafQueue.length}, calls=${rafCalls}`);
            }

            rafQueue.shift()();
            if (rafQueue.length !== 0) {
              throw new Error('reconcile unexpectedly scheduled another frame');
            }
            """
        )
        completed = subprocess.run(
            ['node', '-e', harness, str(convergence)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_retired_question_overlay_is_physically_removed(self):
        self.assertFalse(ROOT.joinpath('static/question-authoring-ux-71.js').exists())
        source = ROOT.joinpath('static/teacher-ux-convergence-72.js').read_text(encoding='utf-8')
        self.assertIn("interceptQuestionNext", source)


if __name__ == '__main__':
    unittest.main()
