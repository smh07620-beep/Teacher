"""F6 read-only recovery integrity audit for DB references and R2 ledger."""
from __future__ import annotations

from typing import Any, Callable

from teacher_app.common import db as common_db


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


def build_recovery_audit(connection_factory: Callable | None = None) -> dict[str, Any]:
    factory=connection_factory or common_db.get_connection
    conn,kind=factory()
    try:
        ph=common_db.placeholder(kind)
        present=_tables(conn,kind)
        checks=[]

        def add(key,label,count,severity="error",detail=""):
            checks.append({
                "key":key,"label":label,"count":int(count or 0),
                "ok":int(count or 0)==0 or severity=="info","severity":severity,"detail":detail,
            })

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
            add(
                "orphan_material_versions","教材版本找不到主教材",
                total_orphans-retained,
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
