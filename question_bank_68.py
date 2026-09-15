"""Question Bank 2.0 review, duplicate and blueprint APIs."""
from __future__ import annotations
import datetime as dt, hashlib, json, random, re, uuid
from collections import Counter
from flask import jsonify, request

VALID={"difficulty":{"easy","medium","hard","standard"},"cognitive_level":{"remember","understand","apply","analyze"},"status":{"draft","reviewed","published","retired"},"origin":{"manual","ai_generated","imported"}}
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def normalized(v):return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "",str(v).lower())).strip()
def similarity(a,b):
    x,y=set(normalized(a).split()),set(normalized(b).split());return len(x&y)/max(1,len(x|y))
def permitted(base):
    denied=base.require_admin();return denied
def metadata(data):
    out={k:data.get(k,"") for k in ("domain","topic","subtopic","learning_objective","source_material_id","review_source")}
    for k,default in (("difficulty","medium"),("cognitive_level","understand"),("status","draft"),("origin","manual")):
        out[k]=str(data.get(k,default));
        if out[k] not in VALID[k]:raise ValueError(f"{k} 格式錯誤")
    out["tags"]=data.get("tags",[])
    if not isinstance(out["tags"],list):raise ValueError("tags 格式錯誤")
    return out
def _decode(value, fallback):
    try:return json.loads(value) if isinstance(value,str) else value
    except Exception:return fallback
def _draw(rows, count, quotas):
    """Draw server-side, meeting each requested metadata quota where possible."""
    selected=[]; used=set()
    for field in ("topic","difficulty","cognitive_level"):
        requested=quotas.get(field,{})
        if not isinstance(requested,dict):continue
        for value, amount in requested.items():
            candidates=[r for r in rows if str(r.get(field) or "")==str(value) and r["id"] not in used]
            random.shuffle(candidates)
            take=max(0,int(amount or 0))
            if len(candidates)<take:raise ValueError(f"{field} quota 無足夠已審核題目：{value}")
            for row in candidates[:take]:selected.append(row);used.add(row["id"])
    remainder=[r for r in rows if r["id"] not in used];random.shuffle(remainder)
    if len(selected)+len(remainder)<count:raise ValueError("已審核題目不足以建立 blueprint")
    return selected+remainder[:count-len(selected)]
