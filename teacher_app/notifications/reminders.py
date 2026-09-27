"""Periodic email reminders for unfinished assigned learning and exams."""
from __future__ import annotations
import datetime as dt, os, uuid
from teacher_app.auth import repository as auth_repository
from teacher_app.auth.self_service import _send
from teacher_app.common import db as common_db
from teacher_app.learning import assignment_service, progress_service

def _parse(v):
    if not v:return None
    try:return dt.datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:return None

def _claim(username,key,kind):
    with common_db.transaction() as (conn,dbkind):
        ph=common_db.placeholder(dbkind)
        try:conn.execute(f"INSERT INTO email_notification_log(id,username,notification_key,kind,sent_at) VALUES ({','.join([ph]*5)})",(uuid.uuid4().hex,username,key,kind,dt.datetime.now(dt.timezone.utc).isoformat()));return True
        except Exception:return False

def run_due_reminders():
    now=dt.datetime.now(dt.timezone.utc); horizon=now+dt.timedelta(days=max(1,int(os.getenv("EMAIL_REMINDER_DAYS","3") or 3))); sent=0
    for row in auth_repository.list_users():
        if not row.get("active") or not row.get("email") or not row.get("email_notifications",True):continue
        user={"username":row["username"],"name":row.get("display_name",""),"empId":row.get("emp_id",""),"role":row.get("role","student"),"roles":row.get("roles_json"),"preferredArea":row.get("preferred_area","internal"),"preferredGroup":row.get("preferred_group","grpBio")}
        try:
            assignments=assignment_service.list_for_user(user)
            progress=progress_service.my_progress(user,area=user["preferredArea"],group=user["preferredGroup"])
        except Exception:continue
        completed={str(c.get("id")) for c in progress.get("courses",[]) if c.get("completed")}
        lines=[]
        for a in assignments:
            due=_parse(a.get("dueAt"))
            if a.get("required") and a.get("courseId") not in completed and due and now<=due<=horizon:
                lines.append(f"課程 {a.get('courseId')}：截止 {due.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}")
        # Published exams with an upcoming close date are reminded when the
        # learner has not yet submitted a passing/completed record.
        try:
            with common_db.read_connection() as (conn,dbkind):
                ph=common_db.placeholder(dbkind)
                windows=conn.execute("SELECT w.quiz_category_id,w.closes_at,c.title FROM exam_windows w JOIN quiz_categories c ON c.id=w.quiz_category_id WHERE w.reminder_enabled="+("TRUE" if dbkind=="postgres" else "1")+" AND c.training_area="+ph+" AND c.group_key="+ph,(user["preferredArea"],user["preferredGroup"])).fetchall()
                done=conn.execute(f"SELECT DISTINCT quiz_category_id FROM exam_records WHERE emp_id={ph}",(user["empId"],)).fetchall()
            completed_exams={str(dict(x).get("quiz_category_id") or "") for x in done}
            for raw in windows:
                item=dict(raw); due=_parse(item.get("closes_at")); cid=str(item.get("quiz_category_id") or "")
                if cid not in completed_exams and due and now<=due<=horizon:
                    lines.append(f"考核 {item.get('title') or cid}：最後作答 {due.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}")
        except Exception:pass
        if not lines:continue
        day=now.astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat(); key=f"learning-due:{day}"
        if not _claim(row["username"],key,"learning_due"):continue
        try:
            if _send(row["email"],"醫學檢驗教學平台｜待完成學習提醒","您好 "+str(row.get("display_name") or row["username"])+"：\n\n以下項目即將到期：\n"+"\n".join(lines)+"\n\n請登入教學平台完成。"):sent+=1
        except Exception:pass
    return sent
__all__=["run_due_reminders"]
