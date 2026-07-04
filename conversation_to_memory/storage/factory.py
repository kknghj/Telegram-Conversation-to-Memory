"""Storage backend factory."""

from __future__ import annotations

import os

from conversation_to_memory.storage.base import MemoryStorage
from conversation_to_memory.storage.local_json import LocalJsonStorage
from conversation_to_memory.storage.supabase import SupabaseStorage

STORAGE_BACKEND_LOCAL_JSON = "local_json"
STORAGE_BACKEND_SUPABASE = "supabase"
DEFAULT_STORAGE_BACKEND = STORAGE_BACKEND_LOCAL_JSON
SUPPORTED_STORAGE_BACKENDS = frozenset({STORAGE_BACKEND_LOCAL_JSON, STORAGE_BACKEND_SUPABASE})


class UnknownStorageBackendError(ValueError):
    """Raised when STORAGE_BACKEND is not supported."""


def get_storage_backend_name() -> str:
    """Return normalized STORAGE_BACKEND env value (default: local_json)."""
    return (
        os.getenv("STORAGE_BACKEND", DEFAULT_STORAGE_BACKEND).strip().lower()
        or DEFAULT_STORAGE_BACKEND
    )


def validate_storage_backend() -> None:
    """Validate STORAGE_BACKEND at app startup."""
    backend = get_storage_backend_name()
    if backend not in SUPPORTED_STORAGE_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_STORAGE_BACKENDS))
        raise UnknownStorageBackendError(
            f"Unknown STORAGE_BACKEND={backend!r}. Supported values: {supported}"
        )


def create_storage() -> MemoryStorage:
    """Create a MemoryStorage implementation from STORAGE_BACKEND."""
    backend = get_storage_backend_name()
    if backend == STORAGE_BACKEND_LOCAL_JSON:
        return LocalJsonStorage()
    if backend == STORAGE_BACKEND_SUPABASE:
        return SupabaseStorage()
    supported = ", ".join(sorted(SUPPORTED_STORAGE_BACKENDS))
    raise UnknownStorageBackendError(
        f"Unknown STORAGE_BACKEND={backend!r}. Supported values: {supported}"
    )
