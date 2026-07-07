"""Decision trace storage interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class TraceStore(ABC):
    """저장소 추상 인터페이스 — local file, Supabase 등 동일 시그니처 유지."""

    @abstractmethod
    def save(
        self,
        trace: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        telegram_user_id: str | None = None,
    ) -> str:
        """trace payload 저장 후 식별자(파일 경로 또는 record id) 반환."""
