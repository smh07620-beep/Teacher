"""Inject Teacher 6.5 workflow/security/maintenance assets into the system page."""


def register_pgy_frontend(app):
    if app.extensions.get("pgy_frontend_registered"):
        return app
    app.extensions["pgy_frontend_registered"] = True

    @app.after_request
    def inject_pgy_workflow_assets(response):
        try:
            if response.status_code != 200:
                return response
            if not str(response.content_type or "").startswith("text/html"):
                return response
            try:
                from flask import request
                path = request.path
            except Exception:
                return response
            if path not in {"/system", "/system.html"}:
                return response
            if response.direct_passthrough:
                response.direct_passthrough = False
            html = response.get_data(as_text=True)
            head_assets = []
            body_assets = []
            if "/pgy-workflow.css" not in html:
                head_assets.append('<link rel="stylesheet" href="/pgy-workflow.css?v=6500">')
            if "/pgy-workflow.js" not in html:
                body_assets.append('<script defer src="/pgy-workflow.js?v=6601"></script>')
            if "/roles-signing-66.js" not in html:
                body_assets.append('<script defer src="/roles-signing-66.js?v=6601"></script>')
            if "/exam-integrity.js" not in html:
                body_assets.append('<script defer src="/exam-integrity.js?v=6604"></script>')
            if "/review-links-66.js" not in html:
                body_assets.append('<script defer src="/review-links-66.js?v=6604"></script>')
            if "/maintenance-64.js" not in html:
                body_assets.append('<script defer src="/maintenance-64.js?v=6605"></script>')
            if head_assets and "</head>" in html:
                html = html.replace("</head>", "\n".join(head_assets) + "\n</head>", 1)
            if body_assets and "</body>" in html:
                html = html.replace("</body>", "\n".join(body_assets) + "\n</body>", 1)
            response.set_data(html)
            response.content_length = len(response.get_data())
        except Exception:
            return response
        return response

    return app
