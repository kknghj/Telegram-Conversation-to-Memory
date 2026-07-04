"""open_questions 휴리스틱 추출·백필 테스트."""

from conversation_to_memory.migration.open_questions import (
    backfill_open_questions,
    extract_open_question_candidates,
    find_noise_entries,
)


def _memory(conversation: list[dict], **extra) -> dict:
    return {"conversation": conversation, **extra}


class TestExtraction:
    def test_self_inquiry_question_extracted(self):
        memory = _memory(
            [{"role": "user", "content": "신청자들은 왜 공지사항을 잘 안읽을까?"}]
        )
        assert extract_open_question_candidates(memory) == [
            "신청자들은 왜 공지사항을 잘 안읽을까?"
        ]

    def test_inquiry_without_question_mark_extracted(self):
        memory = _memory(
            [
                {
                    "role": "user",
                    "content": "이렇게 빌런들로 찬 부서 안에서도 잘 지낼 수 있을까",
                }
            ]
        )
        assert extract_open_question_candidates(memory) == [
            "이렇게 빌런들로 찬 부서 안에서도 잘 지낼 수 있을까"
        ]

    def test_retort_to_bot_question_excluded(self):
        memory = _memory(
            [
                {
                    "role": "assistant",
                    "content": "오뎅바 같은 분위기와 다른 분위기 중 어떤 것을 더 선호하나요?",
                },
                {"role": "user", "content": "다른 분위기가 뭔데??"},
            ]
        )
        assert extract_open_question_candidates(memory) == []

    def test_dont_know_answer_to_bot_question_excluded(self):
        memory = _memory(
            [
                {
                    "role": "assistant",
                    "content": "어떤 방법이 효과적일 것이라고 생각하시나요?",
                },
                {"role": "user", "content": "그건 잘 모르겠어."},
            ]
        )
        assert extract_open_question_candidates(memory) == []

    def test_strong_inquiry_kept_even_after_bot_question(self):
        memory = _memory(
            [
                {"role": "assistant", "content": "어떤 생각이 드셨나요?"},
                {
                    "role": "user",
                    "content": "언니는 뭘 생각하면서 그런 질문을 했는지 궁금하네.",
                },
            ]
        )
        assert extract_open_question_candidates(memory) == [
            "언니는 뭘 생각하면서 그런 질문을 했는지 궁금하네."
        ]

    def test_bot_directed_request_excluded(self):
        memory = _memory([{"role": "user", "content": "오늘 대화 내용 요약해줘?"}])
        assert extract_open_question_candidates(memory) == []

    def test_personality_description_not_extracted(self):
        memory = _memory(
            [
                {
                    "role": "user",
                    "content": "원래 다른 사람 일을 궁금해하는 타입이 아니야.",
                }
            ]
        )
        assert extract_open_question_candidates(memory) == []

    def test_short_fragment_excluded(self):
        memory = _memory([{"role": "user", "content": "학교 동창?"}])
        assert extract_open_question_candidates(memory) == []


class TestNoiseDetection:
    def test_retort_in_existing_field_flagged_as_noise(self):
        memory = _memory(
            [
                {"role": "assistant", "content": "어떤 것을 더 선호하나요?"},
                {"role": "user", "content": "다른 분위기가 뭔데??"},
            ],
            open_questions=["다른 분위기가 뭔데?"],
        )
        assert find_noise_entries(memory) == ["다른 분위기가 뭔데?"]

    def test_valid_entry_not_flagged(self):
        memory = _memory(
            [{"role": "user", "content": "신청자들은 왜 공지사항을 잘 안읽을까?"}],
            open_questions=["신청자들은 왜 공지사항을 잘 안읽을까?"],
        )
        assert find_noise_entries(memory) == []


class TestBackfill:
    def test_backfill_adds_questions_and_source(self):
        memory = _memory([], open_questions=[])
        changed, result = backfill_open_questions(
            memory, ["왜 그럴까?"], source="backfill_test"
        )
        assert changed is True
        assert result == ["왜 그럴까?"]
        assert memory["open_questions"] == ["왜 그럴까?"]
        assert memory["open_questions_source"] == "backfill_test"

    def test_backfill_removes_noise(self):
        memory = _memory([], open_questions=["다른 분위기가 뭔데?"])
        changed, result = backfill_open_questions(
            memory, [], source="backfill_test", remove=["다른 분위기가 뭔데?"]
        )
        assert changed is True
        assert result == []

    def test_no_change_returns_false(self):
        memory = _memory([], open_questions=["왜 그럴까?"])
        changed, _ = backfill_open_questions(
            memory, ["왜 그럴까?"], source="backfill_test"
        )
        assert changed is False
        assert "open_questions_source" not in memory
