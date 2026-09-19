"""Canonical storage primitives for material provider compatibility.

This module owns provider-agnostic object-store mechanics used by the legacy
compatibility host. Provider credentials and SDK client construction remain in
app.py for now; bounded pagination and batch deletion live here so production
does not rely on an entrypoint monkey patch.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

MAX_STORAGE_PAGES = 10_000


class StoragePaginationError(RuntimeError):
    """Raised when object-store pagination cannot prove forward progress."""


def iter_s3_pages(
    client: Any,
    bucket: str,
    *,
    prefix: str = "",
    max_pages: int = MAX_STORAGE_PAGES,
) -> Iterator[dict[str, Any]]:
    """Yield list_objects_v2 pages while requiring forward progress."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    token = None
    seen_tokens: set[str] = set()

    for _page_number in range(1, max_pages + 1):
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix
        if token:
            kwargs["ContinuationToken"] = token

        response = client.list_objects_v2(**kwargs)
        if not isinstance(response, dict):
            raise StoragePaginationError("物件儲存分頁回應格式不正確。")

        yield response

        if not response.get("IsTruncated"):
            return

        next_token = str(response.get("NextContinuationToken") or "").strip()
        if not next_token:
            raise StoragePaginationError("物件儲存回報尚有下一頁，但未提供 continuation token。")
        if next_token == token or next_token in seen_tokens:
            raise StoragePaginationError("物件儲存 continuation token 重複，已停止以避免無限迴圈。")

        seen_tokens.add(next_token)
        token = next_token

    raise StoragePaginationError(
        f"物件儲存分頁超過安全上限 {max_pages} 頁，已停止以避免無限迴圈。"
    )


def bucket_usage_bytes(client: Any, bucket: str) -> int:
    """Return total object bytes using bounded pagination."""
    total = 0
    for response in iter_s3_pages(client, bucket):
        total += sum(int(item.get("Size", 0) or 0) for item in response.get("Contents", []))
    return total


def delete_prefix(
    client: Any,
    bucket: str,
    prefix: str,
    *,
    on_deleted: Callable[[str], None] | None = None,
) -> None:
    """Delete one prefix in bounded batches; empty prefixes are ignored."""
    if not prefix:
        return
    for response in iter_s3_pages(client, bucket, prefix=prefix):
        objects = [{"Key": item["Key"]} for item in response.get("Contents", []) if item.get("Key")]
        if not objects:
            continue
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        if on_deleted:
            for item in objects:
                on_deleted(item["Key"])
