"""Warm LibreOffice conversion runtime for the standalone material Worker.

A resident headless LibreOffice instance amortizes cold-start cost across Office
jobs.  The caller still owns a single-conversion lock.  Every warm-path failure
is recoverable: restart once, then fall back to the legacy isolated one-shot
conversion path.

Cold-start cost (profile creation, font cache, Impress module load) is paid
only once: the profile directory is persistent across Worker restarts, and
``warmup()`` performs a real conversion of a tiny presentation so the first
real material does not pay that cost.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import tempfile
import time
from pathlib import Path

# Minimal flat-ODF presentation.  It contains CJK text so the CJK font cache is
# built during warmup instead of during the first real teaching material.
_WARMUP_FODP = """<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.presentation">
<office:body><office:presentation><draw:page draw:name="warmup"><draw:frame svg:x="2cm" svg:y="2cm" svg:width="12cm" svg:height="3cm"><draw:text-box><text:p>Teacher warmup 醫學檢驗教學平台 暖機</text:p></draw:text-box></draw:frame></draw:page></office:presentation></office:body>
</office:document>
"""


def default_profile_root() -> Path:
    """Persistent directory that holds LibreOffice profiles for the Worker."""
    configured = str(os.environ.get("MATERIAL_LIBREOFFICE_PROFILE_DIR") or "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    base = str(os.environ.get("LOCALAPPDATA") or os.environ.get("PROGRAMDATA") or "").strip()
    if base:
        return Path(base) / "Teacher" / "libreoffice-profile"
    return Path(tempfile.gettempdir()) / "teacher-worker-libreoffice-profile"


def _remove_stale_lock(profile: Path) -> None:
    """Drop a lock left by a crashed LibreOffice so the new instance can start."""
    for name in (".lock", ".~lock"):
        try:
            (profile / "user" / name).unlink(missing_ok=True)
        except OSError:
            pass


class WarmLibreOfficeConverter:
    def __init__(
        self,
        binary: str,
        *,
        enabled: bool = True,
        startup_timeout: float = 5.0,
        profile_dir: str | Path | None = None,
    ) -> None:
        self.binary = str(binary or "soffice")
        self.enabled = bool(enabled)
        self.startup_timeout = max(1.0, min(20.0, float(startup_timeout or 5.0)))
        self._process = None
        self._temp = None
        self._profile = None
        # A persistent profile keeps the font cache and first-start data between
        # Worker restarts.  Without it every start pays the full cold-start cost.
        self._persistent_profile = (
            Path(profile_dir) / "warm" if profile_dir else default_profile_root() / "warm"
        )
        self._pipe_name = f"TeacherMaterialWorker-{os.getpid()}"
        self.last_error = ""
        self.warmed = False
        self.warmup_seconds = 0.0
        self.last_convert_seconds = 0.0
        atexit.register(self.close)

    @property
    def running(self) -> bool:
        return bool(self._process is not None and self._process.poll() is None)

    @property
    def profile_arg(self) -> str:
        if self._profile is None:
            return ""
        return f"-env:UserInstallation={self._profile.resolve().as_uri()}"

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "running": self.running,
            "warmed": bool(self.warmed and self.running),
            "warmupSeconds": round(float(self.warmup_seconds), 2),
            "lastConvertSeconds": round(float(self.last_convert_seconds), 2),
            "lastError": str(self.last_error or "")[:240],
        }

    def _new_profile(self) -> None:
        if self._temp is not None:
            try:
                self._temp.cleanup()
            except Exception:
                pass
            self._temp = None
        try:
            self._persistent_profile.mkdir(parents=True, exist_ok=True)
            _remove_stale_lock(self._persistent_profile)
            self._profile = self._persistent_profile
            return
        except OSError:
            # Unwritable persistent location: fall back to a disposable profile
            # rather than failing Worker startup.
            self._profile = None
        self._temp = tempfile.TemporaryDirectory(prefix="teacher-worker-lo-warm-")
        self._profile = Path(self._temp.name) / "profile"
        self._profile.mkdir(parents=True, exist_ok=True)

    def ensure_running(self) -> bool:
        if not self.enabled:
            return False
        if self.running:
            return True
        self.close()
        self._new_profile()
        command = [
            self.binary,
            "--headless",
            "--invisible",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            self.profile_arg,
            f"--accept=pipe,name={self._pipe_name};urp;StarOffice.ServiceManager",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.last_error = type(exc).__name__
            self._process = None
            return False

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.last_error = f"exit {self._process.returncode}"
                self._process = None
                return False
            # LibreOffice normally stays resident almost immediately.  A short
            # grace period avoids paying the full timeout on every Worker boot.
            # Real readiness is verified by warmup(), which converts a document.
            time.sleep(0.15)
            if self._process.poll() is None:
                self.last_error = ""
                return True
        self.last_error = "startup timeout"
        self.close()
        return False

    def warmup(self, *, timeout: int = 180) -> bool:
        """Start the resident instance and convert a tiny deck once.

        ``ensure_running`` only proves the process is alive.  Converting a real
        (CJK-containing) presentation loads the Impress module and builds the
        font cache, so the first teaching material no longer pays cold start.
        Never raises; a failure just leaves ``warmed`` False and ``last_error``.
        """
        if not self.enabled:
            return False
        if self.warmed and self.running:
            return True
        started = time.monotonic()
        try:
            if not self.ensure_running():
                return False
            with tempfile.TemporaryDirectory(prefix="teacher-worker-lo-warmup-") as temp:
                source = Path(temp) / "warmup.fodp"
                source.write_text(_WARMUP_FODP, encoding="utf-8")
                self.convert_to_pdf(source, Path(temp) / "out", timeout=timeout)
        except Exception as exc:
            if not self.last_error:
                self.last_error = type(exc).__name__
            self.warmed = False
            return False
        self.warmed = True
        self.warmup_seconds = time.monotonic() - started
        self.last_error = ""
        return True

    def restart(self) -> bool:
        self.close()
        return self.ensure_running()

    def convert_to_pdf(self, source: Path, out_dir: Path, *, timeout: int) -> Path:
        if not self.ensure_running():
            raise RuntimeError(self.last_error or "LibreOffice warm instance unavailable")
        started = time.monotonic()
        source = Path(source)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.binary,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            self.profile_arg,
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self.last_error = "conversion timeout"
            raise RuntimeError("LibreOffice warm conversion timed out") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode(errors="ignore")[:300]
            self.last_error = detail or f"exit {completed.returncode}"
            raise RuntimeError(self.last_error)

        # Commands forwarded to a resident LibreOffice may return just before
        # the output file is visible.  Wait briefly within the caller's timeout.
        deadline = time.monotonic() + min(5.0, max(0.5, float(timeout) / 4.0))
        while time.monotonic() < deadline:
            pdfs = sorted(out_dir.glob("*.pdf"))
            if pdfs and pdfs[0].stat().st_size > 0:
                self.last_error = ""
                self.last_convert_seconds = time.monotonic() - started
                return pdfs[0]
            if not self.running:
                break
            time.sleep(0.1)
        self.last_error = "LibreOffice warm instance produced no PDF"
        raise RuntimeError(self.last_error)

    def close(self) -> None:
        process = self._process
        self._process = None
        self.warmed = False
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        # The persistent profile is intentionally kept; only a disposable
        # fallback profile is removed.
        if self._temp is not None:
            try:
                self._temp.cleanup()
            except Exception:
                pass
        self._temp = None
        self._profile = None


__all__ = ["WarmLibreOfficeConverter", "default_profile_root"]
