"""Warm LibreOffice conversion runtime for the standalone material Worker.

A resident headless LibreOffice instance amortizes cold-start cost across Office
jobs.  The caller still owns a single-conversion lock.  Every warm-path failure
is recoverable: restart once, then fall back to the legacy isolated one-shot
conversion path.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import tempfile
import time
from pathlib import Path


class WarmLibreOfficeConverter:
    def __init__(
        self,
        binary: str,
        *,
        enabled: bool = True,
        startup_timeout: float = 5.0,
    ) -> None:
        self.binary = str(binary or "soffice")
        self.enabled = bool(enabled)
        self.startup_timeout = max(1.0, min(20.0, float(startup_timeout or 5.0)))
        self._process = None
        self._temp = None
        self._profile = None
        self._pipe_name = f"TeacherMaterialWorker-{os.getpid()}"
        self.last_error = ""
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
            "lastError": str(self.last_error or "")[:240],
        }

    def _new_profile(self) -> None:
        if self._temp is not None:
            try:
                self._temp.cleanup()
            except Exception:
                pass
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
            time.sleep(0.15)
            if self._process.poll() is None:
                self.last_error = ""
                return True
        self.last_error = "startup timeout"
        self.close()
        return False

    def restart(self) -> bool:
        self.close()
        return self.ensure_running()

    def convert_to_pdf(self, source: Path, out_dir: Path, *, timeout: int) -> Path:
        if not self.ensure_running():
            raise RuntimeError(self.last_error or "LibreOffice warm instance unavailable")
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
                return pdfs[0]
            if not self.running:
                break
            time.sleep(0.1)
        self.last_error = "LibreOffice warm instance produced no PDF"
        raise RuntimeError(self.last_error)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        if self._temp is not None:
            try:
                self._temp.cleanup()
            except Exception:
                pass
        self._temp = None
        self._profile = None


__all__ = ["WarmLibreOfficeConverter"]
