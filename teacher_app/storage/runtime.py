"""Runtime adapter composition for canonical storage deletion.

This module wires already-owned provider operations into provider-neutral
``StorageProviderAdapter`` objects.  It never creates credentials, clients or
sessions; callers pass the live provider callbacks owned elsewhere in
``teacher_app.storage`` or compatibility wrappers during migration.
"""

from __future__ import annotations

from typing import Callable

from teacher_app.storage.service import StorageProviderAdapter


def build_delete_adapters(
    *,
    mega_is_configured: Callable[[], bool],
    mega_delete_object: Callable[[object], None],
    gdrive_is_configured: Callable[[], bool],
    gdrive_delete_object: Callable[[object], None],
    gdrive_delete_material: Callable[[object], None] | None = None,
    oci_is_configured: Callable[[], bool],
    oci_delete_object: Callable[[object], None],
    oci_delete_prefix: Callable[[object], None] | None = None,
    r2_is_configured: Callable[[], bool],
    r2_delete_object: Callable[[object], None],
    r2_delete_prefix: Callable[[object], None] | None = None,
    local_delete_object: Callable[[object], None] | None = None,
    local_delete_prefix: Callable[[object], None] | None = None,
    local_delete_material: Callable[[object], None] | None = None,
) -> dict[str, StorageProviderAdapter]:
    """Build deletion adapters around the existing live provider callbacks."""

    return {
        "mega": StorageProviderAdapter(
            name="mega",
            is_configured=mega_is_configured,
            delete_object=mega_delete_object,
        ),
        "gdrive": StorageProviderAdapter(
            name="gdrive",
            is_configured=gdrive_is_configured,
            delete_object=gdrive_delete_object,
            delete_material=gdrive_delete_material,
        ),
        "oci": StorageProviderAdapter(
            name="oci",
            is_configured=oci_is_configured,
            delete_object=oci_delete_object,
            delete_prefix=oci_delete_prefix,
        ),
        "r2": StorageProviderAdapter(
            name="r2",
            is_configured=r2_is_configured,
            delete_object=r2_delete_object,
            delete_prefix=r2_delete_prefix,
        ),
        "local": StorageProviderAdapter(
            name="local",
            is_configured=lambda: True,
            delete_object=local_delete_object,
            delete_prefix=local_delete_prefix,
            delete_material=local_delete_material,
        ),
    }
