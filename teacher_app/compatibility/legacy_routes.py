"""Legacy route compatibility helpers.

The production compatibility host still mounts selected root adapters while
canonical domains are converged incrementally. Existing Flask views in
``app.py``, ``pgy_workflow.py`` and ``exam_integrity.py`` remain compatibility
surfaces; the redundant ``pgy_atomic.py`` replacement layer has been retired.
"""
