"""Canonical Teacher worker protocol domain.

The executable local worker remains ``material_worker.py``.  Modules in this
package own Web-side protocol state only; they must not start a second worker
loop or import provider credentials.
"""
