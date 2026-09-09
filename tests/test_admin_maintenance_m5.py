"""M5 maintenance placement and scoped scrolling regressions."""
import json
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parents[1]

class Tree(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.stack = []
        self.parents = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        ident = attrs.get('id')
        if ident:
            self.parents[ident] = tuple(self.stack)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, ident))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

class AdminMaintenanceM5Tests(unittest.TestCase):
    def source(self, name):
        return ROOT.joinpath(name).read_text(encoding='utf-8')

    def run_card(self, role, host=True, duplicate=False):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for M5 behavioral regressions')
        script = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = SOURCE;
const role = ROLE, hasHost = HOST, duplicate = DUPLICATE;
const nodes = {'teacher64-backup': {}, 'teacher64-restore': {}};
let inserted = 0, authCalls = 0;
const host = {prepend(box) { inserted++; nodes[box.id] = box; }};
if (hasHost) nodes['admin-section-system'] = host;
if (duplicate) nodes['teacher64-maintenance'] = {};
const context = {
  window: {AppCore: {api: async path => {
    assert.equal(path, '/api/auth/me'); authCalls++;
    return {user: {role}};
  }}, location: {}},
  document: {
    readyState: 'complete',
    getElementById: id => nodes[id] || null,
    createElement: tag => {assert.equal(tag, 'section'); return {};},
    querySelector: () => {throw Error('Must not mount on general frontend');},
    body: {prepend: () => {throw Error('Must not mount on body');}}
  }, console
};
vm.runInNewContext(source, context);
setImmediate(() => {
  const expected = ['system_admin', 'education_admin'].includes(role) && hasHost && !duplicate;
  assert.equal(authCalls, 1);
  assert.equal(inserted, expected ? 1 : 0);
  if (expected) {
    assert.equal(typeof nodes['teacher64-restore'].onclick, 'function');
    nodes['teacher64-backup'].onclick();
    assert.equal(context.window.location.href, '/api/maintenance/backup');
  }
});
'''
        for key, value in {'SOURCE': self.source('static/maintenance-64.js'), 'ROLE': role,
                           'HOST': host, 'DUPLICATE': duplicate}.items():
            script = script.replace(key, json.dumps(value))
        result = subprocess.run([node, '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_admin_maintenance_mounts_only_in_system_settings(self):
        for role in ('education_admin', 'system_admin'):
            with self.subTest(role=role):
                self.run_card(role)
        self.assertIn("'/api/maintenance/restore'", self.source('static/maintenance-64.js'))

    def test_ordinary_roles_do_not_get_maintenance(self):
        for role in ('student', 'clinical_teacher', 'group_leader', 'auditor', ''):
            with self.subTest(role=role):
                self.run_card(role)

    def test_missing_settings_has_no_frontend_fallback(self):
        self.run_card('system_admin', host=False)

    def test_maintenance_is_not_duplicated(self):
        self.run_card('system_admin', duplicate=True)

    def check_scroll(self, section, last_control):
        tree = Tree(self.source('static/system.html'))
        self.assertIn(('div', 'admin-workspace-content'), tree.parents[section])
        self.assertIn(('div', section), tree.parents[last_control])
        css = self.source('static/admin.css').split('/* Teacher 6.6 M5:', 1)[1]
        rules = css.split('}', 1)
        self.assertIn(f'#admin-modal[data-section="{section.removeprefix("admin-section-")}"] > div', rules[0])
        for declaration in ('display: block;', 'height: auto !important;', 'max-height: 94dvh;', 'overflow-y: auto;'):
            self.assertIn(declaration, rules[0])
        self.assertIn('overflow: visible;', rules[1])
        self.assertNotIn('data-section="teacher"', css)

    def test_system_settings_scroll_includes_announcements(self):
        self.check_scroll('admin-section-system', 'admin-announcement-list')

    def test_people_scroll_includes_accounts_and_summary(self):
        self.check_scroll('admin-section-people', 'admin-people-body')
        tree = Tree(self.source('static/system.html'))
        self.assertIn(('div', 'admin-section-people'), tree.parents['admin-user-accounts-body'])

    def test_version_and_production_entrypoint_unchanged(self):
        self.assertEqual(self.source('VERSION').strip(), '6.5.0')
        self.assertIn('pgy_app:app', self.source('run_web.sh').splitlines()[-1])

    def test_updated_assets_have_fresh_cache_versions(self):
        self.assertIn('/maintenance-64.js?v=6605', self.source('pgy_frontend.py'))
        self.assertIn('/admin.css?v=6605', self.source('static/system.html'))
