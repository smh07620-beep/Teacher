"""Defensive pagination guards for legacy S3-compatible storage adapters.

Teacher still keeps R2/OCI compatibility helpers in ``app.py``.  Their
``list_objects_v2`` loops previously trusted ``IsTruncated`` and the returned
continuation token unconditionally.  A malformed provider response could
therefore repeat the same page forever.  This module installs bounded wrappers
at the deployment entrypoint without changing storage ownership or credentials.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

MAX_STORAGE_PAGES = 10_000


class StoragePaginationError(RuntimeError):
    """Raised when an object-store pagination response cannot make progress."""


def iter_s3_pages(
    client: Any,
    bucket: str,
    *,
    prefix: str = "",
    max_pages: int = MAX_STORAGE_PAGES,
) -> Iterator[dict[str, Any]]:
    """Yield ``list_objects_v2`` pages while proving forward progress.

    The guard intentionally fails closed rather than silently returning a
    partial listing/deletion result.  A later retry is safe for both usage
    calculation and idempotent prefix deletion.
    """
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


def install_storage_pagination_hardening(base):
    """Replace only the legacy pagination loops on the imported ``app`` module."""
    if getattr(base, "_storage_pagination_hardening_installed", False):
        return base

    def safe_r2_delete_prefix(prefix: str):
        if not prefix:
            return
        client = base.r2_client()
        for response in iter_s3_pages(client, base.R2_BUCKET_NAME, prefix=prefix):
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if not objects:
                continue
            client.delete_objects(
                Bucket=base.R2_BUCKET_NAME,
                Delete={"Objects": objects, "Quiet": True},
            )
            for item in objects:
                base.r2_record_deleted(item["Key"])

    def safe_oci_bucket_usage_bytes() -> int:
        client = base.oci_client()
        total = 0
        for response in iter_s3_pages(client, base.OCI_BUCKET_NAME):
            total += sum(int(item.get("Size", 0) or 0) for item in response.get("Contents", []))
        return total

    def safe_oci_delete_prefix(prefix: str):
        if not prefix:
            return
        client = base.oci_client()
        for response in iter_s3_pages(client, base.OCI_BUCKET_NAME, prefix=prefix):
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if objects:
                client.delete_objects(
                    Bucket=base.OCI_BUCKET_NAME,
                    Delete={"Objects": objects, "Quiet": True},
                )

    base.r2_delete_prefix = safe_r2_delete_prefix
    base.oci_bucket_usage_bytes = safe_oci_bucket_usage_bytes
    base.oci_delete_prefix = safe_oci_delete_prefix
    base._storage_pagination_hardening_installed = True
    return base
