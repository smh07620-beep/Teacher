"""Phase 6 frame-renderer chain for approved PowerPoint video production.

The local AI Worker prefers the exact desktop PowerPoint renderer when it works,
then LibreOffice headless, and finally lets the caller use the existing safe
text renderer.  Web never executes these desktop binaries.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

POWERPOINT = "powerpoint-com"
LIBREOFFICE = "libreoffice-headless"
SAFE_FALLBACK = "text-fallback"
RENDERER_ORDER = (POWERPOINT, LIBREOFFICE, SAFE_FALLBACK)


def _enabled(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "true" if default else "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _powershell() -> str:
    if os.name != "nt" or not _enabled("AI_VIDEO_POWERPOINT_COM_ENABLED", True):
        return ""
    return shutil.which("powershell.exe") or shutil.which("pwsh.exe") or ""


def _libreoffice() -> str:
    override = str(os.environ.get("AI_VIDEO_LIBREOFFICE_PATH") or "").strip()
    candidates = [override] if override else []
    for command in ("soffice.exe", "soffice", "libreoffice"):
        found = shutil.which(command)
        if found:
            candidates.append(found)
    if os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
            if base:
                candidates.append(str(Path(base) / "LibreOffice" / "program" / "soffice.exe"))
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value))
    return ""


def capability_summary() -> dict[str, Any]:
    """Return non-secret candidate information suitable for Worker logs/API policy."""
    powerpoint_candidate = bool(_powershell())
    libreoffice_candidate = bool(_libreoffice())
    candidates = [
        {
            "id": POWERPOINT,
            "candidate": powerpoint_candidate,
            "detail": (
                "Windows PowerPoint COM will be tried with a bounded timeout; activation is verified only at render time."
                if powerpoint_candidate
                else "PowerPoint COM is disabled or this is not a compatible Windows Worker."
            ),
        },
        {
            "id": LIBREOFFICE,
            "candidate": libreoffice_candidate,
            "detail": (
                "LibreOffice headless is installed and available as the free renderer fallback."
                if libreoffice_candidate
                else "LibreOffice headless is not currently installed/detected."
            ),
        },
        {"id": SAFE_FALLBACK, "candidate": True, "detail": "Built-in safe text renderer is always available."},
    ]
    selected = POWERPOINT if powerpoint_candidate else (LIBREOFFICE if libreoffice_candidate else SAFE_FALLBACK)
    return {"order": list(RENDERER_ORDER), "selectedCandidate": selected, "candidates": candidates}


def _run(command: list[str], *, timeout: int) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except (FileNotFoundError, OSError):
        return False, "unavailable"
    if completed.returncode != 0:
        return False, f"exit-{completed.returncode}"
    return True, "ok"


def export_powerpoint_frames(pptx_path: Path, output_dir: Path) -> tuple[list[Path], str]:
    powershell = _powershell()
    if not powershell:
        return [], "not-candidate"
    output_dir.mkdir(parents=True, exist_ok=True)
    script = output_dir.parent / "export-pptx-frames.ps1"
    script.write_text(
        "param([string]$PresentationPath,[string]$OutputDirectory)\n"
        "$ErrorActionPreference='Stop'\n$ppt=$null\n$deck=$null\n"
        "try {\n"
        "  $ppt=New-Object -ComObject PowerPoint.Application\n"
        "  try { $ppt.DisplayAlerts=1 } catch {}\n"
        "  $deck=$ppt.Presentations.Open($PresentationPath,-1,0,0)\n"
        "  New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null\n"
        "  for($i=1;$i -le $deck.Slides.Count;$i++){\n"
        "    $target=Join-Path $OutputDirectory ('slide-{0:D4}.png' -f $i)\n"
        "    $deck.Slides.Item($i).Export($target,'PNG',1280,720)\n"
        "  }\n"
        "} finally {\n"
        "  if($deck){$deck.Close()}\n  if($ppt){$ppt.Quit()}\n"
        "  [GC]::Collect(); [GC]::WaitForPendingFinalizers()\n"
        "}\n",
        encoding="utf-8",
    )
    try:
        timeout = max(15, min(180, int(os.environ.get("AI_VIDEO_POWERPOINT_COM_TIMEOUT_SECONDS", "45") or 45)))
    except (TypeError, ValueError):
        timeout = 45
    ok, detail = _run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-PresentationPath",
            str(pptx_path),
            "-OutputDirectory",
            str(output_dir),
        ],
        timeout=timeout,
    )
    if not ok:
        return [], detail
    frames = sorted(path for path in output_dir.glob("slide-*.png") if path.is_file() and path.stat().st_size > 0)
    return frames, "ok" if frames else "no-frames"


def _render_pdf_pages(pdf_path: Path, output_dir: Path) -> tuple[list[Path], str]:
    try:
        import fitz  # PyMuPDF; Worker-only optional dependency.
        from PIL import Image
    except Exception:
        return [], "pdf-renderer-missing"
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    try:
        document = fitz.open(str(pdf_path))
        for index, page in enumerate(document, 1):
            rect = page.rect
            scale = max(1.0, min(4.0, 1600.0 / max(1.0, float(rect.width))))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image.thumbnail((1280, 720))
            canvas = Image.new("RGB", (1280, 720), "white")
            left = max(0, (1280 - image.width) // 2)
            top = max(0, (720 - image.height) // 2)
            canvas.paste(image, (left, top))
            target = output_dir / f"slide-{index:04d}.png"
            canvas.save(target, "PNG")
            frames.append(target)
        document.close()
    except Exception:
        return [], "pdf-render-failed"
    return frames, "ok" if frames else "no-frames"


def export_libreoffice_frames(pptx_path: Path, output_dir: Path) -> tuple[list[Path], str]:
    soffice = _libreoffice()
    if not soffice:
        return [], "not-candidate"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="teacher-lo-profile-", dir=str(output_dir.parent)) as profile_temp:
        profile = Path(profile_temp).resolve().as_uri()
        pdf_dir = output_dir.parent / "libreoffice-pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        try:
            timeout = max(30, min(300, int(os.environ.get("AI_VIDEO_LIBREOFFICE_TIMEOUT_SECONDS", "120") or 120)))
        except (TypeError, ValueError):
            timeout = 120
        ok, detail = _run(
            [
                soffice,
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                f"-env:UserInstallation={profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_dir),
                str(pptx_path),
            ],
            timeout=timeout,
        )
        if not ok:
            return [], detail
        expected = pdf_dir / f"{pptx_path.stem}.pdf"
        if not expected.is_file():
            pdf_candidates = sorted(pdf_dir.glob("*.pdf"))
            if not pdf_candidates:
                return [], "pdf-missing"
            expected = pdf_candidates[0]
        return _render_pdf_pages(expected, output_dir)


def render_exact_frames(pptx_path: Path, *, expected_count: int, root: Path) -> tuple[list[Path], str, list[dict[str, str]]]:
    """Try exact/compatible renderers. Caller owns the final safe text fallback."""
    attempts: list[dict[str, str]] = []
    if _powershell():
        frames, detail = export_powerpoint_frames(pptx_path, root / "pptx-frames")
        if len(frames) == expected_count:
            attempts.append({"renderer": POWERPOINT, "status": "success", "detail": "exact-slide-count"})
            return frames, POWERPOINT, attempts
        attempts.append({"renderer": POWERPOINT, "status": "failed", "detail": detail if not frames else "slide-count-mismatch"})
    else:
        attempts.append({"renderer": POWERPOINT, "status": "skipped", "detail": "not-candidate"})

    if _libreoffice():
        frames, detail = export_libreoffice_frames(pptx_path, root / "libreoffice-frames")
        if len(frames) == expected_count:
            attempts.append({"renderer": LIBREOFFICE, "status": "success", "detail": "compatible-slide-count"})
            return frames, LIBREOFFICE, attempts
        attempts.append({"renderer": LIBREOFFICE, "status": "failed", "detail": detail if not frames else "slide-count-mismatch"})
    else:
        attempts.append({"renderer": LIBREOFFICE, "status": "skipped", "detail": "not-candidate"})
    return [], "", attempts


__all__ = [
    "LIBREOFFICE",
    "POWERPOINT",
    "RENDERER_ORDER",
    "SAFE_FALLBACK",
    "capability_summary",
    "export_libreoffice_frames",
    "export_powerpoint_frames",
    "render_exact_frames",
]
