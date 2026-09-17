from pathlib import Path
import ast
import re
import textwrap

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return ROOT.joinpath(path).read_bytes().decode("utf-8")


def write(path, text):
    ROOT.joinpath(path).write_bytes(text.encode("utf-8"))


def route_literal(dec):
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    if dec.func.attr not in {"get", "post", "put", "patch", "delete", "route"}:
        return None
    if not dec.args or not isinstance(dec.args[0], ast.Constant):
        return None
    return dec.args[0].value if isinstance(dec.args[0].value, str) else None


def remove_python_routes(path, endpoints):
    text = read(path)
    tree = ast.parse(text)
    ranges = []
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        matched = False
        start = node.lineno
        for dec in node.decorator_list:
            endpoint = route_literal(dec)
            if endpoint in endpoints:
                found.add(endpoint)
                start = min(start, dec.lineno)
                matched = True
        if matched:
            ranges.append((start, node.end_lineno))
    missing = set(endpoints) - found
    assert not missing, (path, "missing route definitions", sorted(missing))
    lines = text.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start - 1 : end]
    result = "".join(lines)
    ast.parse(result)
    write(path, result)


def matching_brace(text, brace_pos):
    depth = 0
    quote = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace_pos
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
        elif block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 1
        elif quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
        else:
            if ch == "/" and nxt == "/":
                line_comment = True
                i += 1
            elif ch == "/" and nxt == "*":
                block_comment = True
                i += 1
            elif ch in "'\"`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise AssertionError("unmatched JS brace")


def pop_js_function(text, name):
    pat = re.compile(rf"(?m)^(?:async\s+)?function\s+{re.escape(name)}\s*\(")
    matches = list(pat.finditer(text))
    assert len(matches) == 1, (name, "expected exactly one top-level function", len(matches))
    match = matches[0]
    brace = text.find("{", match.end())
    assert brace >= 0
    end = matching_brace(text, brace) + 1
    while end < len(text) and text[end] in "\r\n":
        end += 1
    return text[match.start() : end], text[: match.start()] + text[end:]


def append_before_iife(path, block):
    text = read(path)
    marker = "})();"
    idx = text.rfind(marker)
    assert idx >= 0, (path, "missing IIFE terminator")
    newline = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\r\n", "\n").replace("\n", newline)
    write(path, text[:idx] + block.rstrip() + newline + text[idx:])


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, (label, "expected one occurrence", count)
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 1) Retire only the HTTP routes that are actually obsolete.
#    preview_docx_atlas() stays: atlas_70.py imports it as the canonical parser.
# -----------------------------------------------------------------------------
remove_python_routes(
    "smart_learning_67.py",
    {
        "/api/docx-atlas-preview/<material_id>",
        "/api/learning-analytics",
        "/api/media-processing/capability",
    },
)
smart = read("smart_learning_67.py")
assert "def preview_docx_atlas(" in smart
for symbol in ("ffmpeg_capability", "libreoffice_capability", "worker_architecture"):
    assert len(re.findall(rf"\b{symbol}\b", smart)) == 1, (symbol, "unexpected surviving use")
smart, n = re.subn(
    r"^from media_processing_67 import ffmpeg_capability, libreoffice_capability, worker_architecture\r?\n",
    "",
    smart,
    count=1,
    flags=re.M,
)
assert n == 1
ast.parse(smart)
write("smart_learning_67.py", smart)

remove_python_routes(
    "app.py",
    {
        "/api/groups",
        "/api/training-areas",
        "/api/admin/background-jobs/status",
    },
)

# -----------------------------------------------------------------------------
# 2) Physically move remaining product UI owners out of system-admin.js.
# -----------------------------------------------------------------------------
legacy = read("static/system-admin.js")
legacy = replace_once(
    legacy,
    "/* V5.9.0 · 後台內容、題庫、帳號與系統管理 */",
    "/* Final convergence compatibility shell: shared state + DOCX fallback only. */",
    "legacy header",
)

move_plan = {
    "static/admin-course-material.js": [
        "adminMaterialTypeBadge",
        "adminHubMaterialRow",
        "renderAdminCourseMaterialHub",
    ],
    "static/admin-question-bank.js": [
        "setAdminQuizSyncStatus",
        "adminHasExpandedQuestionEditor",
        "quizCategoryCardHTML",
        "updateQuizWorkspacePresentation",
    ],
    "static/admin-people.js": [
        "renderAdminUserAccounts",
        "createAdminUserAccount",
        "renderAdminPeople",
    ],
    "static/admin-system.js": [
        "systemStatusCard",
        "renderAdminSystemStatus",
    ],
    "static/admin-exam-settings.js": ["difficultyLabel"],
}

