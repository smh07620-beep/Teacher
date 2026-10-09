"""Course-centric teacher follow-up projection for F2."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Mapping, Optional

from teacher_app.assessments import repository as assessment_repository
from teacher_app.auth import accounts as auth_accounts
from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import assignment_service, completion, versioning
from teacher_app.materials import repository as material_repository


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
    text=str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text=text[:-1]+"+00:00"
    try:
        value=dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value=value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _bool(value: Any) -> bool:
    if isinstance(value,str):
        return value.strip().lower() not in {"","0","false","no","off"}
    return bool(value)


def _progress_rows(usernames: list[str]) -> list[dict]:
    if not usernames:
        return []
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind)
        marks=",".join(ph for _ in usernames)
        try:
            rows=conn.execute(
                f"SELECT material_id,username,progress,completed,completed_version,last_viewed_at "
                f"FROM learning_progress WHERE LOWER(username) IN ({marks})",
                tuple(usernames),
            ).fetchall()
        except Exception:
            rows=conn.execute(
                f"SELECT material_id,username,progress,completed,last_viewed_at "
                f"FROM learning_progress WHERE LOWER(username) IN ({marks})",
                tuple(usernames),
            ).fetchall()
    return [dict(row) for row in rows]


def _legacy_progress_rows(emp_ids: list[str]) -> list[dict]:
    if not emp_ids:
        return []
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind)
        marks=",".join(ph for _ in emp_ids)
        try:
            rows=conn.execute(
                f"SELECT emp_id,material_id,completed_at,completed_version "
                f"FROM material_progress WHERE emp_id IN ({marks})",
                tuple(emp_ids),
            ).fetchall()
        except Exception:
            rows=conn.execute(
                f"SELECT emp_id,material_id,completed_at "
                f"FROM material_progress WHERE emp_id IN ({marks})",
                tuple(emp_ids),
            ).fetchall()
    return [dict(row) for row in rows]


def _exam_rows(emp_ids: list[str]) -> list[dict]:
    if not emp_ids:
        return []
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind)
        marks=",".join(ph for _ in emp_ids)
        rows=conn.execute(
            f"SELECT emp_id,course_id,quiz_category_id,score,review_status,passing_score,created_at "
            f"FROM exam_records WHERE emp_id IN ({marks}) ORDER BY created_at DESC",
            tuple(emp_ids),
        ).fetchall()
    return [dict(row) for row in rows]


def _account_rows() -> list[dict]:
    rows=[]
    for raw in auth_accounts.list_accounts():
        item=dict(raw)
        if not item.get("active",True):
            continue
        username=str(item.get("username") or "").strip().lower()
        if not username:
            continue
        rows.append({
            "username":username,
            "name":str(item.get("name") or item.get("displayName") or username)[:100],
            "empId":str(item.get("empId") or "")[:100],
            "area":str(item.get("preferredArea") or "internal"),
            "group":str(item.get("preferredGroup") or "grpBio"),
        })
    return rows


def _expand_assignment(assignment: Mapping[str,Any], accounts: list[dict]) -> list[dict]:
    kind=str(assignment.get("assigneeType") or "")
    key=str(assignment.get("assigneeKey") or "").strip().lower()
    area=str(assignment.get("area") or "")
    group=str(assignment.get("group") or "")
    if kind=="user":
        return [row for row in accounts if row["username"]==key]
    if kind=="group":
        return [row for row in accounts if row["area"]==area and row["group"]==group]
    if kind=="all":
        return [row for row in accounts if row["area"]==area]
    return []


def _completion_current(material: Mapping[str,Any], completed: Any, completed_version: Any) -> bool:
    if not _bool(completed):
        return False
    if completed_version in (None,""):
        return True
    return bool(versioning.classify_completion(material,completed_version)["completionCurrent"])


def build_course_tracking(
    user: Optional[Mapping[str,Any]],
    *,
    course_id: str="",
    now: Optional[dt.datetime]=None,
) -> dict[str,Any]:
    if not user:
        raise ApiError("LOGIN_REQUIRED","請先登入後再查看課程追蹤。",status=401,extra={"loginRequired":True})
    if not has_permission(user,"learning.assign"):
        raise ApiError("FORBIDDEN","此帳號沒有課程追蹤權限。",status=403)

    current=now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current=current.replace(tzinfo=dt.timezone.utc)
    current=current.astimezone(dt.timezone.utc)

    assignments=assignment_service.admin_list(user,include_inactive=False)
    wanted=str(course_id or "").strip()
    if wanted:
        assignments=[row for row in assignments if str(row.get("courseId") or "")==wanted]

    accounts=_account_rows()
    course_assignments=defaultdict(list)
    recipients: dict[tuple[str,str],dict[str,Any]]={}
    due_by_recipient: dict[tuple[str,str],str]={}
    for assignment in assignments:
        cid=str(assignment.get("courseId") or "")
        if not cid:
            continue
        course_assignments[cid].append(assignment)
        for learner in _expand_assignment(assignment,accounts):
            key=(cid,learner["username"])
            recipients[key]=learner
            due=str(assignment.get("dueAt") or "")
            if due and (not due_by_recipient.get(key) or due<due_by_recipient[key]):
                due_by_recipient[key]=due

    course_ids=sorted(course_assignments)
    courses={cid:course_repository.get_course(cid) for cid in course_ids}
    courses={cid:row for cid,row in courses.items() if row}
    materials=material_repository.list_uploaded_materials(include_inactive=False)
    exams=assessment_repository.list_categories(include_inactive=False)

    learner_rows=list(recipients.values())
    usernames=sorted({row["username"] for row in learner_rows})
    emp_ids=sorted({row["empId"] for row in learner_rows if row["empId"]})
    smart=_progress_rows(usernames)
    legacy=_legacy_progress_rows(emp_ids)
    exam_rows=_exam_rows(emp_ids)

    output=[]
    totals={"assigned":0,"notStarted":0,"inProgress":0,"completed":0,"overdue":0,"examNotPassed":0}
    for cid in course_ids:
        course=courses.get(cid)
        if not course:
            continue
        course_materials=[row for row in materials if str(row.get("courseId") or "")==cid]
        course_exams=[row for row in exams if str(row.get("courseId") or "")==cid]
        learners=[]
        for key,learner in recipients.items():
            if key[0]!=cid:
                continue
            username=learner["username"]
            emp_id=learner["empId"]
            smart_rows=[row for row in smart if str(row.get("username") or "").lower()==username and any(str(m.get("id") or "")==str(row.get("material_id") or "") for m in course_materials)]
            legacy_rows=[row for row in legacy if str(row.get("emp_id") or "")==emp_id and any(str(m.get("id") or "")==str(row.get("material_id") or "") for m in course_materials)]
            completed_material_ids=set()
            progress_by_material={}
            for row in smart_rows:
                mid=str(row.get("material_id") or "")
                material=next((m for m in course_materials if str(m.get("id") or "")==mid),None)
                if material and _completion_current(material,row.get("completed"),row.get("completed_version")):
                    completed_material_ids.add(mid)
                progress_by_material[mid]=max(0.0,min(100.0,float(row.get("progress") or 0)))
            for row in legacy_rows:
                mid=str(row.get("material_id") or "")
                material=next((m for m in course_materials if str(m.get("id") or "")==mid),None)
                if material and _completion_current(material,True,row.get("completed_version")):
                    completed_material_ids.add(mid)
                    progress_by_material[mid]=100.0

            learner_exams=[row for row in exam_rows if str(row.get("emp_id") or "")==emp_id and str(row.get("course_id") or "")==cid]
            passed_exam_ids={
                str(row.get("quiz_category_id") or "")
                for row in learner_exams
                if str(row.get("review_status") or "completed")!="pending"
                and float(row.get("score") or 0)>=float(row.get("passing_score") or 80)
            }
            course_completion=completion.evaluate_course_completion(
                materials=course_materials,
                exams=course_exams,
                completed_material_ids=completed_material_ids,
                passed_exam_ids=passed_exam_ids,
                policy=course.get("completionPolicy"),
            )
            material_progress=round(sum(progress_by_material.values())/len(course_materials),1) if course_materials else 100.0
            started=bool(smart_rows or legacy_rows or learner_exams)
            complete=bool(course_completion.get("completed"))
            due=due_by_recipient.get((cid,username),"")
            overdue=bool((parsed:=_parse_datetime(due)) and parsed<current and not complete)
            reviewed=[row for row in learner_exams if str(row.get("review_status") or "completed")!="pending"]
            exam_not_passed=bool(course_exams and reviewed and not course_completion.get("examPassed"))
            status="completed" if complete else "inProgress" if started else "notStarted"
            totals["assigned"]+=1
            totals[status]+=1
            totals["overdue"]+=int(overdue)
            totals["examNotPassed"]+=int(exam_not_passed)
            learners.append({
                **learner,
                "status":status,
                "materialProgress":material_progress,
                "materialsCompleted":len(completed_material_ids),
                "materialsTotal":len(course_materials),
                "examRequired":bool(course_completion.get("examRequired")),
                "examPassed":bool(course_completion.get("examPassed")),
                "examAttempts":len(learner_exams),
                "examNotPassed":exam_not_passed,
                "dueAt":due,
                "overdue":overdue,
            })
        learners.sort(key=lambda row:(0 if row["overdue"] else 1,0 if row["examNotPassed"] else 1,{"notStarted":0,"inProgress":1,"completed":2}.get(row["status"],9),row["name"],row["username"]))
        output.append({
            "courseId":cid,
            "title":course.get("title",""),
            "area":course.get("area",""),
            "group":course.get("group",""),
            "lifecycleStatus":course.get("lifecycleStatus",""),
            "summary":{
                "assigned":len(learners),
                "notStarted":sum(1 for row in learners if row["status"]=="notStarted"),
                "inProgress":sum(1 for row in learners if row["status"]=="inProgress"),
                "completed":sum(1 for row in learners if row["status"]=="completed"),
                "overdue":sum(1 for row in learners if row["overdue"]),
                "examNotPassed":sum(1 for row in learners if row["examNotPassed"]),
            },
            "learners":learners,
        })

    return {
        "generatedAt":current.isoformat(),
        "summary":totals,
        "courses":output,
        "source":"canonical-learning-assignments-progress-and-exam-records",
        "interpretation":"course_followup_without_synthetic_mastery",
    }


__all__=["build_course_tracking"]
