"""Inject Phase 3 PGY workflow assets into the existing legacy system page."""


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

            # send_from_directory/send_file responses are commonly in direct
            # passthrough mode. Disable it only for this HTML page so we can
            # safely append the small Phase 3 asset tags.
            if response.direct_passthrough:
                response.direct_passthrough = False

            html = response.get_data(as_text=True)
            if "/pgy-workflow.js" in html:
                return response
            head_asset = '<link rel="stylesheet" href="/pgy-workflow.css?v=6200">'
            body_asset = '<script defer src="/pgy-workflow.js?v=6200"></script>'
            if "</head>" in html:
                html = html.replace("</head>", head_asset + "\n</head>", 1)
            if "</body>" in html:
                html = html.replace("</body>", body_asset + "\n</body>", 1)
            response.set_data(html)
            response.content_length = len(response.get_data())
        except Exception:
            # The legacy page must remain available even if asset injection fails.
            return response
        return response

    return app