moved = {}
for target, names in move_plan.items():
    moved[target] = []
    for name in names:
        source, legacy = pop_js_function(legacy, name)
        moved[target].append((name, source))

people_state_pattern = re.compile(
    r"let adminUserAccountsCache=\[\];\r?\nconst ADMIN_USER_AREA_LABELS=\{internal:'院內',pgy:'PGY'\};\r?\n"
)
legacy, n = people_state_pattern.subn("", legacy, count=1)
assert n == 1
people = read("static/admin-people.js")
use_strict = "  'use strict';"
assert use_strict in people
people = people.replace(
    use_strict,
    use_strict
    + "\n\n  let adminUserAccountsCache=[];"
    + "\n  const ADMIN_USER_AREA_LABELS={internal:'院內',pgy:'PGY'};",
    1,
)
write("static/admin-people.js", people)

# Dead/duplicated legacy functions with already-proven canonical owners.
for name in (
    "aiMaterialKind",
    "_aiPickerState",
    "_aiMaterialSearchText",
    "adminPayloadFromQuestionEditor",
    "adminBatchQuestionPatch",
    "renderCategoryChart",
    "resetCurrentQuiz",
    "toggleSopModal",
):
    _source, legacy = pop_js_function(legacy, name)

for declaration, symbol in (
    ("const questionActionBusy=new Set();", "questionActionBusy"),
    ("const questionBulkBusy=new Set();", "questionBulkBusy"),
    ("let materialJobsRefreshTimer=null;", "materialJobsRefreshTimer"),
):
    if declaration in legacy:
        assert legacy.count(symbol) == 1, (symbol, "still referenced in legacy bundle")
        legacy = legacy.replace(declaration, "", 1)

write("static/system-admin.js", legacy)

for target, items in moved.items():
    block = "\n  // Final convergence: canonical owner migrated from system-admin.js.\n"
    for _name, source in items:
        block += textwrap.indent(source.rstrip(), "  ") + "\n\n"
    for name, _source in items:
        block += f"  window.{name}={name};\n"
    append_before_iife(target, block)

# -----------------------------------------------------------------------------
# 3) Review-source augmentation wraps the canonical question payload owner.
# -----------------------------------------------------------------------------
review = read("static/review-links-66.js")
assert "adminPayloadFromQuestionEditor" in review
review = review.replace("adminPayloadFromQuestionEditor", "window.adminBuildQuestionPayload")
assert "adminPayloadFromQuestionEditor" not in review
write("static/review-links-66.js", review)

frontend = read("pgy_frontend.py")
early = (
    '            if "/review-links-66.js" not in html:\n'
    '                body_assets.append(\'<script defer src="/review-links-66.js?v=6604"></script>\')\n'
)
frontend = replace_once(frontend, early, "", "early review-links injection")
action_marker = (
    '            if "/admin-question-actions.js" not in html:\n'
    '                body_assets.append(\'<script defer src="/admin-question-actions.js?v=7120"></script>\')\n'
)
review_after_actions = (
    action_marker
    + '            if "/review-links-66.js" not in html:\n'
    + '                body_assets.append(\'<script defer src="/review-links-66.js?v=7400"></script>\')\n'
)
frontend = replace_once(frontend, action_marker, review_after_actions, "question actions marker")
ast.parse(frontend)
write("pgy_frontend.py", frontend)

