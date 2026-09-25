"""Canonical persistence for learner course feedback."""
from __future__ import annotations

from teacher_app.common import db as common_db


def _project(row) -> dict | None:
    if not row:
        return None
    data = dict(row)
    return {
        "courseId": str(data.get("course_id") or ""),
        "username": str(data.get("username") or ""),
        "rating": int(data.get("rating") or 0),
        "comment": str(data.get("comment") or ""),
        "createdAt": str(data.get("created_at") or ""),
        "updatedAt": str(data.get("updated_at") or ""),
    }


def get_feedback(course_id: str, username: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            f"SELECT * FROM course_feedback WHERE course_id={ph} AND username={ph}",
            (course_id, username),
        ).fetchone()
    return _project(row)


def upsert_feedback(
    course_id: str,
    username: str,
    *,
    rating: int,
    comment: str,
    now: str,
) -> dict | None:
    with common_db.transaction() as (conn, kind):
        ph = common_db.placeholder(kind)
        conn.execute(
            f"INSERT INTO course_feedback (course_id,username,rating,comment,created_at,updated_at) "
            f"VALUES ({','.join([ph] * 6)}) "
            "ON CONFLICT(course_id,username) DO UPDATE SET "
            "rating=excluded.rating,comment=excluded.comment,updated_at=excluded.updated_at",
            (course_id, username, rating, comment, now, now),
        )
    return get_feedback(course_id, username)


def feedback_summary(course_id: str) -> dict:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        row = conn.execute(
            "SELECT COUNT(*) AS response_count, AVG(rating) AS average_rating, "
            "SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS rating_1, "
            "SUM(CASE WHEN rating=2 THEN 1 ELSE 0 END) AS rating_2, "
            "SUM(CASE WHEN rating=3 THEN 1 ELSE 0 END) AS rating_3, "
            "SUM(CASE WHEN rating=4 THEN 1 ELSE 0 END) AS rating_4, "
            "SUM(CASE WHEN rating=5 THEN 1 ELSE 0 END) AS rating_5 "
            f"FROM course_feedback WHERE course_id={ph}",
            (course_id,),
        ).fetchone()
    data = dict(row or {})
    return {
        "responseCount": int(data.get("response_count") or 0),
        "averageRating": round(float(data.get("average_rating") or 0), 2),
        "ratingCounts": {
            str(value): int(data.get(f"rating_{value}") or 0)
            for value in range(1, 6)
        },
    }


__all__ = ["feedback_summary", "get_feedback", "upsert_feedback"]
