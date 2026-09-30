"""Worker-only reviewed PowerPoint + narration + subtitle -> MP4 renderer."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import fitz

from teacher_app.materials import ai_presentation_repository, media_subtitle_repository, media_video_repository
from teacher_app.materials import repository as material_repository
from teacher_app.materials.ai_presentation_storage import PresentationStorage
from teacher_app.storage import providers, r2_budget, r2_ledger

VIDEO_MIME = "video/mp4"


def _tool(env_name: str, default_name: str) -> str:
    configured_value = str(os.environ.get(env_name) or "").strip()
    if configured_value:
        return configured_value if Path(configured_value).is_file() else ""
    return shutil.which(default_name) or ""


def _libreoffice() -> str:
    explicit = _tool("MEDIA_VIDEO_LIBREOFFICE_BIN", "libreoffice")
    if explicit: return explicit
    return shutil.which("soffice") or ""


def _ffmpeg() -> str:
    return _tool("MEDIA_VIDEO_FFMPEG_BIN", "ffmpeg")


def configured() -> bool:
    return bool(_libreoffice() and _ffmpeg() and providers.r2_is_configured())


def public_status() -> dict[str, Any]:
    return {
        "enabled": configured(),
        "ffmpeg": bool(_ffmpeg()),
        "libreOffice": bool(_libreoffice()),
        "storesToR2": providers.r2_is_configured(),
        "requiresApprovedPresentation": True,
        "requiresApprovedNarrationSource": True,
        "subtitleMustBeApprovedWhenSelected": True,
        "workerOnly": True,
    }


def _request_key(*, presentation: dict, narration: dict, subtitle: dict | None) -> str:
    payload = {
        "presentationId": presentation.get("id", ""),
        "presentationSha256": presentation.get("artifactSha256", ""),
        "narrationMaterialId": narration.get("id", ""),
        "narrationVersion": int(narration.get("currentVersion") or 1),
        "narrationKey": narration.get("storageKey", ""),
        "subtitleId": (subtitle or {}).get("id", ""),
        "subtitleUpdatedAt": (subtitle or {}).get("updatedAt", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _run(command: list[str], *, cwd: Path, timeout: int, label: str) -> None:
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label}逾時，請檢查本機 Worker 效能或素材長度。") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().replace("\x00", " ")[-1200:]
        raise RuntimeError(f"{label}失敗：{detail or 'unknown error'}")


def _render_slides(pptx: Path, root: Path) -> list[Path]:
    libreoffice = _libreoffice()
    if not libreoffice: raise RuntimeError("AI Worker 找不到 LibreOffice/soffice，無法將 PowerPoint 轉成影片畫面。")
    _run([libreoffice, "--headless", "--convert-to", "pdf", "--outdir", str(root), str(pptx)], cwd=root, timeout=180, label="PowerPoint 轉 PDF")
    pdf = root / f"{pptx.stem}.pdf"
    if not pdf.is_file():
        candidates = list(root.glob("*.pdf")); pdf = candidates[0] if candidates else pdf
    if not pdf.is_file(): raise RuntimeError("LibreOffice 沒有產生 PowerPoint PDF。")
    images: list[Path] = []
    with fitz.open(str(pdf)) as document:
        if len(document) <= 0: raise RuntimeError("PowerPoint 沒有可輸出的投影片。")
        if len(document) > 80: raise RuntimeError("影片單次最多支援 80 張投影片。")
        for index, page in enumerate(document):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            path = root / f"slide-{index + 1:04d}.png"
            pix.save(str(path)); images.append(path)
    return images


def _download_audio(narration: dict, destination: Path) -> None:
    if narration.get("storageBackend") != "r2" or not narration.get("storageKey"):
        raise RuntimeError("影片合成目前只支援 R2 AI 語音教材。")
    providers.r2_client().download_file(providers.R2_BUCKET_NAME, str(narration["storageKey"]), str(destination))
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError("AI 語音教材下載失敗或檔案無效。")


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate(); frames = audio.getnframes()
    except Exception as exc:
        raise RuntimeError("目前影片合成需要 WAV AI 語音教材。") from exc
    if rate <= 0 or frames <= 0: raise RuntimeError("AI 語音教材沒有有效音訊長度。")
    return frames / float(rate)


def _concat_manifest(images: list[Path], duration: float, root: Path) -> Path:
    per_slide = max(0.5, duration / max(1, len(images)))
    lines: list[str] = []
    for image in images:
        lines.extend([f"file '{image.name}'", f"duration {per_slide:.6f}"])
    lines.append(f"file '{images[-1].name}'")
    path = root / "slides.txt"; path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _render_mp4(*, images: list[Path], audio: Path, subtitle: dict | None, root: Path, duration: float) -> Path:
    ffmpeg = _ffmpeg()
    if not ffmpeg: raise RuntimeError("AI Worker 找不到 FFmpeg，無法合成 MP4。")
    manifest = _concat_manifest(images, duration, root)
    output = root / "teaching-video.mp4"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", manifest.name, "-i", audio.name]
    if subtitle:
        srt = root / "captions.srt"; srt.write_text(str(subtitle.get("srtText") or ""), encoding="utf-8")
        command += ["-i", srt.name, "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0"]
    else:
        command += ["-map", "0:v:0", "-map", "1:a:0"]
    command += ["-vf", "scale='min(1920,iw)':-2,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k"]
    if subtitle: command += ["-c:s", "mov_text", "-metadata:s:s:0", "language=zho"]
    command += ["-movflags", "+faststart", "-shortest", output.name]
    _run(command, cwd=root, timeout=max(300, int(duration * 4) + 120), label="FFmpeg MP4 合成")
    if not output.is_file() or output.stat().st_size < 4096: raise RuntimeError("FFmpeg 沒有產生有效 MP4。")
    return output


def _existing_output(video_id: str) -> tuple[int, str]:
    key = f"media-videos/{video_id}/teaching-video.mp4"
    try:
        head = providers.r2_client().head_object(Bucket=providers.R2_BUCKET_NAME, Key=key)
    except Exception as exc:
        response = getattr(exc, "response", {}) or {}; status = int(((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0))
        code = str((response.get("Error") or {}).get("Code") or "")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}: return 0, ""
        raise
    return int(head.get("ContentLength") or 0), str((head.get("Metadata") or {}).get("sha256") or "")


def _store_output(*, job_id: str, video_id: str, output: Path) -> dict:
    key = f"media-videos/{video_id}/teaching-video.mp4"
    digest = hashlib.sha256(output.read_bytes()).hexdigest(); size = output.stat().st_size
    r2_budget.reserve_upload(job_id, key, size)
    try:
        providers.r2_client().upload_file(str(output), providers.R2_BUCKET_NAME, key, ExtraArgs={"ContentType": VIDEO_MIME, "Metadata": {"sha256": digest, "generated-by": "teacher-ai-worker"}})
        r2_ledger.record_object(key, size, estimated_operations=1, is_staging=False)
        r2_budget.release_reservation(job_id, "published")
    except Exception:
        r2_budget.release_reservation(job_id, "failed"); raise
    return {"backend": "r2", "key": key, "sha256": digest, "byteSize": size, "mimeType": VIDEO_MIME}


def generate_video(*, job: dict, progress_callback=None) -> dict:
    presentation = ai_presentation_repository.get_presentation(str(job.get("presentationId") or ""))
    narration = material_repository.get_material(str(job.get("narrationMaterialId") or ""))
    subtitle = media_subtitle_repository.get_subtitle(str(job.get("subtitleId") or "")) if job.get("subtitleId") else None
    if not presentation or presentation.get("status") != "approved" or not presentation.get("approvedBy") or not presentation.get("approvedAt"):
        raise RuntimeError("影片來源 PowerPoint 已不存在或不再是核准版本。")
    if not narration:
        raise RuntimeError("影片來源 AI 語音教材已不存在。")
    meta = narration.get("storageMeta") or {}
    if meta.get("mediaKind") != "ai_narration" or not meta.get("teacherApprovedBy") or not meta.get("teacherApprovedAt"):
        raise RuntimeError("影片來源語音不再符合教師核准來源規則。")
    if narration.get("group") != presentation.get("group") or narration.get("area") != presentation.get("area"):
        raise RuntimeError("影片來源的組別/訓練範圍已改變。")
    if subtitle:
        if subtitle.get("status") != "approved" or subtitle.get("materialId") != narration.get("id"):
            raise RuntimeError("影片字幕已不是本次語音教材的核准字幕。")
        if int(subtitle.get("sourceVersion") or 1) != int(narration.get("currentVersion") or 1):
            raise RuntimeError("影片字幕來源語音已有新版。")
    expected_key = _request_key(presentation=presentation, narration=narration, subtitle=subtitle)
    if expected_key != str(job.get("requestKey") or ""):
        raise RuntimeError("影片來源在排隊後已變更；請重新送出影片合成。")
    existing = media_video_repository.get_video_by_request_key(expected_key)
    if existing:
        return {"videoId": existing["id"], "artifactSha256": existing.get("artifactSha256", ""), "replayed": True}
    video_id = f"mvideo-{expected_key[:24]}"
    if progress_callback: progress_callback(10, "下載已核准素材", "取得 PowerPoint 與 AI 語音")
    with tempfile.TemporaryDirectory(prefix="teacher-video-") as temp:
        root = Path(temp)
        pptx = PresentationStorage().download({"backend": presentation.get("artifactBackend"), "key": presentation.get("artifactStorageKey"), "sha256": presentation.get("artifactSha256")}, root / "presentation.pptx")
        audio = root / "narration.wav"; _download_audio(narration, audio); duration = _wav_duration(audio)
        if progress_callback: progress_callback(30, "轉換投影片畫面", "LibreOffice 正在轉換已核准 PowerPoint")
        images = _render_slides(pptx, root)
        if progress_callback: progress_callback(55, "合成教學影片", "FFmpeg 正在合成投影片、語音與核准字幕")
        output = _render_mp4(images=images, audio=audio, subtitle=subtitle, root=root, duration=duration)
        artifact = _store_output(job_id=str(job.get("id") or ""), video_id=video_id, output=output)
    provenance = {
        "presentationId": presentation.get("id", ""), "presentationSha256": presentation.get("artifactSha256", ""),
        "presentationApprovedBy": presentation.get("approvedBy", ""), "presentationApprovedAt": presentation.get("approvedAt", ""),
        "narrationMaterialId": narration.get("id", ""), "narrationVersion": int(narration.get("currentVersion") or 1),
        "narrationApprovedBy": meta.get("teacherApprovedBy", ""), "narrationApprovedAt": meta.get("teacherApprovedAt", ""),
        "subtitleId": (subtitle or {}).get("id", ""), "subtitleApprovedBy": (subtitle or {}).get("approvedBy", ""),
        "subtitleApprovedAt": (subtitle or {}).get("approvedAt", ""),
    }
    created = media_video_repository.create_video({
        "id": video_id, "request_key": expected_key, "presentation_id": presentation["id"], "narration_material_id": narration["id"],
        "subtitle_id": (subtitle or {}).get("id", ""), "group_key": presentation.get("group", ""), "training_area": presentation.get("area", ""),
        "title": f"{presentation.get('title') or '教學投影片'}｜教學影片", "artifact_backend": artifact["backend"],
        "artifact_storage_key": artifact["key"], "artifact_sha256": artifact["sha256"], "artifact_bytes": artifact["byteSize"],
        "duration_seconds": duration, "source_presentation_sha256": presentation.get("artifactSha256", ""),
        "source_audio_key": narration.get("storageKey", ""), "source_audio_version": int(narration.get("currentVersion") or 1),
        "source_subtitle_updated_at": (subtitle or {}).get("updatedAt", ""), "provenance": provenance,
        "created_by": str(job.get("actorUsername") or ""),
    })
    if progress_callback: progress_callback(95, "影片草稿已完成", "等待授課教師預覽與核准")
    return {"videoId": created.get("id", video_id), "artifactSha256": created.get("artifactSha256", artifact["sha256"]), "artifactBytes": created.get("artifactBytes", artifact["byteSize"]), "durationSeconds": created.get("durationSeconds", duration), "replayed": False}


def preview_url(video: dict, expires: int = 900) -> str:
    if video.get("artifactBackend") != "r2" or not video.get("artifactStorageKey"): return ""
    return providers.r2_client().generate_presigned_url("get_object", Params={"Bucket": providers.R2_BUCKET_NAME, "Key": video["artifactStorageKey"], "ResponseContentType": VIDEO_MIME, "ResponseContentDisposition": 'inline; filename="teaching-video.mp4"'}, ExpiresIn=max(60, min(3600, int(expires))))


__all__ = ["VIDEO_MIME", "configured", "generate_video", "preview_url", "public_status"]