# -----------------------------------------------------------------------------
# 4) Wire backend-complete features into their canonical frontend surfaces.
# -----------------------------------------------------------------------------
actions = read("static/admin-question-actions.js")
bulk_delete_fn = re.search(
    r"  window\.adminBulkDeleteQuestions = async function\(catId\)\{[\s\S]*?\n  \};",
    actions,
)
assert bulk_delete_fn, "adminBulkDeleteQuestions not found"
bulk_text = bulk_delete_fn.group(0)
loop = re.search(
    r"      for\(const id of ids\)\{\n        const r=await fetch\(`/api/quiz-questions/\$\{encodeURIComponent\(id\)\}`,\{method:'DELETE',headers:\{'X-Admin-Key':key\}\}\);\n        const d=await r\.json\(\)\.catch\(\(\)=>\(\{\}\)\); if\(!r\.ok\) throw new Error\(d\.error\|\|'批次刪除失敗'\);\n      \}",
    bulk_text,
)
assert loop, "legacy per-row bulk delete loop not found"
replacement = (
    "      const r=await fetch('/api/quiz-questions/batch-delete',"
    "{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},"
    "body:JSON.stringify({ids})});\n"
    "      const d=await r.json().catch(()=>({})); "
    "if(!r.ok) throw new Error(d.error||'批次刪除失敗');"
)
new_bulk = bulk_text[: loop.start()] + replacement + bulk_text[loop.end() :]
actions = actions[: bulk_delete_fn.start()] + new_bulk + actions[bulk_delete_fn.end() :]
assert "/api/quiz-questions/batch-delete" in actions
write("static/admin-question-actions.js", actions)

workspace = read("static/workspace-shell-70.js")
audit_start = "    auditPanel.innerHTML = `\n      <section"
assert audit_start in workspace
workspace = workspace.replace(
    audit_start,
    """    auditPanel.innerHTML = `
      <section class=\"bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3\">
        <div><h4 class=\"font-black text-slate-900\">🛡️ 安全狀態</h4><p class=\"mt-1 text-xs text-slate-500\">只顯示安全策略是否啟用，不回傳或顯示任何密鑰。</p></div>
        <div id=\"security-status-70\" class=\"grid sm:grid-cols-2 lg:grid-cols-3 gap-2\"><div class=\"text-xs text-slate-400\">讀取安全狀態中…</div></div>
      </section>
      <section""",
    1,
)
audit_vars = (
    "    const status = document.getElementById('audit-status-70');\n"
    "    const body = document.getElementById('audit-body-70');\n"
    "    try {"
)
assert audit_vars in workspace
security_fetch = """    const status = document.getElementById('audit-status-70');
    const body = document.getElementById('audit-body-70');
    const securityHost = document.getElementById('security-status-70');
    try {
      const securityResponse = await fetch('/api/security/status', {credentials: 'same-origin', cache: 'no-store'});
      const security = await securityResponse.json().catch(() => ({}));
      if (!securityResponse.ok) throw new Error(security.error || `讀取失敗（${securityResponse.status}）`);
      const chip = (label, value, good=true) => `<div class=\"rounded-xl border ${good?'border-emerald-200 bg-emerald-50':'border-amber-200 bg-amber-50'} p-3\"><div class=\"text-[11px] font-bold text-slate-500\">${esc(label)}</div><div class=\"mt-1 text-sm font-black text-slate-900\">${esc(value)}</div></div>`;
      securityHost.innerHTML = [
        chip('Session 期限', `${Number(security.sessionHours||0)} 小時`, Number(security.sessionHours||0)>0),
        chip('Secure Cookie', security.secureCookie?'已啟用':'未啟用', !!security.secureCookie),
        chip('CSRF Origin 檢查', security.csrfOriginCheck?'已啟用':'未啟用', !!security.csrfOriginCheck),
        chip('登入失敗限制', `${Number(security.loginRateLimitMaxAttempts||0)} 次`, Number(security.loginRateLimitMaxAttempts||0)>0),
        chip('CSP', security.cspEnforced?'強制模式':'Report-Only', !!security.cspEnforced),
        chip('Production Secret', security.productionSecretRequired?'正式環境必填':'非強制', !!security.productionSecretRequired),
      ].join('');
    } catch (securityError) {
      if (securityHost) securityHost.innerHTML = `<div class=\"sm:col-span-2 lg:col-span-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800\">⚠️ ${esc(securityError.message)}</div>`;
    }
    try {"""
workspace = workspace.replace(audit_vars, security_fetch, 1)
write("static/workspace-shell-70.js", workspace)

# -----------------------------------------------------------------------------
# 5) Remove public dead navigation markup/compat and unify cache key.
# -----------------------------------------------------------------------------
public_pages = ["static/index.html", "static/area-internal.html", "static/area-pgy.html"]
header_removed = 0
bottom_removed = 0
for path in public_pages:
    html = read(path)
    html, n = re.subn(
        r'<a\b[^>]*class="[^"]*\bv575-manage-direct\b[^"]*"[^>]*>教學管理</a>',
        "",
        html,
    )
    header_removed += n
    html = re.sub(r"/portal-v56\.js\?v=\d+", "/portal-v56.js?v=7400", html)
    if path in {"static/area-internal.html", "static/area-pgy.html"}:
        html, n = re.subn(
            r'<a\b[^>]*href="/system\?[^"]*admin=1[^"]*"[^>]*>⚙<span>管理</span></a>',
            "",
            html,
        )
        bottom_removed += n
    write(path, html)
