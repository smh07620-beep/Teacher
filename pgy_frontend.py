"""Inject Teacher workflow/security/maintenance/workspace assets into UI pages."""


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
            if response.direct_passthrough:
                response.direct_passthrough = False

            if path in {"/", "/internal", "/pgy"}:
                html = response.get_data(as_text=True)
                portal_assets = []
                if "/home-profile-title-71.js" not in html:
                    portal_assets.append('<script defer src="/home-profile-title-71.js?v=7203"></script>')
                if "/portal-navigation-73.js" not in html:
                    portal_assets.append('<script defer src="/portal-navigation-73.js?v=7300"></script>')
                if portal_assets and "</body>" in html:
                    html = html.replace("</body>", "\n".join(portal_assets) + "\n</body>", 1)
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                return response

            if path not in {"/system", "/system.html"}:
                return response

            html = response.get_data(as_text=True)

            stale_shared_core = '<script defer src="/shared-core.js?v=6500"></script>'
            fresh_shared_core = '<script defer src="/shared-core.js?v=7111"></script>'
            escape_guard = '<script defer src="/runtime-escape-guard-7111.js?v=7111"></script>'
            if stale_shared_core in html:
                html = html.replace(stale_shared_core, fresh_shared_core, 1)
            if "/runtime-escape-guard-7111.js" not in html and fresh_shared_core in html:
                html = html.replace(fresh_shared_core, fresh_shared_core + "\n" + escape_guard, 1)
            html = html.replace('/system-exam.js?v=6602', '/system-exam.js?v=7111')
            html = html.replace('/teaching.js?v=6603', '/teaching.js?v=7111')

            html = html.replace('onclick="adminCreateCourseBundle()"', 'onclick="courseWizard681Create()"')
            html = html.replace('onclick="resetCourseWizardForm(true)"', 'onclick="courseWizard681Reset()"')

            # Teacher 7.4 final runtime convergence: the historical
            # system-admin.js file is retired. Keep the old static HTML marker
            # as a source-compatibility seam, but rewrite it before the browser
            # sees the page so no request is ever made for the deleted bundle.
            legacy_admin_marker = '<script defer src="/system-admin.js?v=6502"></script>'
            runtime_admin_marker = '<script defer src="/admin-runtime-shared.js?v=7400"></script>'
            if legacy_admin_marker in html:
                html = html.replace(legacy_admin_marker, runtime_admin_marker, 1)

            head_assets = []
            body_assets = []

            workspace_marker = '<script defer src="/admin-workspace.js?v=7110"></script>'
            results_data_marker = '<script defer src="/admin-results-data.js?v=7117"></script>'
            results_mode_marker = '<script defer src="/admin-results-workspace.js?v=7111"></script>'
            exam_settings_marker = '<script defer src="/admin-exam-settings.js?v=7112"></script>'
            doc_templates_marker = '<script defer src="/admin-doc-templates.js?v=7113"></script>'
            pgy_assessments_marker = '<script defer src="/admin-pgy-assessments.js?v=7114"></script>'
            if "/admin-workspace.js" not in html and runtime_admin_marker in html:
                replacement = runtime_admin_marker + "\n" + workspace_marker
                if "/admin-results-data.js" not in html:
                    replacement += "\n" + results_data_marker
                if "/admin-results-workspace.js" not in html:
                    replacement += "\n" + results_mode_marker
                if "/admin-exam-settings.js" not in html:
                    replacement += "\n" + exam_settings_marker
                if "/admin-doc-templates.js" not in html:
                    replacement += "\n" + doc_templates_marker
                if "/admin-pgy-assessments.js" not in html:
                    replacement += "\n" + pgy_assessments_marker
                html = html.replace(runtime_admin_marker, replacement, 1)
            elif "/admin-results-data.js" not in html and workspace_marker in html:
                html = html.replace(workspace_marker, workspace_marker + "\n" + results_data_marker, 1)
            elif "/admin-results-workspace.js" not in html and results_data_marker in html:
                html = html.replace(results_data_marker, results_data_marker + "\n" + results_mode_marker, 1)
            elif "/admin-exam-settings.js" not in html and results_mode_marker in html:
                html = html.replace(results_mode_marker, results_mode_marker + "\n" + exam_settings_marker, 1)
            elif "/admin-doc-templates.js" not in html and exam_settings_marker in html:
                html = html.replace(exam_settings_marker, exam_settings_marker + "\n" + doc_templates_marker, 1)
            elif "/admin-pgy-assessments.js" not in html and doc_templates_marker in html:
                html = html.replace(doc_templates_marker, doc_templates_marker + "\n" + pgy_assessments_marker, 1)

            if "/pgy-workflow.css" not in html:
                head_assets.append('<link rel="stylesheet" href="/pgy-workflow.css?v=6500">')
            if "/learner-layout-stability-73.css" not in html:
                head_assets.append('<link rel="stylesheet" href="/learner-layout-stability-73.css?v=7300">')

            assets = (
                ("/pgy-workflow.js", '<script defer src="/pgy-workflow.js?v=6601"></script>'),
                ("/roles-signing-66.js", '<script defer src="/roles-signing-66.js?v=6601"></script>'),
                ("/exam-integrity.js", '<script defer src="/exam-integrity.js?v=6604"></script>'),
                ("/review-links-66.js", '<script defer src="/review-links-66.js?v=6604"></script>'),
                ("/maintenance-64.js", '<script defer src="/maintenance-64.js?v=6605"></script>'),
                ("/workspace-shell-70.js", '<script defer src="/workspace-shell-70.js?v=7114"></script>'),
                ("/training-command-center-71.js", '<script defer src="/training-command-center-71.js?v=7113"></script>'),
                ("/pgy-competency-matrix-71.js", '<script defer src="/pgy-competency-matrix-71.js?v=7113"></script>'),
                ("/learning-analytics-71.js", '<script defer src="/learning-analytics-71.js?v=7113"></script>'),
                ("/notification-center-71.js", '<script defer src="/notification-center-71.js?v=7113"></script>'),
                ("/worker-status-70.js", '<script defer src="/worker-status-70.js?v=7002"></script>'),
                ("/admin-results.js", '<script defer src="/admin-results.js?v=7100"></script>'),
                ("/admin-course-material.js", '<script defer src="/admin-course-material.js?v=7101"></script>'),
                ("/admin-course-material-hub.js", '<script defer src="/admin-course-material-hub.js?v=7400"></script>'),
                ("/admin-people.js", '<script defer src="/admin-people.js?v=7113"></script>'),
                ("/admin-people-accounts.js", '<script defer src="/admin-people-accounts.js?v=7400"></script>'),
                ("/admin-announcements.js", '<script defer src="/admin-announcements.js?v=7103"></script>'),
                ("/admin-system.js", '<script defer src="/admin-system.js?v=7104"></script>'),
                ("/admin-system-status.js", '<script defer src="/admin-system-status.js?v=7400"></script>'),
                ("/admin-materials.js", '<script defer src="/admin-materials.js?v=7105"></script>'),
                ("/admin-question-card.js", '<script defer src="/admin-question-card.js?v=7400"></script>'),
                ("/admin-question-presentation.js", '<script defer src="/admin-question-presentation.js?v=7400"></script>'),
                ("/admin-question-bank.js", '<script defer src="/admin-question-bank.js?v=7106"></script>'),
                ("/admin-quiz-materials.js", '<script defer src="/admin-quiz-materials.js?v=7118"></script>'),
                ("/admin-question-editor-ui.js", '<script defer src="/admin-question-editor-ui.js?v=7119"></script>'),
                ("/admin-question-actions.js", '<script defer src="/admin-question-actions.js?v=7120"></script>'),
                ("/admin-jobs.js", '<script defer src="/admin-jobs.js?v=7107"></script>'),
                ("/admin-material-upload.js", '<script defer src="/admin-material-upload.js?v=7108"></script>'),
                ("/material-upload-client.js", '<script defer src="/material-upload-client.js?v=7201"></script>'),
                ("/admin-ai-questions.js", '<script defer src="/admin-ai-questions.js?v=7109"></script>'),
                ("/admin-question-panel.js", '<script defer src="/admin-question-panel.js?v=7121"></script>'),
                ("/admin-external-media.js", '<script defer src="/admin-external-media.js?v=7115"></script>'),
                ("/admin-results-export.js", '<script defer src="/admin-results-export.js?v=7116"></script>'),
                ("/admin-results-docx-fallback.js", '<script defer src="/admin-results-docx-fallback.js?v=7400"></script>'),
                ("/learner-exam-controls.js", '<script defer src="/learner-exam-controls.js?v=7122"></script>'),
                ("/learner-result-chart.js", '<script defer src="/learner-result-chart.js?v=7123"></script>'),
                ("/assessment-advanced-74.js", '<script defer src="/assessment-advanced-74.js?v=7400"></script>'),
                ("/teacher-content-studio-71.js", '<script defer src="/teacher-content-studio-71.js?v=7115"></script>'),
                ("/teacher-content-composer-72.js", '<script defer src="/teacher-content-composer-72.js?v=7200"></script>'),
                ("/teacher-ux-convergence-72.js", '<script defer src="/teacher-ux-convergence-72.js?v=7205"></script>'),
                ("/learner-ui-cleanup-71.js", '<script defer src="/learner-ui-cleanup-71.js?v=7132"></script>'),
                ("/portal-navigation-73.js", '<script defer src="/portal-navigation-73.js?v=7300"></script>'),
            )
            for marker, tag in assets:
                if marker not in html:
                    body_assets.append(tag)

            if "/admin-compat-facade.js" not in html:
                body_assets.append('<script defer src="/admin-compat-facade.js?v=7300"></script>')
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