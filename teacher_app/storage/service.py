"""Provider-neutral policy inside the canonical storage package.

Live credentials, SDK clients and the MEGA auth/session owner live in
``teacher_app.storage.providers``. This module remains dependency-inverted so
selection and deletion semantics can be tested without constructing provider
clients or duplicating provider protocols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


VALID_BACKENDS = frozenset({"local", "mega", "oci", "gdrive", "r2"})
AUTO_BACKEND_ORDER = ("mega", "oci", "gdrive", "r2")
DELETE_OPERATIONS = frozenset({"object", "prefix", "material"})


class StorageConfigurationError(RuntimeError):
    """Raised when a requested storage backend is unavailable or incomplete."""


class StorageDeletionUnsupportedError(RuntimeError):
    """Raised when a provider adapter cannot perform the requested delete."""


class StorageDeletionError(RuntimeError):
    """Raised when a strict provider delete was attempted and failed."""

    def __init__(self, backend: str, operation: str, cause: Exception):
        self.backend = backend
        self.operation = operation
        self.cause = cause
        # Keep provider details available through ``cause`` without copying
        # arbitrary SDK/CLI error text into a message a caller may expose.
        super().__init__(f"{backend} {operation} deletion failed")


DeleteHandler = Callable[[Any], None]
AvailabilityHandler = Callable[[], bool]


@dataclass(frozen=True)
class StorageProviderAdapter:
    """Injected adapter around the canonical provider runtime or a local target.

    ``is_configured`` and all delete callables delegate provider-specific work.
    This policy layer never constructs credentials, clients or sessions itself.

    ``has_configuration`` is optional and is useful for fail-closed providers.
    The current MEGA behavior is represented by ``block_auto_if_present=True``:
    if MEGA settings are present but the provider is not usable, ``auto`` raises
    instead of silently selecting another provider.
    """

    name: str
    is_configured: AvailabilityHandler
    has_configuration: AvailabilityHandler | None = None
    block_auto_if_present: bool = False
    unavailable_message: str = ""
    partial_configuration_message: str = ""
    delete_object: DeleteHandler | None = None
    delete_prefix: DeleteHandler | None = None
    delete_material: DeleteHandler | None = None

    def configured(self) -> bool:
        return bool(self.is_configured())

    def configuration_present(self) -> bool:
        if self.has_configuration is None:
            return False
        return bool(self.has_configuration())


@dataclass(frozen=True)
class DeleteRequest:
    """Provider-neutral deletion request.

    ``payload`` is intentionally opaque during convergence.  Each injected
    adapter translates the request into its existing provider protocol.  This
    prevents the canonical layer from duplicating MEGA paths, Google Drive
    metadata rules, or S3 client behavior before those implementations move.
    """

    backend: str
    operation: str
    payload: Any


@dataclass(frozen=True)
class DeleteOutcome:
    backend: str
    operation: str
    deleted: bool
    error: Exception | None = None


def normalize_backend(value: Any) -> str:
    """Normalize one configured backend value using the current legacy rules."""

    mode = str(value or "auto").strip().lower() or "auto"
    return mode if mode in VALID_BACKENDS or mode == "auto" else "auto"


def _adapter_for(
    adapters: Mapping[str, StorageProviderAdapter],
    backend: str,
) -> StorageProviderAdapter | None:
    adapter = adapters.get(backend)
    if adapter is None:
        return None
    if adapter.name != backend:
        raise StorageConfigurationError(
            f"storage adapter key/name mismatch: {backend!r} != {adapter.name!r}"
        )
    return adapter


def _unavailable(
    adapter: StorageProviderAdapter | None,
    backend: str,
    *,
    partial: bool = False,
) -> StorageConfigurationError:
    if adapter is not None:
        if partial and adapter.partial_configuration_message:
            return StorageConfigurationError(adapter.partial_configuration_message)
        if adapter.unavailable_message:
            return StorageConfigurationError(adapter.unavailable_message)
    return StorageConfigurationError(f"storage backend {backend!r} is not configured")


def select_backend(
    requested: Any,
    adapters: Mapping[str, StorageProviderAdapter],
    *,
    auto_order: tuple[str, ...] = AUTO_BACKEND_ORDER,
    local_fallback: bool = True,
) -> str:
    """Resolve the active storage backend without constructing provider clients.

    Explicit remote selections must be configured.  ``auto`` checks providers
    in the supplied order and may fail closed when an adapter reports partial
    configuration with ``block_auto_if_present``.
    """

    mode = normalize_backend(requested)
    if mode == "local":
        return "local"

    if mode != "auto":
        adapter = _adapter_for(adapters, mode)
        if adapter is None or not adapter.configured():
            raise _unavailable(adapter, mode)
        return mode

    for backend in auto_order:
        if backend not in VALID_BACKENDS or backend == "local":
            raise StorageConfigurationError(f"invalid auto backend {backend!r}")
        adapter = _adapter_for(adapters, backend)
        if adapter is None:
            continue
        if adapter.configured():
            return backend
        if adapter.block_auto_if_present and adapter.configuration_present():
            raise _unavailable(adapter, backend, partial=True)

    if local_fallback:
        return "local"
    raise StorageConfigurationError("no configured storage backend is available")


def _validate_delete_request(request: DeleteRequest) -> tuple[str, str]:
    backend = str(request.backend or "").strip().lower()
    operation = str(request.operation or "").strip().lower()
    if backend not in VALID_BACKENDS:
        raise StorageConfigurationError(f"unknown storage backend {backend!r}")
    if operation not in DELETE_OPERATIONS:
        raise StorageDeletionUnsupportedError(
            f"unsupported deletion operation {operation!r} for {backend!r}"
        )
    return backend, operation


def _delete_handler(adapter: StorageProviderAdapter, operation: str) -> DeleteHandler | None:
    if operation == "object":
        return adapter.delete_object
    if operation == "prefix":
        return adapter.delete_prefix
    return adapter.delete_material


def delete_strict(
    request: DeleteRequest,
    adapters: Mapping[str, StorageProviderAdapter],
) -> DeleteOutcome:
    """Perform one delete and surface any failure to the caller.

    Strict callers should remove database metadata only after this function
    succeeds.  Provider delete handlers are expected to raise on remote failure;
    swallowed provider errors cannot be recovered by orchestration above them.
    """

    backend, operation = _validate_delete_request(request)
    adapter = _adapter_for(adapters, backend)
    if adapter is None:
        raise _unavailable(None, backend)
    if backend != "local" and not adapter.configured():
        raise _unavailable(adapter, backend)
    handler = _delete_handler(adapter, operation)
    if handler is None:
        raise StorageDeletionUnsupportedError(
            f"storage backend {backend!r} has no {operation!r} deletion adapter"
        )
    try:
        handler(request.payload)
    except Exception as exc:
        raise StorageDeletionError(backend, operation, exc) from exc
    return DeleteOutcome(backend=backend, operation=operation, deleted=True)


def delete_best_effort(
    request: DeleteRequest,
    adapters: Mapping[str, StorageProviderAdapter],
) -> DeleteOutcome:
    """Attempt cleanup without making replacement/orphan cleanup fail."""

    try:
        return delete_strict(request, adapters)
    except Exception as exc:
        backend = str(request.backend or "").strip().lower()
        operation = str(request.operation or "").strip().lower()
        return DeleteOutcome(
            backend=backend,
            operation=operation,
            deleted=False,
            error=exc,
        )
