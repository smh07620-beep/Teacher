"""Canonical PGY assessment/template persistence and validation."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Mapping

from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.auth import has_role, normalize_role


PGY_ASSESSMENT_TYPES = {
    "dops": "DOPS 直接觀察操作技能評量",
    "mini_cex": "MINI-CEX 臨床能力評估",
    "cbd": "CBD 案例討論",
    "checklist": "CHECKLIST 技能查核表",
    "qc": "QC 品管案例",
    "feedback360": "360 度評量",
    "report": "REPORT 學習報告",
    "qi": "QI 品質改善專案",
    "reflection": "REFLECTION 反思紀錄",
    "attendance": "ATTENDANCE 課程完成",
    "core6": "六大核心能力檢核表（舊版）",
    "adhoc": "Ad-hoc 即時評量表（舊版）",
    "epa": "EPA 可信賴專業活動即時評估（舊版）",
    "learning": "PGY 學習評量表（舊版）",
}

PGY_ASSESSMENT_ITEMS = {
    "dops": ["操作前準備與身分確認", "技術步驟與熟練度", "安全與感染管制", "檢體／設備品質管理", "溝通與專業態度", "整體操作能力"],
    "mini_cex": ["臨床任務與準備", "專業知識與判斷", "溝通與說明", "病人安全與專業態度", "整體臨床能力"],
    "cbd": ["案例摘要與問題辨識", "檢驗數據判讀", "鑑別與臨床連結", "處置或追蹤建議", "討論與反思"],
    "checklist": ["操作前準備", "病人／檢體識別", "SOP 步驟執行", "品質與安全確認", "操作後處理與紀錄"],
    "qc": ["品管資料檢視", "管制規則判斷", "異常原因分析", "矯正措施", "後續監測與紀錄"],
    "feedback360": ["團隊合作", "跨專業溝通", "尊重與同理", "責任感與可靠度", "專業態度"],
    "report": ["主題與問題定義", "資料與文獻運用", "分析與論證", "結論與應用", "書面／口頭表達"],
    "qi": ["問題辨識", "根本原因分析", "改善方案設計", "執行與團隊協作", "成效衡量與維持"],
    "reflection": ["事件描述", "倫理與全人觀點", "自我覺察", "學習重點", "後續行動"],
    "attendance": ["課前準備", "出席與參與", "課程任務完成", "重點理解", "學習應用"],
    "core6": ["病人／檢驗照護", "醫學與檢驗專業知識", "從工作中學習及成長", "人際與溝通技巧", "專業素養", "制度下之臨床工作"],
    "adhoc": ["任務準備", "任務執行", "結果確認／後處置"],
    "epa": ["OPA / 任務一", "OPA / 任務二", "OPA / 任務三"],
    "learning": ["學習態度與主動性", "專業知識與技能", "工作品質與病人安全", "團隊合作與溝通", "時間管理與責任感", "反思與持續改善"],
}

TSLM_EPA_REFERENCE_URL = "https://www.labmed.org.tw/upfiles/file/20240119/20240119172950815081.pdf"


class AssessmentError(ValueError):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def init_schema(connection_factory=None) -> None:
    if connection_factory is None:
        scope_cm = common_db.transaction()
        with scope_cm as (conn, kind):
            _create_schema(conn, kind)
        return
    conn, kind = connection_factory()
    try:
        _create_schema(conn, kind)
    finally:
        conn.close()


def _create_schema(conn, kind: str) -> None:
    details_type = "JSONB NOT NULL DEFAULT '{}'::jsonb" if kind == "postgres" else "TEXT NOT NULL DEFAULT '{}'"
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS pgy_assessments (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, assessment_type TEXT NOT NULL,
            group_key TEXT NOT NULL DEFAULT 'grpBio', name TEXT NOT NULL, emp_id TEXT NOT NULL,
            evaluator_name TEXT NOT NULL DEFAULT '', evaluator_title TEXT NOT NULL DEFAULT '',
            assessment_date TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
            details {details_type}, comments TEXT NOT NULL DEFAULT '',
            overall_score REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'completed'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pgy_assessment_templates (
            template_type TEXT PRIMARY KEY, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL,
            storage_backend TEXT NOT NULL DEFAULT 'local', storage_key TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT ''
        )
    """)


