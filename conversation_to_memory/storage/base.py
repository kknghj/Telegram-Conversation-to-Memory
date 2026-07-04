"""Memory storage interface for approved memories."""

from abc import ABC, abstractmethod


class MemoryStorage(ABC):
    """저장소 추상 인터페이스 — local JSON, Supabase 등 동일 시그니처 유지."""

    @abstractmethod
    def save(self, memory: dict, *, telegram_user_id: str | None = None) -> str:
        """기억 저장 후 식별자(파일 경로 또는 record id) 반환."""
