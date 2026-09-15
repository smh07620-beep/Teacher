from pathlib import Path


def replace(path, old, new, count=1):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


replace(
    "static/assessment-681.js",
    """  const api = async (url, options = {}) => {
    const key = await window.getAdminKey();
    if (!key) throw new Error('需要管理者驗證');
    const headers = {'X-Admin-Key': key, ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {})};
    const response = await fetch(url, {...options, headers});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || '操作失敗');
    return body;
  };
""",
    """  const loginRedirect = () => {
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = `/login?next=${next}`;
  };
  const api = async (url, options = {}) => {
    const headers = {...(options.headers || {})};
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {...options, headers, credentials:'same-origin'});
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) { loginRedirect(); throw new Error('登入已逾時，請重新登入。'); }
    if (response.status === 403) throw new Error(body.error || '此帳號沒有這項操作權限。');
    if (!response.ok) throw new Error(body.error || '操作失敗');
    return body;
  };
""",
)

for target in ("static/teaching.js", "teaching.js"):
    p = Path(target)
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    text = text.replace("    const key = await getAdminKey(); if (!key) return;\n", "")
    text = text.replace("const key = await getAdminKey(); if (!key) return;\n", "")
    text = text.replace("{headers:{'X-Admin-Key':key}}", "{credentials:'same-origin'}")
    text = text.replace(
        "headers:{'Content-Type':'application/json','X-Admin-Key':key}",
        "headers:{'Content-Type':'application/json'},credentials:'same-origin'",
    )
    p.write_text(text, encoding="utf-8")

replace(
    "static/rbac-ui-681.js",
    "const res = await fetch('/api/slides/admin', {headers: {'X-Admin-Key': 'rbac-session'}, cache: 'no-store'});",
    "const res = await fetch('/api/slides/admin', {credentials:'same-origin', cache: 'no-store'});",
)

replace(
    "static/system.html",
    '<script defer src="/system-admin.js?v=6502"></script>',
    '<script defer src="/system-admin.js?v=6502"></script>\n<script defer src="/sensitive-elevation-69.js?v=6900"></script>',
)

p = Path("FEATURE_EXPOSURE_681.md")
text = p.read_text(encoding="utf-8")
text = text.replace("elevated admin mutation", "session RBAC mutation")
text = text.replace(
    "| Admin elevation | elevation API | common `getAdminKey()` flow | eligible admin role + TTL | acceptance test | Usable |",
    "| Sensitive elevation | elevation API | automatic retry only for account/storage/backup/destructive system actions | privileged role + 15 min TTL | elevation boundary tests | Usable |",
)
p.write_text(text, encoding="utf-8")

Path(".github/workflows/session-rbac-cleanup-69.yml").unlink(missing_ok=True)
Path("scripts/session_rbac_cleanup_69.py").unlink(missing_ok=True)