assert header_removed == 3, ("public management header links", header_removed)
assert bottom_removed == 2, ("public direct bottom management links", bottom_removed)

nav = read("static/portal-navigation-73.js")ndead = "    document.querySelectorAll('.v575-manage-direct').forEach(entry=>entry.remove());\n"
assert ndead in nav
nav = nav.replace(ndead, "", 1)
write("static/portal-navigation-73.js", nav)

portal = read("static/portal-v56.js")
handler = re.compile(
    r"\n  // Public \"教學管理\" navigation opens the area catalog\.[\s\S]*?\n  \$\$\('\.v575-manage-direct'\)\.forEach\(link=>link\.addEventListener\('click',event=>\{[\s\S]*?\n  \}\)\);\n"
)
portal, n = handler.subn("\n", portal, count=1)
assert n == 1, "dead public management handler not found"
write("static/portal-v56.js", portal)

v575 = read("static/v575.css")
lines = v575.splitlines(keepends=True)
kept = []
removed_css = 0
for line in lines:
    if "body.portal-v56 .v575-home-nav .v575-manage-direct{" in line or "body.portal-v56 .v575-home-nav .v575-manage-direct:hover{" in line:
        removed_css += 1
        continue
    kept.append(line)
assert removed_css == 2, ("v575 public management css rules", removed_css)
write("static/v575.css", "".join(kept))

teaching_css = ROOT / "static/teaching.css"
assert teaching_css.exists()
assert ".teaching-welcome" in read("static/learner.css")
assert ".teaching-plan" in read("static/learner.css")
teaching_css.unlink()

# -----------------------------------------------------------------------------
# 6) Update old tests that intentionally froze the now-retired contracts.
# -----------------------------------------------------------------------------
nav_test = read("tests/test_teacher_68_material_navigation.py")
old = '''    def test_portal_navigation_uses_area_catalog_without_group_hardcoding(self):
        portal = self.source("static/portal-v56.js")
        self.assertIn("$$('.v575-manage-direct')", portal)
        self.assertIn("location.pathname==='/pgy'?'/pgy':'/internal'", portal)
        self.assertIn("['教材','/internal']", portal)
'''
new = '''    def test_portal_navigation_has_no_dead_public_management_handler(self):
        portal = self.source("static/portal-v56.js")
        self.assertNotIn("$$('.v575-manage-direct')", portal)
        self.assertNotIn("location.pathname==='/pgy'?'/pgy':'/internal'", portal)
        self.assertIn("['教材','/internal']", portal)
'''
nav_test = replace_once(nav_test, old, new, "material navigation regression")
write("tests/test_teacher_68_material_navigation.py", nav_test)

smart_test = read("tests/test_smart_learning_67.py")
old = '''    def test_docx_import_is_preview_first(self):
        source=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        self.assertIn('preview_docx_atlas',source)
        self.assertIn('publishRequired',source)
        self.assertIn('SmartArt',source)
'''
new = '''    def test_docx_import_uses_one_canonical_preview_parser(self):
        source=ROOT.joinpath('smart_learning_67.py').read_text(encoding='utf-8')
        atlas=ROOT.joinpath('atlas_70.py').read_text(encoding='utf-8')
        self.assertIn('def preview_docx_atlas',source)
        self.assertNotIn('/api/docx-atlas-preview/',source)
        self.assertIn('from smart_learning_67 import preview_docx_atlas',atlas)
        self.assertIn('SmartArt',source)
'''
smart_test = replace_once(smart_test, old, new, "smart learning docx regression")
write("tests/test_smart_learning_67.py", smart_test)

r2_test = read("tests/test_r2_free_budget_guard.py")
r2_test = replace_once(
    r2_test,
    '        self.assertIn(client.get("/api/admin/background-jobs/status").status_code, {401, 403, 503})',
    '        self.assertIn(client.get("/api/material-jobs").status_code, {401, 403, 503})',
    "r2 protected status route",
)
write("tests/test_r2_free_budget_guard.py", r2_test)

