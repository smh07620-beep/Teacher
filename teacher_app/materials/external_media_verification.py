"""Bounded server-side availability verification for external teaching media."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from teacher_app.materials import external_media


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
APPROVED_VIDEO_CONTENT_TYPES = frozenset({"video/mp4", "video/webm"})
MAX_RESPONSE_BYTES = 64 * 1024
MAX_REDIRECTS = 2


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _headers_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    if isinstance(headers, Mapping):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {}


def default_http_request(
    method: str,
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
) -> dict:
    """Make one bounded request without automatically following redirects."""

    opener = build_opener(_NoRedirect())
    request = Request(
        url,
        method=str(method or "GET").upper(),
        headers={"User-Agent": "Teacher-ExternalMediaVerifier/1.0", **dict(headers or {})},
    )
    try:
        response = opener.open(request, timeout=timeout)
        try:
            body = b"" if request.method == "HEAD" else response.read(max(0, max_bytes) + 1)
            if len(body) > max_bytes:
                raise ValueError("verification response exceeds bounded size")
            return {
                "status": int(getattr(response, "status", response.getcode())),
                "headers": _headers_dict(getattr(response, "headers", {})),
                "body": body,
                "url": str(getattr(response, "url", url) or url),
            }
        finally:
            response.close()
    except HTTPError as exc:
        body = b""
        if request.method != "HEAD":
            try:
                body = exc.read(max(0, max_bytes) + 1)
            except Exception:
                body = b""
        return {
            "status": int(exc.code or 0),
            "headers": _headers_dict(exc.headers),
            "body": body[:max_bytes],
            "url": str(exc.geturl() or url),
        }
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"external media verification request failed: {exc}") from exc


def _status(response: Mapping[str, Any]) -> int:
    try:
        return int(response.get("status") or 0)
    except (TypeError, ValueError):
        return 0


def _response_headers(response: Mapping[str, Any]) -> dict[str, str]:
    return _headers_dict(response.get("headers"))


def _validate_destination(url: str, allowed_hosts: frozenset[str]) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("verification redirect must remain HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("verification redirect cannot contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("verification redirect port is invalid") from exc
    if port not in (None, 443):
        raise ValueError("verification redirect must use standard HTTPS port")
    host = parsed.hostname.lower().rstrip(".")
    if host not in allowed_hosts:
        raise ValueError("verification redirect left the allowlisted provider/host")
    return host


def _request_with_redirects(
    method: str,
    url: str,
    *,
    allowed_hosts: frozenset[str],
    http_request: Callable,
    timeout: float,
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
    redirect_validator: Callable[[str], None] | None = None,
) -> tuple[dict, str]:
    current = str(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        _validate_destination(current, allowed_hosts)
        response = http_request(
            method,
            current,
            timeout=timeout,
            max_bytes=max_bytes,
            headers=dict(headers or {}),
        )
        response = dict(response or {})
        code = _status(response)
        if code not in REDIRECT_STATUSES:
            return response, current
        if redirect_count >= MAX_REDIRECTS:
            raise ValueError("external media verification exceeded redirect limit")
        location = _response_headers(response).get("location", "").strip()
        if not location:
            raise ValueError("external media verification redirect missing Location")
        target = urljoin(current, location)
        _validate_destination(target, allowed_hosts)
        if redirect_validator is not None:
            redirect_validator(target)
        current = target
    raise ValueError("external media verification redirect limit exceeded")


def _result(status: str, *, error: str = "", metadata: Mapping[str, Any] | None = None) -> dict:
    return {
        "availabilityStatus": status,
        "lastVerifiedAt": external_media.now(),
        "lastError": str(error or "")[:1000],
        "providerMetadata": dict(metadata or {}),
    }


def _provider_oembed(
    provider: str,
    canonical_url: str,
    *,
    http_request: Callable,
    timeout: float,
) -> dict:
    registry = external_media.PROVIDER_REGISTRY[provider]
    endpoint = str(registry["oembed_endpoint"])
    query = urlencode({"url": canonical_url, "format": "json"})
    url = f"{endpoint}?{query}"
    try:
        response, final_url = _request_with_redirects(
            "GET",
            url,
            allowed_hosts=frozenset(registry["verification_hosts"]),
            http_request=http_request,
            timeout=timeout,
            max_bytes=MAX_RESPONSE_BYTES,
        )
    except Exception as exc:
        return _result("error", error=str(exc))
    code = _status(response)
    if code == 200:
        try:
            raw = response.get("body") or b"{}"
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="strict")
            payload = json.loads(str(raw))
            if not isinstance(payload, dict):
                raise ValueError("oEmbed payload is not an object")
        except Exception as exc:
            return _result("error", error=f"provider metadata invalid: {exc}")
        metadata = {
            "providerKind": provider,
            "title": str(payload.get("title") or "")[:500],
            "authorName": str(payload.get("author_name") or "")[:250],
            "verificationHost": urlparse(final_url).hostname or "",
        }
        return _result("available", metadata=metadata)
    if code in {400, 401, 403, 404, 410}:
        return _result("unavailable", error=f"provider returned HTTP {code}")
    return _result("error", error=f"provider verification returned HTTP {code or 'unknown'}")


def _verify_cdn(
    media: Mapping[str, Any],
    *,
    hospital_hosts: frozenset[str],
    http_request: Callable,
    timeout: float,
) -> dict:
    canonical = str(media.get("canonicalUrl") or "")
    try:
        validated = external_media.validate_external_url(canonical, hospital_hosts)
    except ValueError as exc:
        return _result("unavailable", error=str(exc))
    if validated.get("provider") != "direct":
        return _result("unavailable", error="direct CDN verification requires an allowlisted hospital host")

    def validate_redirect(target: str) -> None:
        redirected = external_media.validate_external_url(target, hospital_hosts)
        if redirected.get("provider") != "direct":
            raise ValueError("CDN redirect left the approved direct-video contract")

    headers: dict[str, str] = {}
    try:
        response, final_url = _request_with_redirects(
            "HEAD",
            canonical,
            allowed_hosts=hospital_hosts,
            http_request=http_request,
            timeout=timeout,
            max_bytes=0,
            redirect_validator=validate_redirect,
        )
        code = _status(response)
        content_type = _response_headers(response).get("content-type", "").split(";", 1)[0].strip().lower()
        if code in {405, 501} or (200 <= code < 300 and not content_type):
            headers = {"Range": "bytes=0-0"}
            response, final_url = _request_with_redirects(
                "GET",
                canonical,
                allowed_hosts=hospital_hosts,
                http_request=http_request,
                timeout=timeout,
                max_bytes=1024,
                headers=headers,
                redirect_validator=validate_redirect,
            )
            code = _status(response)
            content_type = _response_headers(response).get("content-type", "").split(";", 1)[0].strip().lower()
    except Exception as exc:
        return _result("error", error=str(exc))

    if code in {200, 206}:
        if content_type not in APPROVED_VIDEO_CONTENT_TYPES:
            return _result("unavailable", error=f"unapproved video content type: {content_type or 'missing'}")
        return _result(
            "available",
            metadata={
                "providerKind": "hospital_cdn",
                "cdnHost": urlparse(final_url).hostname or "",
                "contentType": content_type,
            },
        )
    if code in {400, 401, 403, 404, 410}:
        return _result("unavailable", error=f"hospital CDN returned HTTP {code}")
    return _result("error", error=f"hospital CDN verification returned HTTP {code or 'unknown'}")


def verify_media(
    media: Mapping[str, Any],
    *,
    hospital_hosts=(),
    http_request: Callable | None = None,
    timeout_seconds: float = 5.0,
) -> dict:
    """Verify one normalized external-media record without mutating storage."""

    requester = http_request or default_http_request
    timeout = max(1.0, min(15.0, float(timeout_seconds or 5.0)))
    provider = str(media.get("provider") or "").strip().lower()
    canonical = str(media.get("canonicalUrl") or "").strip()
    if provider in {"youtube", "vimeo"}:
        try:
            normalized = external_media.validate_external_url(canonical, hospital_hosts)
        except ValueError as exc:
            return _result("unavailable", error=str(exc))
        if normalized.get("provider") != provider:
            return _result("unavailable", error="stored provider does not match canonical URL")
        return _provider_oembed(provider, canonical, http_request=requester, timeout=timeout)
    if provider == "direct":
        return _verify_cdn(
            media,
            hospital_hosts=external_media.normalize_hospital_cdn_hosts(hospital_hosts),
            http_request=requester,
            timeout=timeout,
        )
    return _result("unavailable", error="unsupported external media provider")


__all__ = [
    "APPROVED_VIDEO_CONTENT_TYPES",
    "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES",
    "default_http_request",
    "verify_media",
]
