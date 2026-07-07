"""Trace storage backend factory."""

from __future__ import annotations

import os

from conversation_to_memory.debug.trace_store.base import TraceStore
from conversation_to_memory.debug.trace_store.file import FileTraceStore
from conversation_to_memory.debug.trace_store.supabase import SupabaseTraceStore

TRACE_STORAGE_BACKEND_FILE = "file"
TRACE_STORAGE_BACKEND_SUPABASE = "supabase"
DEFAULT_TRACE_STORAGE_BACKEND = TRACE_STORAGE_BACKEND_FILE
SUPPORTED_TRACE_STORAGE_BACKENDS = frozenset(
    {TRACE_STORAGE_BACKEND_FILE, TRACE_STORAGE_BACKEND_SUPABASE}
)


class UnknownTraceStorageBackendError(ValueError):
    """Raised when TRACE_STORAGE_BACKEND is not supported."""


def get_trace_storage_backend_name() -> str:
    """Return normalized TRACE_STORAGE_BACKEND env value (default: file)."""
    return (
        os.getenv("TRACE_STORAGE_BACKEND", DEFAULT_TRACE_STORAGE_BACKEND).strip().lower()
        or DEFAULT_TRACE_STORAGE_BACKEND
    )


def validate_trace_storage_backend() -> None:
    """Validate TRACE_STORAGE_BACKEND when decision trace mode may be used."""
    backend = get_trace_storage_backend_name()
    if backend not in SUPPORTED_TRACE_STORAGE_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_TRACE_STORAGE_BACKENDS))
        raise UnknownTraceStorageBackendError(
            f"Unknown TRACE_STORAGE_BACKEND={backend!r}. Supported values: {supported}"
        )


def create_trace_store() -> TraceStore:
    """Create a TraceStore implementation from TRACE_STORAGE_BACKEND."""
    backend = get_trace_storage_backend_name()
    if backend == TRACE_STORAGE_BACKEND_FILE:
        return FileTraceStore()
    if backend == TRACE_STORAGE_BACKEND_SUPABASE:
        return SupabaseTraceStore()
    supported = ", ".join(sorted(SUPPORTED_TRACE_STORAGE_BACKENDS))
    raise UnknownTraceStorageBackendError(
        f"Unknown TRACE_STORAGE_BACKEND={backend!r}. Supported values: {supported}"
    )
