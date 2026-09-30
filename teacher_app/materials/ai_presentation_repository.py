"""Persistence for AI PowerPoint templates, jobs, revisions, and publication receipts."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db


PRESENTATION_STATUSES = {"draft", "approved", "published", "superseded"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _decode(value: Any, default):
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, type(default)) else default
        except Exception:
            pass
    return default


def _json(kind: str, ph: str) -> str:
    return f"{ph}::jsonb" if kind == "postgres" else ph


def _template(row):
    if not row:
        return None
    r = dict(row)
    return {
        "id": str(r.get("id") or ""), "name": str(r.get("name") or ""),
        "group": str(r.get("group_key") or ""), "area": str(r.get("training_area") or ""),
        "active": bool(r.get("active", True)),
        "storageBackend": str(r.get("storage_backend") or "local").lower(),
        "storageKey": str(r.get("storage_key") or ""),
        "storageFilename": str(r.get("storage_filename") or ""),
        "sha256": str(r.get("sha256") or ""), "byteSize": int(r.get("byte_size") or 0),
        "mimeType": str(r.get("mime_type") or ""), "createdBy": str(r.get("created_by") or ""),
        "createdAt": str(r.get("created_at") or ""), "updatedAt": str(r.get("updated_at") or ""),
    }


def _job(row):
    if not row:
        return None
    r = dict(row)
    return {
        "id": str(r.get("id") or ""), "draftId": str(r.get("draft_id") or ""),
        "templateId": str(r.get("template_id") or ""), "group": str(r.get("group_key") or ""),
        "area": str(r.get("training_area") or ""), "actorUsername": str(r.get("actor_username") or ""),
        "status": str(r.get("status") or ""), "request": _decode(r.get("request_json"), {}),
        "result": _decode(r.get("result_json"), {}), "progressPercent": float(r.get("progress_percent") or 0),
        "progressStage": str(r.get("progress_stage") or ""), "progressDetail": str(r.get("progress_detail") or ""),
        "error": str(r.get("error") or ""), "claimToken": str(r.get("claim_token") or ""),
        "attempts": int(r.get("attempts") or 0), "createdAt": str(r.get("created_at") or ""),
        "updatedAt": str(r.get("updated_at") or ""), "startedAt": str(r.get("started_at") or ""),
        "completedAt": str(r.get("completed_at") or ""),
    }


def _presentation(row):
    if not row:
        return None
    r = dict(row)
    pid = str(r.get("id") or "")
    return {
        "id": pid, "presentationFamilyId": str(r.get("presentation_family_id") or "") or pid,
        "parentVersionId": str(r.get("parent_version_id") or ""),
        "revisionNumber": max(1, int(r.get("revision_number") or 1)),
        "materialId": str(r.get("material_id") or ""), "draftId": str(r.get("draft_id") or ""),
        "templateId": str(r.get("template_id") or ""), "group": str(r.get("group_key") or ""),
        "area": str(r.get("training_area") or ""), "title": str(r.get("title") or ""),
        "status": str(r.get("status") or "draft"), "slides": _decode(r.get("slides_json"), []),
        "artifactBackend": str(r.get("artifact_backend") or "local").lower(),
        "artifactStorageKey": str(r.get("artifact_storage_key") or ""),
        "artifactStorageFilename": str(r.get("artifact_storage_filename") or ""),
        "artifactSha256": str(r.get("artifact_sha256") or ""),
        "artifactBytes": int(r.get("artifact_bytes") or 0),
        "artifactMimeType": str(r.get("artifact_mime_type") or ""),
        "provider": str(r.get("provider") or ""), "model": str(r.get("model") or ""),
        "sourceJobId": str(r.get("source_job_id") or ""), "createdBy": str(r.get("created_by") or ""),
        "updatedBy": str(r.get("updated_by") or ""), "approvedBy": str(r.get("approved_by") or ""),
        "approvedAt": str(r.get("approved_at") or ""), "publishedAt": str(r.get("published_at") or ""),
        "createdAt": str(r.get("created_at") or ""), "updatedAt": str(r.get("updated_at") or ""),
    }


def _publication(row):
    if not row:
        return None
    r = dict(row)
    return {
        "id": str(r.get("id") or ""), "presentationId": str(r.get("presentation_id") or ""),
        "publicationMaterialId": str(r.get("publication_material_id") or ""),
        "receiptKey": str(r.get("receipt_key") or ""), "receipt": _decode(r.get("receipt_json"), {}),
        "createdBy": str(r.get("created_by") or ""), "createdAt": str(r.get("created_at") or ""),
    }


def create_template(**data) -> dict:
    tid, stamp = f"ptpl-{uuid.uuid4().hex}", _now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            "INSERT INTO ai_presentation_templates(id,name,group_key,training_area,active,storage_backend,"
            "storage_key,storage_filename,sha256,byte_size,mime_type,created_by,created_at,updated_at) VALUES(" +
            ",".join([ph] * 14) + ")",
            (tid, data["name"], data["group_key"], data["training_area"], True if kind == "postgres" else 1,
             data["storage_backend"], data["storage_key"], data["storage_filename"], data["sha256"],
             int(data["byte_size"]), data["mime_type"], data["actor_username"], stamp, stamp),
        )
    return get_template(tid) or {}


def get_template(template_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM ai_presentation_templates WHERE id={ph}", (template_id,)).fetchone()
    return _template(row)


def list_templates(*, group_key="", training_area="", include_inactive=False):
    with common_db.read_connection() as (conn, kind):
        ph, clauses, params = common_db.placeholder(kind), [], []
        if group_key:
            clauses.append(f"group_key={ph}"); params.append(group_key)
        if training_area:
            clauses.append(f"training_area={ph}"); params.append(training_area)
        if not include_inactive:
            clauses.append("active=" + ("TRUE" if kind == "postgres" else "1"))
        sql = "SELECT * FROM ai_presentation_templates" + ((" WHERE " + " AND ".join(clauses)) if clauses else "") + " ORDER BY updated_at DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_template(row) for row in rows]


def create_job(*, draft_id, template_id, group_key, training_area, actor_username, request_payload=None):
    jid, stamp = f"pptjob-{uuid.uuid4().hex}", _now()
    payload = json.dumps(dict(request_payload or {}), ensure_ascii=False, separators=(",", ":"))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph)
        conn.execute(
            "INSERT INTO ai_presentation_jobs(id,draft_id,template_id,group_key,training_area,actor_username,status,"
            "request_json,progress_percent,progress_stage,progress_detail,result_json,error,claim_token,attempts,"
            "created_at,updated_at,started_at,completed_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{ph},{j},{ph},{ph},{ph},{j},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (jid,draft_id,template_id,group_key,training_area,actor_username,"queued",payload,0,
             "等待產生 PowerPoint","工作已排入 AI Worker 佇列","{}","","",0,stamp,stamp,"",""),
        )
    return get_job(jid) or {}


def get_job(job_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM ai_presentation_jobs WHERE id={ph}",(job_id,)).fetchone()
    return _job(row)


def list_queued(limit=20):
    limit = max(1, min(100, int(limit)))
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        rows = conn.execute(f"SELECT * FROM ai_presentation_jobs WHERE status={ph} ORDER BY created_at ASC LIMIT {ph}", ("queued", limit)).fetchall()
    return [_job(row) for row in rows]


def claim_job(job_id: str, token: str):
    stamp = _now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE ai_presentation_jobs SET status={ph},claim_token={ph},attempts=attempts+1,started_at={ph},updated_at={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE id={ph} AND status={ph}",
            ("processing",token,stamp,stamp,"PowerPoint 產生中","AI Worker 已取得工作",job_id,"queued"),
        )
        if not int(getattr(cur,"rowcount",0) or 0):
            return None
        row = conn.execute(f"SELECT * FROM ai_presentation_jobs WHERE id={ph}",(job_id,)).fetchone()
    return _job(row)


def set_job_progress(job_id, token, percent, stage, detail):
    stamp = _now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE ai_presentation_jobs SET progress_percent={ph},progress_stage={ph},progress_detail={ph},updated_at={ph} "
            f"WHERE id={ph} AND status={ph} AND claim_token={ph}",
            (max(0,min(99,float(percent or 0))),str(stage or "")[:200],str(detail or "")[:1000],stamp,job_id,"processing",token),
        )
    return bool(int(getattr(cur,"rowcount",0) or 0))


def complete_job(job_id, token, result):
    stamp = _now(); payload = json.dumps(dict(result), ensure_ascii=False, separators=(",", ":"))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph)
        cur = conn.execute(
            f"UPDATE ai_presentation_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},"
            f"result_json={j},error={ph},completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("completed",100,"PowerPoint 完成","請由授課教師檢查後核准",payload,"",stamp,stamp,job_id,"processing",token),
        )
    return bool(int(getattr(cur,"rowcount",0) or 0))


def fail_job(job_id, token, error):
    stamp, message = _now(), str(error or "PowerPoint 產生失敗")[:2000]
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE ai_presentation_jobs SET status={ph},progress_percent={ph},progress_stage={ph},progress_detail={ph},error={ph},"
            f"completed_at={ph},updated_at={ph} WHERE id={ph} AND status={ph} AND claim_token={ph}",
            ("failed",0,"PowerPoint 產生失敗",message[:1000],message,stamp,stamp,job_id,"processing",token),
        )
    return bool(int(getattr(cur,"rowcount",0) or 0))


def requeue_stale_processing(cutoff: str) -> int:
    stamp = _now()
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        cur = conn.execute(
            f"UPDATE ai_presentation_jobs SET status={ph},claim_token={ph},started_at={ph},updated_at={ph},progress_percent={ph},"
            f"progress_stage={ph},progress_detail={ph} WHERE status={ph} AND updated_at<{ph}",
            ("queued","","",stamp,0,"等待產生 PowerPoint","前一個 AI Worker 已中斷，工作已重新排入佇列","processing",cutoff),
        )
    return int(getattr(cur,"rowcount",0) or 0)


def create_presentation(*, material_id, draft_id, template_id, group_key, training_area, title, slides,
                        actor_username, source_job_id, provider="", model="", artifact=None,
                        presentation_family_id="", parent_version_id="", revision_number=1):
    pid, stamp = f"ppt-{uuid.uuid4().hex}", _now(); family = presentation_family_id or pid; artifact = dict(artifact or {})
    slides_json = json.dumps(slides or [], ensure_ascii=False, separators=(",", ":"))
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind); j = _json(kind, ph)
        conn.execute(
            "INSERT INTO ai_presentations(id,presentation_family_id,parent_version_id,revision_number,material_id,draft_id,template_id,"
            "group_key,training_area,title,status,slides_json,artifact_backend,artifact_storage_key,artifact_storage_filename,artifact_sha256,"
            "artifact_bytes,artifact_mime_type,provider,model,source_job_id,created_by,updated_by,approved_by,approved_at,published_at,created_at,updated_at) VALUES("
            f"{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{j}," + ",".join([ph]*16) + ")",
            (pid,family,parent_version_id,max(1,int(revision_number)),material_id,draft_id,template_id,group_key,training_area,title,"draft",slides_json,
             str(artifact.get("backend") or "local"),str(artifact.get("key") or ""),str(artifact.get("filename") or ""),str(artifact.get("sha256") or ""),
             int(artifact.get("byteSize") or 0),str(artifact.get("mimeType") or ""),provider,model,source_job_id,actor_username,actor_username,"","","",stamp,stamp),
        )
    return get_presentation(pid) or {}


def get_presentation(presentation_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM ai_presentations WHERE id={ph}",(presentation_id,)).fetchone()
    return _presentation(row)


def get_presentation_by_source_job_id(source_job_id: str):
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(f"SELECT * FROM ai_presentations WHERE source_job_id={ph} ORDER BY created_at DESC LIMIT 1",(source_job_id,)).fetchone()
    return _presentation(row)


def list_presentations(*, group_key="", material_id="", limit=50):
    limit=max(1,min(100,int(limit)))
    with common_db.read_connection() as (conn,kind):
        ph, clauses, params=common_db.placeholder(kind),[],[]
        if group_key:
            clauses.append(f"group_key={ph}"); params.append(group_key)
        if material_id:
            clauses.append(f"material_id={ph}"); params.append(material_id)
        sql="SELECT * FROM ai_presentations" + ((" WHERE "+" AND ".join(clauses)) if clauses else "") + f" ORDER BY updated_at DESC LIMIT {ph}"
        rows=conn.execute(sql,tuple(params+[limit])).fetchall()
    return [_presentation(row) for row in rows]


def next_revision_number(family_id: str) -> int:
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind)
        row=conn.execute(f"SELECT MAX(revision_number) AS n FROM ai_presentations WHERE presentation_family_id={ph}",(family_id,)).fetchone()
    return int((dict(row).get("n") if row else 0) or 0)+1


def create_revision(current: Mapping[str,Any], *, actor_username: str, title=None, slides=None, artifact=None):
    family=str(current.get("presentationFamilyId") or current.get("id") or "")
    selected_slides = list(current.get("slides") or []) if slides is None else list(slides)
    return create_presentation(
        material_id=str(current.get("materialId") or ""), draft_id=str(current.get("draftId") or ""), template_id=str(current.get("templateId") or ""),
        group_key=str(current.get("group") or ""), training_area=str(current.get("area") or ""), title=str(current.get("title") if title is None else title),
        slides=selected_slides, actor_username=actor_username, source_job_id=str(current.get("sourceJobId") or ""),
        provider=str(current.get("provider") or ""), model=str(current.get("model") or ""), artifact=artifact or {
            "backend":current.get("artifactBackend"),"key":current.get("artifactStorageKey"),"filename":current.get("artifactStorageFilename"),
            "sha256":current.get("artifactSha256"),"byteSize":current.get("artifactBytes"),"mimeType":current.get("artifactMimeType")},
        presentation_family_id=family, parent_version_id=str(current.get("id") or ""), revision_number=next_revision_number(family))


def set_status(presentation_id: str, *, status: str, actor_username: str):
    if status not in PRESENTATION_STATUSES:
        raise ValueError("不支援的 PowerPoint 狀態。")
    stamp=_now()
    with common_db.transaction() as (conn,kind):
        ph=common_db.placeholder(kind)
        row=conn.execute(f"SELECT status,approved_by,approved_at FROM ai_presentations WHERE id={ph}",(presentation_id,)).fetchone()
        if not row:
            return None
        prev=dict(row)
        if status=="published" and str(prev.get("status") or "") not in {"approved","published"}:
            raise ValueError("PowerPoint 必須先由授課教師核准才能發布。")
        approved_by=str(prev.get("approved_by") or actor_username) if status=="published" else (actor_username if status=="approved" else "")
        approved_at=str(prev.get("approved_at") or stamp) if status=="published" else (stamp if status=="approved" else "")
        conn.execute(f"UPDATE ai_presentations SET status={ph},updated_by={ph},updated_at={ph},approved_by={ph},approved_at={ph},published_at={ph} WHERE id={ph}",
                     (status,actor_username,stamp,approved_by,approved_at,stamp if status=="published" else "",presentation_id))
    return get_presentation(presentation_id)


def publication_receipt_key(presentation_id: str, publication_material_id: str) -> str:
    return "pptpub-"+hashlib.sha256(f"{presentation_id}:{publication_material_id}".encode()).hexdigest()


def get_publication_by_key(key: str):
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind)
        row=conn.execute(f"SELECT * FROM ai_presentation_publications WHERE receipt_key={ph}",(key,)).fetchone()
    return _publication(row)


def create_publication(*, presentation_id, publication_material_id, actor_username, receipt):
    key=publication_receipt_key(presentation_id,publication_material_id); existing=get_publication_by_key(key)
    if existing:
        return existing
    stamp=_now(); payload=json.dumps(dict(receipt or {}),ensure_ascii=False,separators=(",",":")); pub_id=f"pptpub-{uuid.uuid4().hex}"
    with common_db.transaction() as (conn,kind):
        ph=common_db.placeholder(kind); j=_json(kind,ph)
        prefix="INSERT INTO" if kind=="postgres" else "INSERT OR IGNORE INTO"
        suffix=" ON CONFLICT(receipt_key) DO NOTHING" if kind=="postgres" else ""
        conn.execute(prefix+" ai_presentation_publications(id,presentation_id,publication_material_id,receipt_key,receipt_json,created_by,created_at) VALUES("
                     f"{ph},{ph},{ph},{ph},{j},{ph},{ph})"+suffix,(pub_id,presentation_id,publication_material_id,key,payload,actor_username,stamp))
    return get_publication_by_key(key) or {}


__all__ = ["create_template","get_template","list_templates","create_job","get_job","list_queued","claim_job","set_job_progress","complete_job","fail_job","requeue_stale_processing","create_presentation","get_presentation","get_presentation_by_source_job_id","list_presentations","next_revision_number","create_revision","set_status","publication_receipt_key","get_publication_by_key","create_publication"]
