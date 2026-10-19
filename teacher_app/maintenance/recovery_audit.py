"""F6 read-only recovery integrity audit for DB references and R2 ledger."""
from __future__ import annotations

import json
from typing import Any, Callable

from teacher_app.common import db as common_db

# Cap on how many unexplained orphan materials are described in the report.
ORPHAN_SAMPLE_LIMIT = 50


def _tables(conn, kind: str) -> set[str]:
    if kind == "postgres":
        rows=conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        return {str(dict(row).get("tablename") or "") for row in rows}
    rows=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(dict(row).get("name") or "") for row in rows}


def _count(conn, sql: str, params=()) -> int:
    try:
        row=conn.execute(sql,params).fetchone()
        if not row:
            return 0
        data=dict(row)
        return int(next(iter(data.values())) or 0)
    except Exception:
        return 0


def _rollback_quietly(conn) -> None:
    # PostgreSQL aborts the transaction after a failed statement; clear it so the
    # remaining audit checks still run.
    try:
        conn.rollback()
    except Exception:
        pass


def _is_authoring_source(snapshot: dict) -> bool:
    """True for the private AI-authoring source materials that retention removes.

    Uses the same rule as ``retention`` (24 h purge of "authoring only" sources),
    which deletes the catalog row but, by design, writes only one summary audit
    event, not one ``material.delete`` event per material.
    """
    try:
        from teacher_app.maintenance import retention

        return bool(retention._is_authoring_source(snapshot))  # noqa: SLF001 - shared rule
    except Exception:
        return False


def _orphan_version_samples(conn, kind: str, present: set[str]) -> list[dict[str, Any]]:
    """Describe material versions whose material row is gone, grouped per material.

    Read-only and best effort: any failure returns an empty list so the audit
    itself never breaks.  Only unexplained orphans (no ``material.delete`` audit
    event) are listed, i.e. exactly what the error count covers.
    """
    ph = common_db.placeholder(kind)
    sql = (
        "SELECT v.* FROM material_versions v "
        "LEFT JOIN materials m ON m.id=v.material_id WHERE m.id IS NULL"
    )
    if "audit_events" in present:
        sql += (
            " AND NOT EXISTS (SELECT 1 FROM audit_events a "
            "WHERE a.action='material.delete' AND a.target_type='material' "
            "AND a.target_id=v.material_id)"
        )
    sql += " ORDER BY v.material_id, v.version"
    try:
        rows = [dict(row) for row in conn.execute(sql).fetchall()]
    except Exception:
        _rollback_quietly(conn)
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        material_id = str(row.get("material_id") or "")
        entry = grouped.setdefault(
            material_id,
            {"materialId": material_id, "versions": [], "authoringSource": False, "title": "", "group": "",
             "firstPublishedAt": "", "lastPublishedAt": "", "publishedBy": "",
             "changeReason": "", "lastAuditAction": "", "lastAuditAt": ""},
        )
        entry["versions"].append(row.get("version"))
        published_at = str(row.get("published_at") or "")
        if published_at:
            entry["firstPublishedAt"] = min(filter(None, [entry["firstPublishedAt"], published_at]))
            entry["lastPublishedAt"] = max(entry["lastPublishedAt"], published_at)
        entry["publishedBy"] = str(row.get("published_by") or entry["publishedBy"])
        entry["changeReason"] = str(row.get("change_reason") or entry["changeReason"])[:120]
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, dict):  # TEXT on SQLite, already a dict on PostgreSQL JSONB
            try:
                snapshot = json.loads(str(snapshot or "{}"))
            except Exception:
                snapshot = {}
        if isinstance(snapshot, dict):
            if _is_authoring_source(snapshot):
                entry["authoringSource"] = True
            entry["title"] = str(snapshot.get("title") or entry["title"])[:120]
            entry["group"] = str(snapshot.get("group") or snapshot.get("group_key") or entry["group"])
    return list(grouped.values())