def assessment_to_dict(row) -> dict:
    data = dict(row)
    raw = data.pop("details", "{}") or "{}"
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    data["details"] = raw if isinstance(raw, dict) else {}
    data["assessmentType"] = data.pop("assessment_type", "")
    data["group"] = scope.normalize_group(data.pop("group_key", scope.DEFAULT_GROUP))
    data["empId"] = data.pop("emp_id", "")
    data["evaluatorName"] = data.pop("evaluator_name", "")
    data["evaluatorTitle"] = data.pop("evaluator_title", "")
    data["assessmentDate"] = data.pop("assessment_date", "")
    data["overallScore"] = float(data.pop("overall_score", 0) or 0)
    data["createdAt"] = data.pop("created_at", "")
    return data


def template_to_dict(row) -> dict:
    data = dict(row)
    template_type = data.get("template_type", "")
    return {
        "templateType": template_type,
        "label": PGY_ASSESSMENT_TYPES.get(template_type, "EPA 公版參考" if template_type == "epa_reference" else template_type),
        "filename": data.get("filename", ""),
        "uploadedAt": data.get("uploaded_at", ""),
        "storageBackend": data.get("storage_backend", "local"),
        "sourceUrl": data.get("source_url", ""),
        "exists": True,
    }


def list_templates() -> list[dict]:
    with common_db.read_connection() as (conn, _kind):
        rows = conn.execute("SELECT * FROM pgy_assessment_templates ORDER BY template_type").fetchall()
    return [template_to_dict(row) for row in rows]


def get_template(template_type: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM pgy_assessment_templates WHERE template_type={ph}",
            (template_type,),
        ).fetchone()
    return dict(row) if row else None


def save_template(template_type: str, filename: str, backend: str, key: str, source_url: str = "") -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with common_db.transaction() as (conn, kind):
        values = (template_type, filename, now, backend, key, source_url)
        if kind == "postgres":
            conn.execute("""INSERT INTO pgy_assessment_templates(template_type,filename,uploaded_at,storage_backend,storage_key,source_url)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(template_type) DO UPDATE SET
                filename=EXCLUDED.filename,uploaded_at=EXCLUDED.uploaded_at,storage_backend=EXCLUDED.storage_backend,
                storage_key=EXCLUDED.storage_key,source_url=EXCLUDED.source_url""", values)
        else:
            conn.execute("""INSERT INTO pgy_assessment_templates(template_type,filename,uploaded_at,storage_backend,storage_key,source_url)
                VALUES(?,?,?,?,?,?) ON CONFLICT(template_type) DO UPDATE SET
                filename=excluded.filename,uploaded_at=excluded.uploaded_at,storage_backend=excluded.storage_backend,
                storage_key=excluded.storage_key,source_url=excluded.source_url""", values)


def delete_template(template_type: str) -> None:
    with common_db.transaction() as (conn, kind):
        conn.execute(
            f"DELETE FROM pgy_assessment_templates WHERE template_type={common_db.placeholder(kind)}",
            (template_type,),
        )