def register_question_bank(base):
    app=base.app
    if app.extensions.get("teacher_question_bank_68_registered"):return app
    @app.post("/api/question-bank/drafts")
    def create_draft():
        denied=permitted(base)
        if denied:return denied
        body=request.get_json(silent=True) or {}
        try:m=metadata(body)
        except ValueError as exc:return jsonify({"error":str(exc)}),400
        if not str(body.get("question") or "").strip() or not isinstance(body.get("options"),list):return jsonify({"error":"題目與選項為必填"}),400
        # AI inputs are schema validated and always forced to draft.
        if m["origin"]=="ai_generated":m["status"]="draft"
        qid=str(uuid.uuid4()); text=str(body["question"]).strip(); h=hashlib.sha256(normalized(text).encode()).hexdigest()
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            rows=conn.execute("SELECT id,question,normalized_hash FROM quiz_questions").fetchall(); dup=[{"id":dict(r)["id"],"similarity":round(similarity(text,dict(r)["question"]),2)} for r in rows if dict(r).get("normalized_hash")==h or similarity(text,dict(r)["question"])>=.85]
            values=(qid,str(body.get("quizCategoryId") or ""),str(body.get("tag") or ""),text,str(body.get("questionType") or "choice"),json.dumps(body["options"],ensure_ascii=False),int(body.get("correct",0) or 0),str(body.get("explanation") or ""),m["domain"],m["topic"],m["subtopic"],m["learning_objective"],m["difficulty"],m["cognitive_level"],json.dumps(m["tags"],ensure_ascii=False),m["source_material_id"],json.dumps(m["review_source"],ensure_ascii=False),m["status"],m["origin"],now(),h)
            sql=f"INSERT INTO quiz_questions(id,quiz_category_id,tag,question,question_type,options,correct,explanation,domain,topic,subtopic,learning_objective,difficulty,cognitive_level,tags,source_material_id,review_source,status,origin,updated_at,normalized_hash) VALUES({','.join([ph]*21)})"
            conn.execute(sql,values)
        finally:conn.close()
        return jsonify({"id":qid,"status":m["status"],"suspectedDuplicates":dup}),201
    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied=permitted(base)
        if denied:return denied
        decision=str((request.get_json(silent=True) or {}).get("decision") or "")
        if decision not in {"accept","reject"}:return jsonify({"error":"decision 格式錯誤"}),400
        user=base._current_user() or {}; conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            if decision=="accept":cur=conn.execute(f"UPDATE quiz_questions SET status={ph},reviewed_by={ph},reviewed_at={ph},updated_at={ph},version=version+1 WHERE id={ph} AND status='draft'",("reviewed",user.get("username",""),now(),now(),question_id))
            else:cur=conn.execute(f"UPDATE quiz_questions SET status={ph},updated_at={ph},version=version+1 WHERE id={ph}",("retired",now(),question_id))
        finally:conn.close()
        return jsonify({"ok":bool(getattr(cur,"rowcount",0))})
    @app.post("/api/exam-blueprints")
    def blueprint():
        denied=permitted(base)
        if denied:return denied
        b=request.get_json(silent=True) or {}; count=max(1,min(500,int(b.get("questionCount",0) or 0))); quotas=b.get("quotas") or {}
        if not isinstance(quotas,dict):return jsonify({"error":"quotas 格式錯誤"}),400
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?";qid=str(uuid.uuid4())
        try:conn.execute(f"INSERT INTO exam_blueprints(id,quiz_category_id,question_count,quotas,exclude_recent,created_by,created_at) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph})",(qid,str(b.get("quizCategoryId") or ""),count,json.dumps(quotas),max(0,int(b.get("excludeRecent",0) or 0)),(base._current_user() or {}).get("username",""),now()))
        finally:conn.close()
        return jsonify({"id":qid,"questionCount":count,"immutableSnapshotRequired":True}),201
    @app.get("/api/questions/<question_id>/analytics")
    def analytics(question_id):
        denied=permitted(base)
        if denied:return denied
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try: rows=conn.execute(f"SELECT selected_option,is_correct FROM question_attempt_analytics WHERE question_id={ph}",(question_id,)).fetchall()
        finally:conn.close()
        n=len(rows)
        if n<10:return jsonify({"attemptCount":n,"sufficientData":False,"message":"資料不足"})
        vals=[dict(r) for r in rows];return jsonify({"attemptCount":n,"sufficientData":True,"correctRate":round(sum(bool(r["is_correct"]) for r in vals)/n,3),"optionSelectionCounts":dict(Counter(r["selected_option"] for r in vals))})
    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied=permitted(base)
        if denied:return denied
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            existing=conn.execute(f"SELECT id,questions,created_at FROM exam_blueprint_snapshots WHERE blueprint_id={ph}",(blueprint_id,)).fetchone()
            if existing:
                row=dict(existing);return jsonify({"id":row["id"],"blueprintId":blueprint_id,"questions":_decode(row["questions"],[]),"createdAt":row["created_at"],"immutable":True})
            bp=conn.execute(f"SELECT * FROM exam_blueprints WHERE id={ph}",(blueprint_id,)).fetchone()
            if not bp:return jsonify({"error":"找不到 blueprint"}),404
            bp=dict(bp); rows=[dict(r) for r in conn.execute(f"SELECT * FROM quiz_questions WHERE quiz_category_id={ph} AND status IN ('reviewed','published') AND active={ 'TRUE' if kind=='postgres' else '1'}",(bp["quiz_category_id"],)).fetchall()]
            try:chosen=_draw(rows,int(bp["question_count"]),_decode(bp["quotas"],{}))
            except ValueError as exc:return jsonify({"error":str(exc)}),409
            # Stored snapshot includes answer material only on the server; learners
            # continue to receive the established sanitized attempt projection.
            sid=str(uuid.uuid4()); stamp=now(); packed=json.dumps(chosen,ensure_ascii=False)
            conn.execute(f"INSERT INTO exam_blueprint_snapshots(id,blueprint_id,quiz_category_id,questions,created_at) VALUES({ph},{ph},{ph},{ph},{ph})",(sid,blueprint_id,bp["quiz_category_id"],packed,stamp))
        finally:conn.close()
        return jsonify({"id":sid,"blueprintId":blueprint_id,"questionCount":len(chosen),"immutable":True,"createdAt":stamp}),201
    app.extensions["teacher_question_bank_68_registered"]=True
    return app
