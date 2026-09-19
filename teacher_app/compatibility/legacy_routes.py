"""Legacy route compatibility helpers.

Canonical production composition lives in ``teacher_app.factory``. Historical
Flask/root-module contracts may still import compatibility surfaces such as
``app.py``, ``pgy_workflow.py`` and ``exam_integrity.py``; the redundant
``pgy_atomic.py`` replacement layer has been retired.
"""