stage3 = read("tests/test_final_convergence_stage3_cleanup.py")
needle = "    def test_admin_key_remains_session_rbac_compatibility_only(self):\n"
assert needle in stage3
case = '''    def test_legacy_bundle_no_longer_owns_migrated_product_ui(self):
        for forbidden in (
            "function renderAdminCourseMaterialHub(",
            "function quizCategoryCardHTML(",
            "function renderAdminUserAccounts(",
            "function renderAdminPeople(",
            "function renderAdminSystemStatus(",
            "function renderCategoryChart(",
            "function resetCurrentQuiz(",
            "function toggleSopModal(",
            "function adminPayloadFromQuestionEditor(",
        ):
            self.assertNotIn(forbidden, self.legacy)

'''
stage3 = stage3.replace(needle, case + needle, 1)
write("tests/test_final_convergence_stage3_cleanup.py", stage3)

final_test = '''from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalSkeletonCleanup74Tests(unittest.TestCase):
    def source(self, path):
        return ROOT.joinpath(path).read_text(encoding="utf-8")

    def test_public_portals_have_no_dead_v575_management_markup(self):
        for path in ("static/index.html", "static/area-internal.html", "static/area-pgy.html"):
            html = self.source(path)
            self.assertNotIn('class="v575-manage-direct"', html)
            self.assertIn('/portal-v56.js?v=7400', html)
        self.assertIn('data-pgy-management-only', self.source('static/area-pgy.html'))
        self.assertIn('class="v575-manage-direct"', self.source('static/system.html'))

    def test_public_navigation_no_longer_carries_dead_management_compat(self):
        portal = self.source('static/portal-v56.js')
        nav = self.source('static/portal-navigation-73.js')
        self.assertNotIn("$$('.v575-manage-direct')", portal)
        self.assertNotIn("document.querySelectorAll('.v575-manage-direct').forEach(entry=>entry.remove())", nav)

    def test_teaching_css_is_retired_and_learner_css_owns_classes(self):
        self.assertFalse(ROOT.joinpath('static/teaching.css').exists())
        learner = self.source('static/learner.css')
        self.assertIn('.teaching-welcome', learner)
        self.assertIn('.teaching-plan', learner)

    def test_obsolete_backend_routes_are_physically_retired(self):
        app = self.source('app.py')
        smart = self.source('smart_learning_67.py')
        for route in ('/api/groups', '/api/training-areas', '/api/admin/background-jobs/status'):
            self.assertNotIn(route, app)
        for route in ('/api/docx-atlas-preview/', '/api/learning-analytics', '/api/media-processing/capability'):
            self.assertNotIn(route, smart)
        self.assertIn('def preview_docx_atlas(', smart)
        self.assertIn('/api/atlas/import-docx/', self.source('atlas_70.py'))
        self.assertIn('/api/training-command-center/learning-analytics', self.source('teacher_app/command_center.py'))
        self.assertIn('/api/material-jobs', app)

    def test_completed_backend_features_have_canonical_frontend_consumers(self):
        actions = self.source('static/admin-question-actions.js')
        workspace = self.source('static/workspace-shell-70.js')
        self.assertIn('/api/quiz-questions/batch-delete', actions)
        self.assertIn('/api/security/status', workspace)
        self.assertIn('security-status-70', workspace)

    def test_review_links_wrap_canonical_question_payload_owner(self):
        review = self.source('static/review-links-66.js')
        frontend = self.source('pgy_frontend.py')
        self.assertIn('window.adminBuildQuestionPayload', review)
        self.assertNotIn('adminPayloadFromQuestionEditor', review)
        self.assertGreater(frontend.index('/review-links-66.js?v=7400'), frontend.index('/admin-question-actions.js?v=7120'))

    def test_legacy_admin_ownership_moved_to_canonical_modules(self):
        legacy = self.source('static/system-admin.js')
        owners = {
            'static/admin-course-material.js': 'renderAdminCourseMaterialHub',
            'static/admin-question-bank.js': 'quizCategoryCardHTML',
            'static/admin-people.js': 'renderAdminUserAccounts',
            'static/admin-system.js': 'renderAdminSystemStatus',
            'static/admin-exam-settings.js': 'difficultyLabel',
            'static/learner-result-chart.js': 'renderCategoryChart',
            'static/learner-exam-controls.js': 'resetCurrentQuiz',
        }
        for path, symbol in owners.items():
            self.assertIn(symbol, self.source(path))
            self.assertNotIn(f'function {symbol}(', legacy)
        self.assertIn('async function getAdminKey()', legacy)
        self.assertIn('let cachedTemplateBuffer = null', legacy)
        self.assertIn('let pendingExportRecordIndex = null', legacy)


if __name__ == '__main__':
    unittest.main()
'''
write("tests/test_final_skeleton_cleanup_74.py", final_test)

