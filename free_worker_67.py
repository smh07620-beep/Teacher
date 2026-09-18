"""Legacy import adapter for the canonical worker HTTP routes."""

from teacher_app.worker.routes import register_free_worker


__all__ = ["register_free_worker"]
