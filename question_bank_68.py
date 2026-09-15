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
def permitted(base, capability="question.manage", group=None):
    if not hasattr(base, "require_scoped_permission"):
        return base.require_admin()
    # Question rows use the existing quiz-category assignment for scope.  An
    # absent category is deliberately not widened for a teacher/group leader.
    if group is None:
        body = request.get_json(silent=True) or {}
        category = str(request.args.get("quizCategoryId") or body.get("quizCategoryId") or "").strip()
        if category:
            quiz = base.get_quiz_category(category)
            group = (quiz or {}).get("group")
    return base.require_scoped_permission(capability, group)
def metadata(data):
    aliases={"learning_objective":"learningObjective","source_material_id":"sourceMaterialId","review_source":"reviewSource","cognitive_level":"cognitiveLevel"}
    out={k:(data[aliases[k]] if aliases.get(k) in data else data.get(k,"")) for k in ("domain","topic","subtopic","learning_objective","source_material_id","review_source")}
    for k,default in (("difficulty","medium"),("cognitive_level","understand"),("status","draft"),("origin","manual")):
        out[k]=str(data[aliases[k]] if aliases.get(k) in data else data.get(k,default));
        if out[k] not in VALID[k]:raise ValueError(f"{k} 格式錯誤")
    out["tags"]=data.get("tags",[])
    if not isinstance(out["tags"],list):raise ValueError("tags 格式錯誤")
    return out
def _decode(value, fallback):
    try:return json.loads(value) if isinstance(value,str) else value
    except Exception:return fallback
def question_payload(row):
    """Serialize the extended bank fields without leaking a second schema.

    The legacy quiz reader deliberately only projects fields needed by a
    learner.  This admin-only projection is the editor contract.
    """
    item=dict(row)
    for key, fallback in (("options",[]),("tags",[]),("review_source",{})):
        item[key]=_decode(item.get(key),fallback)
    item["quizCategoryId"]=item.pop("quiz_category_id","") or ""
    item["questionType"]=item.pop("question_type","choice") or "choice"
    item["learningObjective"]=item.pop("learning_objective","") or ""
    item["cognitiveLevel"]=item.pop("cognitive_level","understand") or "understand"
    item["sourceMaterialId"]=item.pop("source_material_id","") or ""
    item["reviewSource"]=item.pop("review_source",{}) or {}
    item["updatedAt"]=item.pop("updated_at","") or ""
    item["reviewedAt"]=item.pop("reviewed_at","") or ""
    item["reviewedBy"]=item.pop("reviewed_by","") or ""
    item["active"]=bool(item.get("active",True))
    return item
