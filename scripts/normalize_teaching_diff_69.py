from pathlib import Path
import subprocess

subprocess.run(["git", "checkout", "origin/main", "--", "static/teaching.js", "teaching.js"], check=True)

p = Path("static/teaching.js")
data = p.read_bytes()
old_guard = b"    const key = await getAdminKey(); if (!key) return;\r\n"
if data.count(old_guard) < 2:
    raise SystemExit(f"expected at least two teaching AdminKey guards, got {data.count(old_guard)}")
data = data.replace(old_guard, b"")
old_read = b"{headers:{'X-Admin-Key':key}}"
if old_read not in data:
    raise SystemExit("teaching read AdminKey header marker not found")
data = data.replace(old_read, b"{credentials:'same-origin'}")
old_write = b"headers:{'Content-Type':'application/json','X-Admin-Key':key}"
if old_write not in data:
    raise SystemExit("teaching write AdminKey header marker not found")
data = data.replace(old_write, b"headers:{'Content-Type':'application/json'},credentials:'same-origin'")
p.write_bytes(data)

Path("scripts/normalize_teaching_diff_69.py").unlink(missing_ok=True)
Path(".github/workflows/normalize-teaching-diff-69.yml").unlink(missing_ok=True)
