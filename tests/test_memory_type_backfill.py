"""memory_type 백필 추론 테스트."""

from conversation_to_memory.migration.memory_type import (
    backfill_memory_type,
    infer_memory_type,
)


def _event_memory() -> dict:
    return {
        "topic": "팀장과 회의",
        "event_summary": "오늘 팀장과 프로젝트 회의를 했다.",
        "people": ["팀장"],
        "memory_candidate": "오늘 팀장과 회의했다.",
        "conversation": [
            {"role": "user", "content": "오늘 팀장과 프로젝트 회의를 했어."},
        ],
    }


def _observation_memory() -> dict:
    return {
        "topic": "반복되는 불안",
        "event_summary": "직장 맥락에서 불안이 자주 반복된다.",
        "memory_candidate": "직장에서 불안이 자주 느껴진다.",
        "conversation": [
            {"role": "user", "content": "요즘 직장에서 불안한 게 자주 반복되는 것 같아."},
        ],
    }


def _reflection_seed_memory() -> dict:
    return {
        "topic": "관계의 의미",
        "open_questions": ["왜 관계가 이렇게 중요할까?"],
        "memory_candidate": "관계에 대한 철학적 고민",
        "conversation": [
            {"role": "user", "content": "왜 사람들은 관계를 그렇게 중요하게 여길까? 궁금해."},
        ],
    }


class TestMemoryTypeInference:
    def test_event_with_people_and_action(self):
        result = infer_memory_type(_event_memory(), memory_id="2026-06-10_120000")
        assert result["memory_type"] == "event"
        assert result["memory_type_confidence"] in ("high", "medium")

    def test_observation_with_repeated_feeling(self):
        result = infer_memory_type(_observation_memory())
        assert result["memory_type"] == "observation"

    def test_reflection_seed_with_open_question(self):
        result = infer_memory_type(_reflection_seed_memory())
        assert result["memory_type"] == "reflection_seed"
        assert result["memory_type_confidence"] in ("high", "medium")

    def test_existing_type_not_overwritten(self):
        memory = {**_event_memory(), "memory_type": "observation"}
        result = infer_memory_type(memory)
        assert result["memory_type"] == "observation"
        assert result["memory_type_confidence"] == "high"


class TestMemoryTypeBackfill:
    def test_backfill_adds_fields(self):
        memory = _observation_memory()
        migrated, result = backfill_memory_type(memory, memory_id="2026-06-13_test")
        assert migrated is True
        assert memory["memory_type"] == result["memory_type"]
        assert memory["memory_type_confidence"] == result["memory_type_confidence"]

    def test_backfill_skips_existing(self):
        memory = {**_event_memory(), "memory_type": "event", "memory_type_confidence": "high"}
        migrated, _ = backfill_memory_type(memory)
        assert migrated is False