def _draw(rows, count, quotas, excluded=()):
    """Find one *single* exact-sized set satisfying all quota dimensions.

    Unlike sequential draws, every selected question contributes to topic,
    difficulty and cognitive quotas simultaneously.  Exhaustive backtracking
    is bounded by the requested exam size and refuses an unsatisfiable plan.
    """
    rows=[row for row in rows if row["id"] not in set(excluded)]
    if count < 1 or len(rows) < count: raise ValueError("已審核題目不足以建立 blueprint")
    requirements=[]
    for field in ("topic","difficulty","cognitive_level"):
        requested=quotas.get(field,{})
        if not isinstance(requested,dict): raise ValueError("quota 格式錯誤")
        for value, amount in requested.items():
            amount=int(amount or 0)
            if amount<0 or amount>count: raise ValueError("quota 數量無效")
            if amount: requirements.append((field,str(value),amount))
    random.shuffle(rows)
    suffix=[[0]*len(requirements) for _ in range(len(rows)+1)]
    for i in range(len(rows)-1,-1,-1):
        suffix[i]=suffix[i+1].copy()
        for j,(field,value,_amount) in enumerate(requirements):
            suffix[i][j]+=str(rows[i].get(field) or "")==value
    def search(index, picked, counts):
        if len(picked)==count:
            return picked if all(counts[j]>=need for j,(_f,_v,need) in enumerate(requirements)) else None
        if len(rows)-index < count-len(picked): return None
        if any(counts[j]+suffix[index][j]<need for j,(_f,_v,need) in enumerate(requirements)): return None
        row=rows[index]; next_counts=counts.copy()
        for j,(field,value,_need) in enumerate(requirements): next_counts[j]+=str(row.get(field) or "")==value
        result=search(index+1,picked+[row],next_counts)
        return result if result is not None else search(index+1,picked,counts)
    result=search(0,[],[0]*len(requirements))
    if result is None: raise ValueError("無法同時滿足 topic、difficulty 與 cognitive quota")
    return result
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
    @app.get("/api/question-bank")
    def list_bank():
        denied=(base.require_any_permission("question.manage", "audit.read") if hasattr(base,"require_any_permission") else base.require_admin())
        if denied:return denied
        category=str(request.args.get("quizCategoryId") or "").strip()
        status=str(request.args.get("status") or "").strip()
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            sql="SELECT * FROM quiz_questions"; clauses=[]; args=[]
            if category: clauses.append(f"quiz_category_id={ph}");args.append(category)
            if status: clauses.append(f"status={ph}");args.append(status)
            if clauses:sql+=" WHERE "+" AND ".join(clauses)
            sql+=" ORDER BY updated_at DESC, sort_order ASC"
            rows=[question_payload(row) for row in conn.execute(sql,args).fetchall()]
        finally:conn.close()
        return jsonify({"items":rows})
    @app.patch("/api/question-bank/<question_id>")
    def update_bank_question(question_id):
        denied=permitted(base)
        if denied:return denied
        body=request.get_json(silent=True) or {}
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            existing=conn.execute(f"SELECT * FROM quiz_questions WHERE id={ph}",(question_id,)).fetchone()
            if not existing:return jsonify({"error":"找不到題目"}),404
            old=dict(existing); merged={**old,**body}
            try:m=metadata(merged)
            except ValueError as exc:return jsonify({"error":str(exc)}),400
            question=str(merged.get("question") or "").strip()
            options=merged.get("options")
            if not question or not isinstance(options,list):return jsonify({"error":"題目與選項為必填"}),400
            values=(question,json.dumps(options,ensure_ascii=False),int(merged.get("correct",0) or 0),str(merged.get("explanation") or ""),m["topic"],m["subtopic"],m["learning_objective"],m["difficulty"],m["cognitive_level"],json.dumps(m["tags"],ensure_ascii=False),m["source_material_id"],json.dumps(m["review_source"],ensure_ascii=False),m["status"],m["origin"],now(),question_id)
            conn.execute(f"UPDATE quiz_questions SET question={ph},options={ph},correct={ph},explanation={ph},topic={ph},subtopic={ph},learning_objective={ph},difficulty={ph},cognitive_level={ph},tags={ph},source_material_id={ph},review_source={ph},status={ph},origin={ph},updated_at={ph},version=version+1 WHERE id={ph}",values)
            row=conn.execute(f"SELECT * FROM quiz_questions WHERE id={ph}",(question_id,)).fetchone()
        finally:conn.close()
        return jsonify({"ok":True,"item":question_payload(row)})
    @app.delete("/api/question-bank/<question_id>")
    def delete_bank_question(question_id):
        denied=permitted(base)
        if denied:return denied
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:cur=conn.execute(f"DELETE FROM quiz_questions WHERE id={ph}",(question_id,))
        finally:conn.close()
        return jsonify({"ok":bool(getattr(cur,"rowcount",0))})
    @app.post("/api/question-bank/<question_id>/review")
    def review(question_id):
        denied=permitted(base,"question.review")
        if denied:return denied
        decision=str((request.get_json(silent=True) or {}).get("decision") or "")
        if decision not in {"accept","reject","return"}:return jsonify({"error":"decision 格式錯誤"}),400
        user=base._current_user() or {}; conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            if decision=="accept":cur=conn.execute(f"UPDATE quiz_questions SET status={ph},reviewed_by={ph},reviewed_at={ph},updated_at={ph},version=version+1 WHERE id={ph} AND status='draft'",("reviewed",user.get("username",""),now(),now(),question_id))
            elif decision=="return":cur=conn.execute(f"UPDATE quiz_questions SET status={ph},updated_at={ph},version=version+1 WHERE id={ph}",("draft",now(),question_id))
            else:cur=conn.execute(f"UPDATE quiz_questions SET status={ph},updated_at={ph},version=version+1 WHERE id={ph}",("retired",now(),question_id))
        finally:conn.close()
        return jsonify({"ok":bool(getattr(cur,"rowcount",0))})
    @app.post("/api/exam-blueprints")
    def blueprint():
        denied=permitted(base,"exam.manage")
        if denied:return denied
        b=request.get_json(silent=True) or {}; count=max(1,min(500,int(b.get("questionCount",0) or 0))); quotas=b.get("quotas") or {}
        if not isinstance(quotas,dict):return jsonify({"error":"quotas 格式錯誤"}),400
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?";qid=str(uuid.uuid4())
        try:conn.execute(f"INSERT INTO exam_blueprints(id,quiz_category_id,question_count,quotas,exclude_recent,created_by,created_at) VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph})",(qid,str(b.get("quizCategoryId") or ""),count,json.dumps(quotas),max(0,int(b.get("excludeRecent",0) or 0)),(base._current_user() or {}).get("username",""),now()))
        finally:conn.close()
        return jsonify({"id":qid,"questionCount":count,"immutableSnapshotRequired":True}),201
    @app.get("/api/questions/<question_id>/analytics")
    def analytics(question_id):
        denied=(base.require_any_permission("question.manage", "audit.read") if hasattr(base,"require_any_permission") else base.require_admin())
        if denied:return denied
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try: rows=conn.execute(f"SELECT selected_option,is_correct FROM question_attempt_analytics WHERE question_id={ph}",(question_id,)).fetchall()
        finally:conn.close()
        n=len(rows)
        if n<10:return jsonify({"attemptCount":n,"sufficientData":False,"message":"資料不足"})
        vals=[dict(r) for r in rows]; counts=dict(Counter(r["selected_option"] for r in vals))
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:question=conn.execute(f"SELECT correct FROM quiz_questions WHERE id={ph}",(question_id,)).fetchone()
        finally:conn.close()
        correct=str(dict(question).get("correct","") if question else "")
        return jsonify({"attemptCount":n,"sufficientData":True,"correctRate":round(sum(bool(r["is_correct"]) for r in vals)/n,3),"optionSelectionCounts":counts,"distractorDistribution":{key:value for key,value in counts.items() if str(key)!=correct}})
    @app.post("/api/exam-blueprints/<blueprint_id>/publish")
    def publish_blueprint(blueprint_id):
        denied=permitted(base,"exam.publish")
        if denied:return denied
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            existing=conn.execute(f"SELECT id,questions,created_at FROM exam_blueprint_snapshots WHERE blueprint_id={ph}",(blueprint_id,)).fetchone()
            if existing:
                row=dict(existing);return jsonify({"id":row["id"],"blueprintId":blueprint_id,"questions":_decode(row["questions"],[]),"createdAt":row["created_at"],"immutable":True})
            bp=conn.execute(f"SELECT * FROM exam_blueprints WHERE id={ph}",(blueprint_id,)).fetchone()
            if not bp:return jsonify({"error":"找不到 blueprint"}),404
            bp=dict(bp); rows=[dict(r) for r in conn.execute(f"SELECT * FROM quiz_questions WHERE quiz_category_id={ph} AND status IN ('reviewed','published') AND active={ 'TRUE' if kind=='postgres' else '1'}",(bp["quiz_category_id"],)).fetchall()]
            recent=set()
            if int(bp.get("exclude_recent") or 0)>0:
                history=conn.execute(f"SELECT questions FROM exam_blueprint_snapshots WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT {int(bp['exclude_recent'])}",(bp["quiz_category_id"],)).fetchall()
                recent={str(q.get("id")) for item in history for q in _decode(dict(item).get("questions"),[]) if isinstance(q,dict)}
            try:chosen=_draw(rows,int(bp["question_count"]),_decode(bp["quotas"],{}),recent)
            except ValueError as exc:return jsonify({"error":str(exc)}),409
            # Stored snapshot includes answer material only on the server; learners
            # continue to receive the established sanitized attempt projection.
            sid=str(uuid.uuid4()); stamp=now(); packed=json.dumps(chosen,ensure_ascii=False)
            conn.execute(f"INSERT INTO exam_blueprint_snapshots(id,blueprint_id,quiz_category_id,questions,created_at) VALUES({ph},{ph},{ph},{ph},{ph})",(sid,blueprint_id,bp["quiz_category_id"],packed,stamp))
        finally:conn.close()
        return jsonify({"id":sid,"blueprintId":blueprint_id,"questionCount":len(chosen),"immutable":True,"createdAt":stamp}),201
    app.extensions["teacher_question_bank_68_registered"]=True
    return app
