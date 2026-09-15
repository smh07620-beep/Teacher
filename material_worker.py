"""Teacher local material worker (outbound HTTPS only)."""
from __future__ import annotations
import datetime as dt
import hashlib, json, os, re, socket, subprocess, sys, tempfile, time
from pathlib import Path
import requests
from upload_hardening import ZIP_EXT, _magic_ok, _validate_zip_bytes

BASE_URL=os.environ.get("TEACHER_BASE_URL", "").rstrip("/")
TOKEN=os.environ.get("MATERIAL_WORKER_TOKEN", "")
WORKER_ID=os.environ.get("MATERIAL_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"
POLL_SECONDS=max(2,min(60,int(os.environ.get("MATERIAL_WORKER_POLL_SECONDS","5"))))
REQUEST_TIMEOUT=max(10,min(600,int(os.environ.get("MATERIAL_WORKER_HTTP_TIMEOUT","120"))))
ALLOWED_EXT={".pptx",".ppt",".pdf",".doc",".docx",".xls",".xlsx",".odp",".odt",".ods",".png",".jpg",".jpeg",".gif",".webp",".mp4",".webm",".mov",".m4v",".mp3",".wav",".m4a",".ogg",".txt",".csv",".srt",".vtt",".zip"}
VIDEO_EXT={".mp4",".webm",".mov",".m4v"}; AUDIO_EXT={".mp3",".wav",".m4a",".ogg"}
RESTART_FOR_UPDATE=75
ROOT=Path(__file__).resolve().parent

def _env_true(name, default=False):
    value=os.environ.get(name, "true" if default else "false").strip().lower()
    return value in {"1","true","yes","on"}

def _utc_now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def _run_git(*args):
    try:
        completed=subprocess.run(["git",*args],cwd=ROOT,capture_output=True,text=True,timeout=10,check=False)
        return completed.returncode, (completed.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""

def worker_metadata():
    """Return non-sensitive build/update data that is safe for the Web API."""
    try: version=(ROOT/"VERSION").read_text(encoding="utf-8").strip()[:32]
    except OSError: version=""
    _code, sha=_run_git("rev-parse","--short=7","HEAD")
    _code, branch=_run_git("branch","--show-current")
    return {"workerVersion":version,"workerSha":sha[:40],"workerBranch":branch[:80]}

class AutoUpdateController:
    """Run the fixed local updater only between jobs; never hot-reload Python."""
    def __init__(self, root=ROOT, runner=None, now=None):
        self.root=Path(root); self.runner=runner or self._run_updater; self.now=now or _utc_now
        self.enabled=_env_true("MATERIAL_WORKER_AUTO_UPDATE", True)
        try: requested=float(os.environ.get("MATERIAL_WORKER_UPDATE_INTERVAL_HOURS","6"))
        except ValueError: requested=6
        self.interval_seconds=max(1.0, requested)*3600
        self.state_path=Path(os.environ.get("MATERIAL_WORKER_UPDATE_STATE_PATH", str(self.root/".worker-update-state.json")))
        self.last_check_at=""; self.update_available=False; self._load_state()

    def _load_state(self):
        try:
            state=json.loads(self.state_path.read_text(encoding="utf-8"))
            self.last_check_at=str(state.get("lastUpdateCheckAt") or "")[:64]
            self.update_available=bool(state.get("updateAvailable", False))
        except (OSError, ValueError, TypeError): pass

    def _save_state(self):
        # This local, gitignored state file intentionally has no credentials.
        try: self.state_path.write_text(json.dumps({"lastUpdateCheckAt":self.last_check_at,"updateAvailable":self.update_available}),encoding="utf-8")
        except OSError: pass

    def metadata(self):
        return {**worker_metadata(),"updateAvailable":self.update_available,"lastUpdateCheckAt":self.last_check_at}

    def due(self, timestamp=None):
        if not self.enabled: return False
        if not self.last_check_at: return True
        try:
            last=dt.datetime.fromisoformat(self.last_check_at.replace("Z","+00:00"))
            if last.tzinfo is None: last=last.replace(tzinfo=dt.timezone.utc)
            current=timestamp or dt.datetime.now(dt.timezone.utc)
            return (current-last).total_seconds()>=self.interval_seconds
        except (TypeError, ValueError): return True

    def _run_updater(self):
        if sys.platform != "win32": return None
        script=self.root/"update_material_worker.ps1"
        if not script.is_file(): return None
        shell=os.environ.get("POWERSHELL_EXE", "powershell.exe")
        try:
            return subprocess.run([shell,"-NoProfile","-ExecutionPolicy","Bypass","-File",str(script)],cwd=self.root,capture_output=True,text=True,timeout=180,check=False).returncode
        except (OSError, subprocess.TimeoutExpired): return None

    def check_when_idle(self):
        """Return True only after a successful on-disk update requiring restart."""
        if not self.due(): return False
        before=worker_metadata().get("workerSha", "")
        result=self.runner()
        self.last_check_at=self.now()
        after=worker_metadata().get("workerSha", "")
        updated=bool(result == 0 and before and after and before != after)
        self.update_available=updated
        self._save_state()
        if result not in (0, None): log(f"safe update check failed (exit {result}); continuing current local version")
        return updated

AUTO_UPDATER=AutoUpdateController()

def log(message): print(f"[teacher-local-worker {WORKER_ID}] {message}",flush=True)
def _bin(env,fallback):
    value=os.environ.get(env,"").strip()
    if value:return value
    import shutil
    return shutil.which(fallback) or ""
def _works(path,args):
    try:return bool(path) and subprocess.run([path,*args],capture_output=True,timeout=5,check=False).returncode==0
    except (OSError,subprocess.TimeoutExpired):return False
def capability():
    ffmpeg,ffprobe,soffice=_bin("FFMPEG_PATH","ffmpeg"),_bin("FFPROBE_PATH","ffprobe"),_bin("SOFFICE_PATH","soffice")
    return {"platform":sys.platform,"ffmpeg":{"available":_works(ffmpeg,["-version"])} ,"ffprobe":{"available":_works(ffprobe,["-version"])} ,"libreOffice":{"available":_works(soffice,["--version"])}}

class WorkerApi:
    def __init__(self):
        if not BASE_URL.startswith("https://"):raise RuntimeError("TEACHER_BASE_URL 必須是 HTTPS URL。")
        if not TOKEN:raise RuntimeError("MATERIAL_WORKER_TOKEN 尚未設定。")
        self.headers={"Authorization":f"Bearer {TOKEN}"}
    def post(self,path,body):
        response=requests.post(BASE_URL+path,json=body,headers=self.headers,timeout=REQUEST_TIMEOUT)
        if response.status_code>=300:
            try:message=response.json().get("error","")
            except Exception:message=response.text[:300]
            raise RuntimeError(f"Worker API {response.status_code}: {message}")
        return response.json()
    def heartbeat(self,job_id=""):
        path=f"/api/material-worker/{job_id}/heartbeat" if job_id else "/api/material-worker/heartbeat"
        return self.post(path,{"workerId":WORKER_ID,"capabilities":capability(),**AUTO_UPDATER.metadata()})
    def download(self,job,target):
        url=str(job.get("downloadUrl") or "")
        headers={}
        if not url:
            path=str(job.get("downloadPath") or "")
            if not path.startswith("/api/material-worker/"):
                raise RuntimeError("Worker 工作未提供安全下載位置。")
            url=BASE_URL+path; headers={**self.headers,"X-Teacher-Worker-Id":WORKER_ID}
        download(url,target,headers=headers)

def _sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()
def validate_download(source,job):
    original=Path(str(job.get("originalName") or "")).name; ext=Path(original).suffix.lower(); source=Path(source)
    if ext not in ALLOWED_EXT:raise RuntimeError("Worker 收到不支援的副檔名。")
    if not source.is_file() or source.stat().st_size<=0:raise RuntimeError("Worker 下載到空白檔案。")
    if source.stat().st_size!=int(job.get("sourceBytes",0) or 0):raise RuntimeError("Worker 下載檔案大小不符。")
    if _sha256(source)!=str(job.get("sourceSha256") or "").lower():raise RuntimeError("Worker 下載檔案 SHA256 不符。")
    with source.open("rb") as fh:head=fh.read(8192)
    if not _magic_ok(ext,head):raise RuntimeError("Worker 檔案內容與副檔名不符。")
    if ext in ZIP_EXT:_validate_zip_bytes(source.read_bytes(),ext)
    return original
def download(url,target,headers=None):
    if not str(url).startswith("https://"):raise RuntimeError("Worker download URL 必須是 HTTPS。")
    with requests.get(url,stream=True,headers=headers or {},timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        with Path(target).open("wb") as fh:
            for chunk in response.iter_content(1024*1024):
                if chunk:fh.write(chunk)

def _transcode_if_needed(source,original,temp):
    ext=Path(original).suffix.lower(); ffmpeg=_bin("FFMPEG_PATH","ffmpeg")
    if ext not in VIDEO_EXT|AUDIO_EXT:return source,original,{}
    if not ffmpeg:raise RuntimeError("FFmpeg unavailable")
    if ext in VIDEO_EXT:
        output=Path(temp)/"web.mp4"; command=[ffmpeg,"-y","-i",str(source),"-c:v","libx264","-preset","medium","-movflags","+faststart","-c:a","aac","-b:a","160k",str(output)]; name=Path(original).with_suffix(".mp4").name
    else:
        output=Path(temp)/"web.m4a"; command=[ffmpeg,"-y","-i",str(source),"-c:a","aac","-b:a","160k",str(output)]; name=Path(original).with_suffix(".m4a").name
    try:completed=subprocess.run(command,capture_output=True,text=True,timeout=max(60,min(3600,int(os.environ.get("MATERIAL_FFMPEG_TIMEOUT_SECONDS","1800")))),check=False)
    except subprocess.TimeoutExpired:raise RuntimeError("FFmpeg conversion timed out")
    if completed.returncode!=0 or not output.is_file() or output.stat().st_size<=0:raise RuntimeError(f"FFmpeg conversion failed: {(completed.stderr or '')[-300:]}")
    return output,name,{"transcoded":True,"sourceOriginalName":original}

def publish_to_storage(source,original,job,temp):
    """Use existing MEGA-primary/GDrive-fallback helpers with local env only."""
    import app as storage
    material_id=str(job["materialId"]); source,stored_name,media_meta=_transcode_if_needed(source,original,temp)
    backend=storage.active_material_backend(); slides=Path(temp)/"slides"; slides.mkdir(exist_ok=True); preview=Path(temp)/"preview.pdf"; ext=source.suffix.lower(); pages=0
    single=bool(backend=="mega" and storage.MATERIAL_SINGLE_PREVIEW and (ext==".pdf" or ext in storage.OFFICE_EXT))
    if single:
        pages=storage.build_single_preview_pdf(source,preview)
        if pages<=0 or not preview.is_file() or preview.stat().st_size<=0: raise RuntimeError("Office/PDF preview 產生失敗，不能完成工作。")
        key,prefix,remote=storage.upload_material_preview_to_mega(material_id,source,preview,pages); meta={"previewMode":"single_pdf","previewFilename":"preview.pdf","slideFormat":"pdf",**(remote or {}),**media_meta}
    elif ext==".pdf" or ext in storage.OFFICE_EXT:
        pages=storage.convert_pdf_to_images(source,slides) if ext==".pdf" else storage.convert_office_to_images(source,slides)
        if pages<=0: raise RuntimeError("Office/PDF 頁面數為零，不能完成工作。")
        if backend=="mega":key,prefix,remote=storage.upload_material_tree_to_mega(material_id,source,slides,pages)
        elif backend=="gdrive":key,prefix,remote=storage.upload_material_tree_to_gdrive(material_id,source,slides,pages,original_name=stored_name)
        else:raise RuntimeError("Local Worker 正式教材儲存需設定 MEGA 或 Google Drive。")
        meta={"slideFormat":storage._slide_format(slides,pages),**(remote or {}),**media_meta}
    elif backend=="mega":
        folder=storage._mega_remote_join(storage._mega_root_id(),material_id); key=storage._mega_upload_file(source,folder,f"source{source.suffix.lower()}"); prefix=""; meta=media_meta
    elif backend=="gdrive":
        key,prefix,remote=storage.upload_material_tree_to_gdrive(material_id,source,slides,0,original_name=stored_name); meta={**(remote or {}),**media_meta}
    else:raise RuntimeError("Local Worker 正式教材儲存需設定 MEGA 或 Google Drive。")
    return {"storageBackend":backend,"storageKey":key,"slidesPrefix":prefix,"storageFilename":f"source{source.suffix.lower()}","pageCount":pages,"storageMeta":meta}

def process_one(api,job):
    job_id=job["id"]
    try:
        with tempfile.TemporaryDirectory(prefix="teacher-local-worker-") as temp_name:
            temp=Path(temp_name); staged=temp/"source.bin"; api.download(job,staged); original=validate_download(staged,job)
            # File content is staged as .bin, but processing must see the actual
            # extension so LibreOffice and preview routing are deterministic.
            source=temp/("source"+Path(original).suffix.lower()); staged.replace(source)
            api.heartbeat(job_id); result=publish_to_storage(source,original,job,temp); api.post(f"/api/material-worker/{job_id}/complete",{"workerId":WORKER_ID,"result":result})
        log(f"completed {job_id}")
    except Exception as exc:
        message=str(exc)[:1200]
        try:api.post(f"/api/material-worker/{job_id}/retry",{"workerId":WORKER_ID,"error":message})
        except Exception as report:log(f"failed to report {job_id}: {report}")
        log(f"job {job_id}: {message}")
def main():
    try:api=WorkerApi()
    except RuntimeError as exc:log(str(exc));return 2
    caps=capability();log(f"startup ffmpeg={caps['ffmpeg']['available']} ffprobe={caps['ffprobe']['available']} libreoffice={caps['libreOffice']['available']}")
    while True:
        try:
            api.heartbeat(); data=api.post("/api/material-worker/claim",{"workerId":WORKER_ID,"capabilities":caps,**AUTO_UPDATER.metadata()}); job=data.get("job")
            if job:
                # A claimed job is processing work: never fetch or modify code here.
                process_one(api,job)
            else:
                # The updater may fast-forward files only after no job was claimed.
                if AUTO_UPDATER.check_when_idle():
                    api.heartbeat()
                    log("safe update installed while idle; requesting launcher restart")
                    return RESTART_FOR_UPDATE
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:return 0
        except Exception as exc:log(f"API unavailable: {exc}");time.sleep(POLL_SECONDS)
if __name__=="__main__":sys.exit(main())