def _attach_last_audit(conn, kind: str, present: set[str], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ph = common_db.placeholder(kind)
    items = items[:ORPHAN_SAMPLE_LIMIT]
    if "audit_events" in present:
        for entry in items:
            try:
                last = conn.execute(
                    "SELECT action, created_at FROM audit_events "
                    f"WHERE target_type='material' AND target_id={ph} "
                    "ORDER BY created_at DESC LIMIT 1",
                    (entry["materialId"],),
                ).fetchone()
            except Exception:
                _rollback_quietly(conn)
                last = None
            if last:
                data = dict(last)
                entry["lastAuditAction"] = str(data.get("action") or "")
                entry["lastAuditAt"] = str(data.get("created_at") or "")
    return items


def build_recovery_audit(connection_factory: Callable | None = None) -> dict[str, Any]:
    factory=connection_factory or common_db.get_connection
    conn,kind=factory()
    try:
        ph=common_db.placeholder(kind)
        present=_tables(conn,kind)
        checks=[]

        def add(key,label,count,severity="error",detail="",items=None):
            check={
                "key":key,"label":label,"count":int(count or 0),
                "ok":int(count or 0)==0 or severity=="info","severity":severity,"detail":detail,
            }
            if items:
                check["items"]=items
            checks.append(check)

        if {"material_versions","materials"} <= present:
            orphan_sql=(
                "SELECT COUNT(*) AS n FROM material_versions v "
                "LEFT JOIN materials m ON m.id=v.material_id WHERE m.id IS NULL"
            )
            total_orphans=_count(conn,orphan_sql)
            # delete_material() removes the catalog row but deliberately keeps the
            # immutable version history (and its provider storage). Orphans whose
            # material has a recorded material.delete audit event are that retained
            # history, not corruption; only unexplained orphans stay an error.
            retained=0
            if total_orphans and "audit_events" in present:
                retained=_count(
                    conn,
                    orphan_sql+" AND EXISTS (SELECT 1 FROM audit_events a "
                    "WHERE a.action='material.delete' AND a.target_type='material' "
                    "AND a.target_id=v.material_id)",
                )
            unexplained=total_orphans-retained
            groups=_orphan_version_samples(conn,kind,present) if unexplained else []
            authoring_groups=[g for g in groups if g["authoringSource"]]
            other_groups=[g for g in groups if not g["authoringSource"]]
            authoring_rows=sum(len(g["versions"]) for g in authoring_groups)
            real_orphans=max(0,unexplained-authoring_rows)
            add(
                "orphan_material_versions","教材版本找不到主教材",
                real_orphans,
                detail=(
                    "這些教材已不在教材清單，且找不到「刪除教材」的稽核紀錄；"
                    "請對照下方明細確認是否為以前刪除的舊教材。"
                ) if real_orphans else "",
                items=_attach_last_audit(conn,kind,present,other_groups) if real_orphans else None,
            )
            if authoring_rows:
                add(
                    "purged_authoring_sources","AI 講稿私人來源（已依 24 小時規則自動清除）",
                    authoring_rows,severity="info",
                    detail="AI 講稿用的私人來源教材沒有加入課程，系統依 24 小時保留規則自動清除，只留下版本歷史；這是設計行為，不是損壞。",
                    items=_attach_last_audit(conn,kind,present,authoring_groups),
                )
            if retained:
                add(
                    "retained_material_versions","已刪除教材保留的版本歷史",
                    retained,severity="info",
                    detail="教材刪除時系統刻意保留版本歷史與儲存檔案，以便日後還原；這是設計行為，不是損壞。",
                )
        if {"material_derivative_publications","materials"} <= present:
            add(
                "orphan_material_derivatives","AI 衍生內容找不到主教材",
                _count(conn,"SELECT COUNT(*) AS n FROM material_derivative_publications d LEFT JOIN materials m ON m.id=d.material_id WHERE m.id IS NULL"),
            )
        if {"ai_presentations","materials"} <= present:
            add(
                "orphan_presentations","AI PowerPoint 找不到來源教材",
                _count(conn,"SELECT COUNT(*) AS n FROM ai_presentations p LEFT JOIN materials m ON m.id=p.material_id WHERE p.material_id<>'' AND m.id IS NULL"),
            )
        if {"ai_presentation_videos","ai_presentations"} <= present:
            add(
                "orphan_videos","AI 影片找不到來源 PowerPoint",
                _count(conn,"SELECT COUNT(*) AS n FROM ai_presentation_videos v LEFT JOIN ai_presentations p ON p.id=v.presentation_id WHERE p.id IS NULL"),
            )
        if {"quiz_questions","materials"} <= present:
            add(
                "orphan_question_sources","考題來源教材已不存在",
                _count(conn,"SELECT COUNT(*) AS n FROM quiz_questions q LEFT JOIN materials m ON m.id=q.source_material_id WHERE q.source_material_id<>'' AND m.id IS NULL"),
            )
        if {"learning_assignments","courses"} <= present:
            add(
                "orphan_assignments","學習指派找不到課程",
                _count(conn,"SELECT COUNT(*) AS n FROM learning_assignments a LEFT JOIN courses c ON c.id=a.course_id WHERE c.id IS NULL"),
            )
        if {"material_derivative_publications","r2_usage_ledger"} <= present:
            add(
                "untracked_r2_derivatives","R2 衍生 artifact 缺少 live ledger 紀錄",
                _count(
                    conn,
                    "SELECT COUNT(*) AS n FROM material_derivative_publications d "
                    "LEFT JOIN r2_usage_ledger r ON r.object_key=d.artifact_storage_key AND r.deleted_at='' "
                    "WHERE d.artifact_backend='r2' AND d.artifact_storage_key<>'' AND r.object_key IS NULL",
                ),
                severity="warning",
                detail="R2 ledger 是站內觀測紀錄；此項異常需要再對遠端物件確認。",
            )

        errors=sum(item["count"] for item in checks if item["severity"]=="error")
        warnings=sum(item["count"] for item in checks if item["severity"]=="warning")
        return {
            "ok":errors==0,
            "status":"healthy" if errors==0 and warnings==0 else "warning" if errors==0 else "broken_references",
            "checks":checks,
            "errorCount":errors,
            "warningCount":warnings,
        }
    finally:
        conn.close()


__all__=["build_recovery_audit"]
