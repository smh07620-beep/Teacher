"""Collect candidate Tailwind class tokens from static/*.html and static/*.js into tokens.json."""
import glob
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).with_name("tokens.json")
pattern = re.compile(r"[A-Za-z0-9_:\-/\[\]\.%#()!,&>*=+]+")
tokens = set()
for name in glob.glob(str(ROOT / "static" / "*.html")) + glob.glob(str(ROOT / "static" / "*.js")):
    text = pathlib.Path(name).read_text(encoding="utf8", errors="ignore")
    for match in pattern.findall(text):
        match = match.strip(".,:")
        if 1 < len(match) < 70 and re.search(r"[a-z]", match):
            tokens.add(match)
OUT.write_text(json.dumps(sorted(tokens)), encoding="utf8")
print(len(tokens), "tokens ->", OUT)