def create_assessment(user: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    if not has_role(user, "clinical_teacher"):
        raise AssessmentError("權限不足：此操作限臨床教師使用。", 403)
    assessment_type = str(data.get("assessmentType", "")).strip()
    if assessment_type not in PGY_ASSESSMENT_TYPES:
        raise AssessmentError("評量類型不正確", 400)
    name = str(data.get("name", "")).strip()[:100]
    emp_id = str(data.get("empId", "")).strip()[:100]
    evaluator = str(user.get("name", "")).strip()[:100]
    if not name or not emp_id or not evaluator:
        raise AssessmentError("請填寫受評者姓名、工號與評估者", 400)
    group = scope.normalize_group(data.get("group", scope.DEFAULT_GROUP))
    if normalize_role(user.get("role")) == "clinical_teacher" and group != scope.normalize_group(user.get("preferredGroup")):
        raise AssessmentError("權限不足：臨床教師只能評核自己負責組別的學員。", 403)
    details = data.get("details") or {}
    if not isinstance(details, dict):
        raise AssessmentError("評核明細格式錯誤", 400)
    ratings = details.get("ratings") or []
    expected = PGY_ASSESSMENT_ITEMS.get(assessment_type, [])
    if not isinstance(ratings, list) or len(ratings) != len(expected):
        raise AssessmentError(f"教師評核必須完成全部 {len(expected)} 項評分", 400)
    normalized_ratings = []
    for index, item_name in enumerate(expected):
        row = ratings[index] if index < len(ratings) and isinstance(ratings[index], dict) else {}
        try:
            rating = int(row.get("rating", 0) or 0)
        except Exception:
            rating = 0
        if rating not in {1, 2, 3, 4, 5}:
            raise AssessmentError(f"第 {index + 1} 項「{item_name}」尚未完成 1–5 分評核", 400)
        normalized_ratings.append({"item": item_name, "rating": rating, "note": str(row.get("note", ""))[:1000]})
    details = {"ratings": normalized_ratings}
    record_id = uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    assessment_date = str(data.get("assessmentDate", "")).strip()[:30] or now[:10]
    title = str(data.get("title", PGY_ASSESSMENT_TYPES[assessment_type])).strip()[:255]
    comments = str(data.get("comments", "")).strip()[:4000]
    score = sum(item["rating"] for item in normalized_ratings) / len(normalized_ratings) if normalized_ratings else 0
    payload = json.dumps(details, ensure_ascii=False)
    with common_db.transaction() as (conn, kind):
        values = (
            record_id, now, assessment_type, group, name, emp_id, evaluator, "臨床教師",
            assessment_date, title, payload, comments, score, "completed",
        )
        if kind == "postgres":
            conn.execute("INSERT INTO pgy_assessments(id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,evaluator_title,assessment_date,title,details,comments,overall_score,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)", values)
        else:
            conn.execute("INSERT INTO pgy_assessments(id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,evaluator_title,assessment_date,title,details,comments,overall_score,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
    return record_id


def list_assessments(
    user: Mapping[str, Any] | None,
    *,
    emp_id: str = "",
    group: str | None = None,
    admin_override: bool = False,
) -> list[dict]:
    if not admin_override and not user:
        raise AssessmentError("請先登入後查看評量紀錄", 401)
    role = normalize_role((user or {}).get("role"))
    if not admin_override and role == "student":
        emp_id = str((user or {}).get("empId", ""))
    scoped_group = ""
    if not admin_override and role in {"clinical_teacher", "group_leader"}:
        own_group = scope.normalize_group((user or {}).get("preferredGroup"))
        # Preserve the legacy distinction between an omitted group query and an
        # explicitly empty `?group=` query.  Omitted means "my own group";
        # explicit empty normalizes to the platform default group.
        requested_group = scope.normalize_group(own_group if group is None else group)
        if requested_group != own_group:
            raise AssessmentError("權限不足：臨床教師只能查看自己負責組別的評量。", 403)
        scoped_group = own_group
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        if scoped_group:
            rows = conn.execute(f"SELECT * FROM pgy_assessments WHERE group_key={ph} ORDER BY created_at DESC", (scoped_group,)).fetchall()
        elif emp_id:
            rows = conn.execute(f"SELECT * FROM pgy_assessments WHERE emp_id={ph} ORDER BY created_at DESC", (emp_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pgy_assessments ORDER BY created_at DESC").fetchall()
    return [assessment_to_dict(row) for row in rows]


__all__ = [
    "AssessmentError", "PGY_ASSESSMENT_ITEMS", "PGY_ASSESSMENT_TYPES", "TSLM_EPA_REFERENCE_URL",
    "create_assessment", "delete_template", "get_template", "init_schema", "list_assessments",
    "list_templates", "save_template", "template_to_dict",
]