# -----------------------------------------------------------------------------
# 7) Record the finalized ownership policy.
# -----------------------------------------------------------------------------
architecture = read("ARCHITECTURE_FINAL_CONVERGENCE.md")
appendix = '''
## Final skeleton cleanup (7.4 RC)

- Public `/`, `/internal`, and `/pgy` pages no longer carry the retired `v575-manage-direct` markup; role-aware management entries remain the only public-to-management path.
- `system-admin.js` no longer owns course/material hub rendering, question-bank presentation, people management, system health UI, or learner controls. Those implementations live in their canonical extracted modules.
- `getAdminKey()` remains only as the session-RBAC compatibility header seam, and local DOCX fallback state remains intentionally preserved.
- Obsolete unconsumed HTTP routes retired here: legacy DOCX Atlas preview, legacy learning analytics, standalone media capability, legacy background-job status, and unused groups/training-areas catalog APIs. The shared `preview_docx_atlas()` parser remains because the canonical Atlas DOCX wizard imports it directly.
- Supported replacements are the Atlas DOCX import wizard, training command-center analytics, and `/api/material-jobs`. Public group cards remain static presentation data for this RC; a data-driven catalog is a separate future change rather than a release-candidate refactor.
- `/api/quiz-questions/batch-delete` and `/api/security/status` now have canonical frontend consumers.
- `static/teaching.css` is retired; `static/learner.css` is the single owner of the teaching layout classes.
'''
if "## Final skeleton cleanup (7.4 RC)" not in architecture:
    architecture = architecture.rstrip() + "\n" + appendix + "\n"
write("ARCHITECTURE_FINAL_CONVERGENCE.md", architecture)

audit = read("RUNTIME_CONVERGENCE_AUDIT_74.md")
audit_appendix = '''
## Final skeleton cleanup result

The post-audit cleanup physically removes dead public navigation markup, retires obsolete unconsumed HTTP routes, connects batch-delete and security-status to canonical frontend owners, retires `teaching.css`, unifies `portal-v56.js` cache keys, and migrates the remaining course/question/people/system UI owners out of `system-admin.js`. The compatibility shell deliberately retains shared cache/state helpers, `getAdminKey()` as a non-secret session-RBAC header seam, and the tested local DOCX fallback only.
'''
if "## Final skeleton cleanup result" not in audit:
    audit = audit.rstrip() + "\n" + audit_appendix + "\n"
write("RUNTIME_CONVERGENCE_AUDIT_74.md", audit)

# -----------------------------------------------------------------------------
# 8) Hard stop on incomplete/over-broad cleanup.
# -----------------------------------------------------------------------------
legacy = read("static/system-admin.js")
for forbidden in (
    "function renderAdminCourseMaterialHub(",
    "function quizCategoryCardHTML(",
    "function renderAdminUserAccounts(",
    "function renderAdminPeople(",
    "function renderAdminSystemStatus(",
    "function renderCategoryChart(",
    "function resetCurrentQuiz(",
    "function toggleSopModal(",
    "function adminPayloadFromQuestionEditor(",
    "function aiMaterialKind(",
):
    assert forbidden not in legacy, forbidden
assert "async function getAdminKey()" in legacy
assert "return 'rbac-session';" in legacy
assert "let cachedTemplateBuffer = null" in legacy
assert "let pendingExportRecordIndex = null" in legacy
assert "docx-template-input" in legacy
assert "/api/quiz-questions/batch-delete" in read("static/admin-question-actions.js")
assert "/api/security/status" in read("static/workspace-shell-70.js")
for path in public_pages:
    assert "/portal-v56.js?v=7400" in read(path)
    assert 'class="v575-manage-direct"' not in read(path)
assert 'class="v575-manage-direct"' in read("static/system.html")
print("final skeleton cleanup patch applied with all guards satisfied")
