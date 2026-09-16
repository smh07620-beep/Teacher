"""Phase 2 teaching-resource search and formal Atlas API.

This adapter deliberately keeps search keyword based.  ``_normalise`` is the
single extension point for future synonym/fuzzy/semantic providers; no vector
or external search service is introduced here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
import zipfile
from pathlib import Path

from flask import jsonify, request, send_from_directory
from teacher_app.common.auth import has_permission, has_role, is_system_admin

ATLAS_CATEGORIES = {"microscope", "blood_cell", "urine_sediment", "colony"}
MAX_QUERY = 200


def _now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def _row(row): return dict(row) if row else {}
def _normalise(value): return re.sub(r"[\s_\-]+", " ", str(value or "").casefold()).strip()
def _tags(value):
    if isinstance(value, list): raw = value
    else: raw = str(value or "").split(",")
    return [str(item).strip()[:80] for item in raw if str(item).strip()][:20]


def register_atlas_70(base):
    app = base.app
    if app.extensions.get("teacher_atlas_70_registered"):
        return app

    def user_or_denied():
        user = base._current_user()
        if not user: return None, (jsonify({"error":"請先登入。", "loginRequired":True}), 401)
        return user, None

    def group_allowed(user, group):
        if is_system_admin(user) or has_role(user, "education_admin"): return True
        return str(user.get("preferredGroup") or user.get("preferred_group") or "") == str(group)

    def readable_groups(user):
        if is_system_admin(user) or has_role(user, "education_admin"): return None
        group = str(user.get("preferredGroup") or user.get("preferred_group") or "").strip()
        return {group} if group else set()

    def can_read(user):
        # Auditors are intentionally read-only, but retain their scoped audit
        # visibility for the teaching resources they are assigned to inspect.
        return has_permission(user, "material.read") or has_role(user, "auditor")

    def can_manage(user, group):
        return has_permission(user, "material.manage") and group_allowed(user, group)

    def image_dir():
        directory = Path(base.MATERIAL_STORAGE) / "atlas_images"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def material_visible(user, material):
        return bool(material and material.get("active", True) and can_read(user) and (readable_groups(user) is None or str(material.get("group") or material.get("groupKey") or "") in readable_groups(user)))

    def atlas_dict(row):
        item = _row(row)
        try: item["tags"] = json.loads(item.get("tags") or "[]")
        except Exception: item["tags"] = []
        try: item["annotationJson"] = json.loads(item.pop("annotation_json", "{}") or "{}")
        except Exception: item["annotationJson"] = {}
        item["group"] = item.pop("group_key", "")
        item["imageUrl"] = item.pop("image_url", "")
        item["thumbnailUrl"] = item["imageUrl"].replace("/api/atlas/images/", "/api/atlas/images/thumb-") if item["imageUrl"].startswith("/api/atlas/images/") else item["imageUrl"]
        item["differentialPoints"] = item.pop("differential_points", "")
        item["teachingNotes"] = item.pop("teaching_notes", "")
        item["sourceMaterialId"] = item.pop("source_material_id", "")
        item["sourceDocx"] = item.pop("source_docx", "")
        item["sortOrder"] = item.pop("sort_order", 0)
        item["createdAt"] = item.pop("created_at", "")
        item["updatedAt"] = item.pop("updated_at", "")
        item["createdBy"] = item.pop("created_by", "")
        item["updatedBy"] = item.pop("updated_by", "")
        item["published"] = bool(item.get("published"))
        return item

    @app.post("/api/atlas/images")
    def atlas_image_upload():
        user, denied=user_or_denied()
        if denied:return denied
        group=str(request.form.get("group") or "").strip()
        if not can_manage(user, group):return jsonify({"error":"無權管理此組圖譜。"}),403
        uploaded=request.files.get("file")
        if not uploaded or not uploaded.filename:return jsonify({"error":"缺少圖片檔案。"}),400
        ext=Path(uploaded.filename).suffix.lower()
        if ext not in {".jpg",".jpeg",".png",".webp"}:return jsonify({"error":"僅接受 JPG、PNG、WEBP 圖片。"}),400
        raw=uploaded.read()
        if not raw or len(raw)>15*1024*1024:return jsonify({"error":"圖片不可為空且不得超過 15 MB。"}),400
        try:
            from PIL import Image
            from io import BytesIO
            image=Image.open(BytesIO(raw)); image.verify()
            image=Image.open(BytesIO(raw)); image.load()
            if image.format not in {"JPEG","PNG","WEBP"}:raise ValueError("format")
            name=f"{uuid.uuid4().hex}{ext}"; target=image_dir()/name; target.write_bytes(raw)
            thumb=image.copy(); thumb.thumbnail((640,640)); thumb.save(image_dir()/f"thumb-{name}", format=image.format)
        except Exception:return jsonify({"error":"圖片內容或 MIME 驗證失敗。"}),400
        return jsonify({"imageUrl":f"/api/atlas/images/{name}","thumbnailUrl":f"/api/atlas/images/thumb-{name}"}),201

    @app.get("/api/atlas/images/<path:name>")
    def atlas_image_read(name):
        user, denied=user_or_denied()
        if denied:return denied
        safe=Path(name).name
        original=safe[6:] if safe.startswith("thumb-") else safe
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT group_key,published FROM atlas_items WHERE image_url={ph}",(f"/api/atlas/images/{original}",)).fetchone()
        finally:conn.close()
        item=_row(row); groups=readable_groups(user)
        if not item or not can_read(user) or (groups is not None and item.get("group_key") not in groups) or (not bool(item.get("published")) and not can_manage(user,item.get("group_key"))):return jsonify({"error":"找不到圖譜圖片。"}),404
        return send_from_directory(str(image_dir()),safe)

    def docx_source(material_id):
        material=base.get_material(material_id)
        if not material:return None,None
        path=Path(base.UPLOADED_SLIDES_DIR)/str(material.get("folder") or material_id)/str(material.get("storageFilename") or material.get("filename") or "")
        return material,path if path.suffix.lower()==".docx" and path.is_file() else None

    @app.post("/api/atlas/import-docx/<material_id>/preview")
    def atlas_docx_preview(material_id):
        user,denied=user_or_denied()
        if denied:return denied
        material,path=docx_source(material_id)
        if not material or not path:return jsonify({"error":"需要可安全存取的 DOCX 原始檔。"}),409
        if not can_manage(user,material.get("group") or material.get("groupKey")):return jsonify({"error":"無權管理此教材。"}),403
        from smart_learning_67 import preview_docx_atlas
        preview=preview_docx_atlas(path)
        preview["warnings"]=list(preview.get("warnings") or [])+["只會匯入可驗證的內嵌圖片；浮動圖、SmartArt、圖表、群組物件、OLE 與損壞 relationship 不會自動建立圖譜。"]
        return jsonify({"materialId":material_id,"preview":preview,"defaultGroup":material.get("group") or material.get("groupKey"),"initialStatus":"draft"})

    @app.post("/api/atlas/import-docx/<material_id>/confirm")
    def atlas_docx_confirm(material_id):
        user,denied=user_or_denied()
        if denied:return denied
        material,path=docx_source(material_id)
        if not material or not path:return jsonify({"error":"需要可安全存取的 DOCX 原始檔。"}),409
        source_group=str(material.get("group") or material.get("groupKey") or "")
        if not can_manage(user,source_group):return jsonify({"error":"無權管理此教材。"}),403
        body=request.get_json(silent=True) or {}; selected=body.get("items")
        if not isinstance(selected,list) or not selected:return jsonify({"error":"請至少選擇一張圖片。"}),400
        common=body.get("metadata") or body.get("commonMetadata") or {}
        if not isinstance(common,dict):return jsonify({"error":"共用 metadata 格式不正確。"}),400
        with zipfile.ZipFile(path) as archive:
            media=[name for name in archive.namelist() if name.startswith("word/media/")]
            created=[]; now=_now(); conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
            try:
                for picked in selected[:30]:
                    if not isinstance(picked,dict):continue
                    values={**common,**picked}; index=int(values.get("index",0))-1
                    if index<0 or index>=len(media):continue
                    raw=archive.read(media[index]); ext=Path(media[index]).suffix.lower()
                    if ext not in {".jpg",".jpeg",".png",".webp"}:continue
                    try:
                        from PIL import Image
                        from io import BytesIO
                        im=Image.open(BytesIO(raw));im.verify();im=Image.open(BytesIO(raw));im.load()
                        if im.format not in {"JPEG","PNG","WEBP"}:continue
                        name=f"{uuid.uuid4().hex}{ext}";image_dir().joinpath(name).write_bytes(raw);thumb=im.copy();thumb.thumbnail((640,640));thumb.save(image_dir()/f"thumb-{name}",format=im.format)
                    except Exception:continue
                    group=str(values.get("group") or source_group).strip()
                    if not group or not can_manage(user,group):continue
                    category=str(values.get("category") or "microscope")
                    if category not in ATLAS_CATEGORIES:category="microscope"
                    item_id=uuid.uuid4().hex; title=str(values.get("title") or Path(media[index]).stem)[:255]
                    conn.execute(f"INSERT INTO atlas_items(id,category,group_key,title,image_url,description,tags,differential_points,teaching_notes,difficulty,published,source,source_material_id,source_docx,sort_order,annotation_json,created_at,updated_at,created_by,updated_by) VALUES({','.join([ph]*20)})",(item_id,category,group,title,f"/api/atlas/images/{name}",str(values.get("description") or "")[:6000],json.dumps(_tags(values.get("tags")),ensure_ascii=False),str(values.get("differentialPoints") or "")[:6000],str(values.get("teachingNotes") or "")[:6000],str(values.get("difficulty") or "general")[:40],False,"docx",material_id,str(material.get("filename") or "")[:255],int(values.get("sortOrder") or 0),"{}",now,now,str(user.get("username") or ""),str(user.get("username") or "")))
                    created.append(item_id)
            finally:conn.close()
        if not created:return jsonify({"error":"沒有可安全匯入的內嵌圖片。","warnings":["請確認 DOCX 使用支援的 inline JPG/PNG/WEBP 圖片。"]}),409
        return jsonify({"ok":True,"created":created,"status":"draft"}),201

    @app.get("/api/atlas")
    def atlas_list():
        user, denied = user_or_denied()
        if denied: return denied
        if not can_read(user): return jsonify({"error":"權限不足。"}), 403
        category = str(request.args.get("category", "")).strip()
        group_filter = str(request.args.get("group", "")).strip()
        tag_filter = _normalise(request.args.get("tag", ""))[:80]
        status_filter = str(request.args.get("status", "")).strip().lower()
        if status_filter not in {"", "published", "draft"}: return jsonify({"error":"發布狀態篩選不正確。"}),400
        query = _normalise(request.args.get("q", ""))[:MAX_QUERY]
        groups = readable_groups(user)
        conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
        try:
            rows = conn.execute("SELECT * FROM atlas_items ORDER BY sort_order,title,id").fetchall()
        finally: conn.close()
        items=[]
        for row in rows:
            item=atlas_dict(row)
            if groups is not None and item["group"] not in groups: continue
            if not can_manage(user, item["group"]) and not item["published"]: continue
            if group_filter and item["group"] != group_filter: continue
            if tag_filter and tag_filter not in {_normalise(tag) for tag in item["tags"]}: continue
            if status_filter == "published" and not item["published"]: continue
            if status_filter == "draft" and (not can_manage(user,item["group"]) or item["published"]): continue
            hay=_normalise(" ".join([item["title"], item["description"], " ".join(item["tags"]), item["differentialPoints"]]))
            if category and item["category"] != category: continue
            if query and query not in hay: continue
            items.append(item)
        return jsonify({"items":items, "categories":sorted(ATLAS_CATEGORIES)})

    @app.get("/api/atlas/<item_id>")
    def atlas_get(item_id):
        user, denied=user_or_denied()
        if denied: return denied
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT * FROM atlas_items WHERE id={ph}",(item_id,)).fetchone()
        finally: conn.close()
        item=atlas_dict(row)
        if not item or not can_read(user) or (readable_groups(user) is not None and item["group"] not in readable_groups(user)) or (not item["published"] and not can_manage(user,item["group"])): return jsonify({"error":"找不到圖譜。"}),404
        return jsonify({"item":item, "questionContract":{"atlasItemId":item["id"],"status":"not_available"}})

    @app.get("/api/teaching-resource-search")
    def teaching_resource_search():
        """Search only resources the current user may already read.

        This is intentionally application-side normalization for predictable
        SQLite/Postgres behavior.  A later trigram/synonym provider can replace
        the matching branch without changing this public response contract.
        """
        user, denied=user_or_denied()
        if denied:return denied
        if not can_read(user):return jsonify({"error":"權限不足。"}),403
        query=_normalise(request.args.get("q", ""))[:MAX_QUERY]
        if not query:return jsonify({"items":[]})
        groups=readable_groups(user); items=[]
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            for material in base.list_uploaded_materials(False):
                if not material_visible(user,material):continue
                rows=conn.execute(f"SELECT page_no,title,text FROM material_text_index WHERE material_id={ph} ORDER BY page_no LIMIT 100",(str(material.get("id")),)).fetchall()
                for row in rows:
                    data=_row(row); text=str(data.get("text") or "")
                    if query not in _normalise(" ".join([str(data.get("title") or ""),text])):continue
                    start=max(0,_normalise(text).find(query)-80)
                    items.append({"type":"material","materialId":str(material.get("id")),"title":material.get("title") or material.get("filename"),"group":material.get("group") or material.get("groupKey"),"page":int(data.get("page_no") or 0),"excerpt":text[start:start+240]})
            rows=conn.execute("SELECT * FROM atlas_items ORDER BY sort_order,title LIMIT 300").fetchall()
        finally:conn.close()
        for row in rows:
            item=atlas_dict(row)
            if groups is not None and item["group"] not in groups:continue
            if not item["published"] and not can_manage(user,item["group"]):continue
            text=" ".join([item["title"],item["description"]," ".join(item["tags"]),item["differentialPoints"]])
            if query in _normalise(text):items.append({"type":"atlas","atlasItemId":item["id"],"title":item["title"],"group":item["group"],"category":item["category"],"excerpt":item["description"] or item["differentialPoints"],"imageUrl":item["imageUrl"]})
        return jsonify({"items":items[:100]})

    @app.post("/api/atlas")
    def atlas_create():
        user, denied=user_or_denied()
        if denied: return denied
        body=request.get_json(silent=True) or {}; group=str(body.get("group") or "").strip()
        if not can_manage(user, group): return jsonify({"error":"無權管理此組圖譜。"}),403
        category=str(body.get("category") or "").strip()
        if category not in ATLAS_CATEGORIES: return jsonify({"error":"圖譜類別不正確。"}),400
        title=str(body.get("title") or "").strip()[:255]
        if not title: return jsonify({"error":"請填寫圖譜名稱。"}),400
        source=str(body.get("source") or "manual").strip()
        if source not in {"manual","docx","material"}: return jsonify({"error":"匯入來源不正確。"}),400
        values={"id":uuid.uuid4().hex,"category":category,"group":group,"title":title,"image":str(body.get("imageUrl") or "").strip()[:2000],"description":str(body.get("description") or "")[:6000],"tags":json.dumps(_tags(body.get("tags")),ensure_ascii=False),"differential":str(body.get("differentialPoints") or "")[:6000],"notes":str(body.get("teachingNotes") or "")[:6000],"difficulty":str(body.get("difficulty") or "general")[:40],"published":bool(body.get("published",False)),"source":source,"material":str(body.get("sourceMaterialId") or "")[:100],"docx":str(body.get("sourceDocx") or "")[:255],"sort":int(body.get("sortOrder") or 0),"annotations":json.dumps(body.get("annotationJson") if isinstance(body.get("annotationJson"),dict) else {},ensure_ascii=False),"now":_now(),"username":str(user.get("username") or "")}
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try:
            conn.execute(f"INSERT INTO atlas_items(id,category,group_key,title,image_url,description,tags,differential_points,teaching_notes,difficulty,published,source,source_material_id,source_docx,sort_order,annotation_json,created_at,updated_at,created_by,updated_by) VALUES({','.join([ph]*20)})",tuple(values[key] for key in ("id","category","group","title","image","description","tags","differential","notes","difficulty","published","source","material","docx","sort","annotations","now","now","username","username")))
        finally: conn.close()
        return jsonify({"ok":True,"id":values["id"]}),201

    @app.patch("/api/atlas/<item_id>")
    def atlas_update(item_id):
        user,denied=user_or_denied()
        if denied:return denied
        body=request.get_json(silent=True) or {}; conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT * FROM atlas_items WHERE id={ph}",(item_id,)).fetchone()
        finally: conn.close()
        item=atlas_dict(row)
        if not item:return jsonify({"error":"找不到圖譜。"}),404
        if not can_manage(user,item["group"]):return jsonify({"error":"無權管理此圖譜。"}),403
        if "group" in body:
            next_group=str(body["group"] or "").strip()
            if not next_group or not can_manage(user,next_group):return jsonify({"error":"無權移動至此組別。"}),403
        allowed={"title":"title","imageUrl":"image_url","description":"description","differentialPoints":"differential_points","teachingNotes":"teaching_notes","difficulty":"difficulty","sourceDocx":"source_docx","sortOrder":"sort_order","published":"published","category":"category","group":"group_key"}
        changes=[]; params=[]
        for key,column in allowed.items():
            if key not in body: continue
            value=body[key]
            if key=="category" and value not in ATLAS_CATEGORIES:return jsonify({"error":"圖譜類別不正確。"}),400
            if key=="published": value=bool(value)
            changes.append(f"{column}={ph}");params.append(value)
        if "tags" in body: changes.append(f"tags={ph}");params.append(json.dumps(_tags(body["tags"]),ensure_ascii=False))
        if "annotationJson" in body: changes.append(f"annotation_json={ph}");params.append(json.dumps(body["annotationJson"] if isinstance(body["annotationJson"],dict) else {},ensure_ascii=False))
        if not changes:return jsonify({"ok":True})
        changes.extend([f"updated_at={ph}",f"updated_by={ph}"]);params.extend([_now(),str(user.get("username") or ""),item_id])
        conn,kind=base._db_conn()
        try: conn.execute(f"UPDATE atlas_items SET {','.join(changes)} WHERE id={ph}",tuple(params))
        finally: conn.close()
        return jsonify({"ok":True})

    @app.delete("/api/atlas/<item_id>")
    def atlas_delete(item_id):
        user,denied=user_or_denied()
        if denied:return denied
        if not bool((request.get_json(silent=True) or {}).get("confirmed")):return jsonify({"error":"請確認刪除圖譜。","confirmationRequired":True}),400
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            row=conn.execute(f"SELECT group_key FROM atlas_items WHERE id={ph}",(item_id,)).fetchone()
            if not row:return jsonify({"error":"找不到圖譜。"}),404
            if not can_manage(user,_row(row).get("group_key")):return jsonify({"error":"無權管理此圖譜。"}),403
            conn.execute(f"DELETE FROM atlas_items WHERE id={ph}",(item_id,))
        finally:conn.close()
        return jsonify({"ok":True})

    app.extensions["teacher_atlas_70_registered"]=True
    return app
