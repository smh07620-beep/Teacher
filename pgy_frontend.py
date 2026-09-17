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

            # Teacher 7.2 unified identity renderer is presentation-only and can
            # enhance signed-in headers without changing /api/auth/me.
            if path in {"/", "/internal", "/pgy"}:
                html = response.get_data(as_text=True)
                if "/home-profile-title-71.js" not in html and "</body>" in html:
                    html = html.replace(
                        "</body>",
                        '<script defer src="/home-profile-title-71.js?v=7203"></script>\n</body>',
                        1,
                    )
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                return response

            if path not in {"/system", "/system.html"}:
                return response

            html = response.get_data(as_text=True)

            # Teacher 7.1 P0 runtime recovery: production browsers can retain the
            # old shared-core URL even after a deploy. Rewrite the critical
            # runtime assets to a fresh cache key and insert an independent
            # escape guard immediately after shared-core. The guard is only a
            # compatibility bridge; AppCore.escapeHtml remains canonical.
            stale_shared_core = '<script defer src="/shared-core.js?v=6500"></script>'
            fresh_shared_core = '<script defer src="/shared-core.js?v=7111"></script>'
            escape_guard = '<script defer src="/runtime-escape-guard-7111.js?v=7111"></script>'
            if stale_shared_core in html:
                html = html.replace(stale_shared_core, fresh_shared_core, 1)
            if "/runtime-escape-guard-7111.js" not in html and fresh_shared_core in html:
                html = html.replace(fresh_shared_core, fresh_shared_core + "\n" + escape_guard, 1)
            html = html.replace('/system-exam.js?v=6602', '/system-exam.js?v=7111')
            html = html.replace('/teaching.js?v=6603', '/teaching.js?v=7111')

            # Final Convergence: current server-rendered pages call the canonical
            # Course Wizard directly. The compatibility facade remains for
            # cached/older HTML that still carries the legacy onclick names.
            html = html.replace('onclick="adminCreateCourseBundle()"', 'onclick="courseWizard681Create()"')
            html = html.replace('onclick="resetCourseWizardForm(true)"', 'onclick="courseWizard681Reset()"')
            head_assets = []
            body_assets = []

            legacy_admin_marker = '<script defer src="/system-admin.js?v=6502"></script>'
            workspace_marker = '<script defer src="/admin-workspace.js?v=7110"></script>'
            results_data_marker = '<script defer src="/admin-results-data.js?v=7117"></script>'
            results_mode_marker = '<script defer src="/admin-results-workspace.js?v=7111"></script>'
            exam_settings_marker = '<script defer src="/admin-exam-settings.js?v=7112"></script>'
            doc_templates_marker = '<script defer src="/admin-doc-templates.js?v=7113"></script>'
            pgy_assessments_marker = '<script defer src="/admin-pgy-assessments.js?v=7114"></script>'
            if "/admin-workspace.js" not in html and legacy_admin_marker in html:
                replacement = legacy_admin_marker + "\n" + workspace_marker
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
                html = html.replace(legacy_admin_marker, replacement, 1)
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
            if "/workspace-shell-70.js" not in html:
                body_assets.append('<script defer src="/workspace-shell-70.js?v=7114"></script>')
            if "/training-command-center-71.js" not in html:
                body_assets.append('<script defer src="/training-command-center-71.js?v=7113"></script>')
            if "/pgy-competency-matrix-71.js" not in html:
                body_assets.append('<script defer src="/pgy-competency-matrix-71.js?v=7113"></script>')
            if "/learning-analytics-71.js" not in html:
                body_assets.append('<script defer src="/learning-analytics-71.js?v=7113"></script>')
            if "/notification-center-71.js" not in html:
                body_assets.append('<script defer src="/notification-center-71.js?v=7113"></script>')
            if "/worker-status-70.js" not in html:
                body_assets.append('<script defer src="/worker-status-70.js?v=7002"></script>')
            if "/admin-results.js" not in html:
                body_assets.append('<script defer src="/admin-results.js?v=7100"></script>')
            if "/admin-course-material.js" not in html:
                body_assets.append('<script defer src="/admin-course-material.js?v=7101"></script>')
            if "/admin-people.js" not in html:
                body_assets.append('<script defer src="/admin-people.js?v=7113"></script>')
            if "/admin-announcements.js" not in html:
                body_assets.append('<script defer src="/admin-announcements.js?v=7103"></script>')
            if "/admin-system.js" not in html:
                body_assets.append('<script defer src="/admin-system.js?v=7104"></script>')
            if "/admin-materials.js" not in html:
                body_assets.append('<script defer src="/admin-materials.js?v=7105"></script>')
            if "/admin-question-bank.js" not in html:
                body_assets.append('<script defer src="/admin-question-bank.js?v=7106"></script>')
            if "/admin-quiz-materials.js" not in html:
                body_assets.append('<script defer src="/admin-quiz-materials.js?v=7118"></script>')
            if "/admin-question-editor-ui.js" not in html:
                body_assets.append('<script defer src="/admin-question-editor-ui.js?v=7119"></script>')
            if "/admin-question-actions.js" not in html:
                body_assets.append('<script defer src="/admin-question-actions.js?v=7120"></script>')
            if "/admin-jobs.js" not in html:
                body_assets.append('<script defer src="/admin-jobs.js?v=7107"></script>')
            if "/admin-material-upload.js" not in html:
                body_assets.append('<script defer src="/admin-material-upload.js?v=7108"></script>')
            if "/material-upload-client.js" not in html:
                body_assets.append('<script defer src="/material-upload-client.js?v=7201"></script>')
            if "/admin-ai-questions.js" not in html:
                body_assets.append('<script defer src="/admin-ai-questions.js?v=7109"></script>')
            if "/admin-question-panel.js" not in html:
                body_assets.append('<script defer src="/admin-question-panel.js?v=7121"></script>')
            if "/admin-external-media.js" not in html:
                body_assets.append('<script defer src="/admin-external-media.js?v=7115"></script>')
            if "/admin-results-export.js" not in html:
                body_assets.append('<script defer src="/admin-results-export.js?v=7116"></script>')
            if "/learner-exam-controls.js" not in html:
                body_assets.append('<script defer src="/learner-exam-controls.js?v=7122"></script>')
            if "/learner-result-chart.js" not in html:
                body_assets.append('<script defer src="/learner-result-chart.js?v=7123"></script>')
            if "/question-authoring-ux-71.js" not in html:
                body_assets.append('<script defer src="/question-authoring-ux-71.js?v=7132"></script>')
            if "/teacher-content-composer-72.js" not in html:
                body_assets.append('<script defer src="/teacher-content-composer-72.js?v=7200"></script>')
            if "/teacher-ux-convergence-72.js" not in html:
                body_assets.append('<script defer src="/teacher-ux-convergence-72.js?v=7202"></script>')
            if "/learner-ui-cleanup-71.js" not in html:
                body_assets.append('<script defer src="/learner-ui-cleanup-71.js?v=7131"></script>')
            # Final Convergence: load the compatibility facade after all
            # canonical feature owners so legacy globals resolve to them.
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