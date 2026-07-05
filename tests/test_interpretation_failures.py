"""Regression tests for interpretation failure snapshot recording."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation_to_memory import failure_recorder


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "interpretation_failures.jsonl"


def test_repeated_question_recorded_when_memory_unavailable(log_path: Path):
    conversation = [
        {"role": "user", "content": "신규 때 조직이 바뀐 적은 있는데 기억이 안 난다."},
    ]
    followup = "그때 어떤 감정이 기억나나요?"

    record = failure_recorder.record_repeated_question_failure(
        user_text=conversation[-1]["content"],
        followup_question=followup,
        conversation=conversation,
        conversation_id="conv-repeated-001",
        log_path=log_path,
    )

    assert record is not None
    assert record["failure_type"] == "repeated_question"
    assert record["fixed_rule"] == "Rule 4"
    assert followup in record["assistant_after_correction"]
    assert record["user_correction"] == ""

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["failure_type"] == "repeated_question"


def test_korean_misparse_recorded_for_conditional_phrase(log_path: Path):
    user_text = "연이 왕주임이 되면 지금 팀에 계속 있는 건 너무 고역일 것 같다."
    conversation = [{"role": "user", "content": user_text}]
    assistant_output = "연이 왕주임과 함께 일하는 것이 고역일 것 같다고 했다."

    record = failure_recorder.record_korean_misparse_failure(
        user_text=user_text,
        assistant_output=assistant_output,
        conversation=conversation,
        draft={"people": ["연이 왕주임"], "event_summary": assistant_output},
        conversation_id="conv-misparse-001",
        log_path=log_path,
    )

    assert record is not None
    assert record["failure_type"] == "korean_misparse"
    assert record["fixed_rule"] == "Rule 2"
    assert "조건문" in record["expected_behavior"]


def test_correction_ignored_recorded_on_user_correction(log_path: Path):
    context = [
        {
            "role": "user",
            "content": "연이 왕주임이 되면 지금 팀에 계속 있는 건 너무 고역일 것 같다.",
        },
        {
            "role": "assistant",
            "content": "연이 왕주임과 함께 일하는 것과 다른 팀에서 일하는 것의 차이점은 무엇이라고 생각해?",
        },
    ]
    user_correction = "그 뜻이 아니다. 연이가 왕주임이 되는 상황을 말한 거야."

    pending = failure_recorder.try_prepare_correction_failure(
        user_correction=user_correction,
        conversation=context,
        draft={"event_summary": context[-1]["content"]},
        conversation_id="conv-correction-001",
    )
    assert pending is not None
    assert pending["failure_type"] == "correction_ignored"

    after = "연이가 왕주임이 되는 상황을 가정하며, 그때 현재 팀에 남는 것이 고역일 것 같다고 말했다."
    record = failure_recorder.finalize_pending_failure(pending, after, log_path=log_path)

    assert record["failure_type"] == "correction_ignored"
    assert record["user_correction"] == user_correction
    assert record["assistant_after_correction"] == after
    assert record["fixed_rule"] == "Rule 3"


def test_value_hidden_by_event_recorded(log_path: Path):
    user_text = (
        "난 사람들의 일을 줄이고 편의성을 주는 것을 만들고 싶은데 "
        "게임앱이나 인스타언팔앱은 결국 사용자의 시간과 마음을 낭비한다는 생각이 들었어."
    )
    conversation = [{"role": "user", "content": user_text}]
    draft = {
        "event_summary": "토스 미니앱을 확인하고 다른 강의로 수강 변경했다.",
        "memory_type": "event",
        "value_tags": [],
    }

    record = failure_recorder.record_value_hidden_by_event_failure(
        user_text=user_text,
        draft=draft,
        conversation=conversation,
        conversation_id="conv-value-hidden-001",
        log_path=log_path,
    )

    assert record is not None
    assert record["failure_type"] == "value_hidden_by_event"
    assert record["fixed_rule"] == "Rule 6"
    assert record["root_cause"] == "가치관이 핵심이었는데 사건 요약 위주로 저장됨"

    parsed = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert parsed["failure_type"] == "value_hidden_by_event"


def test_value_hidden_not_recorded_when_value_reflected(log_path: Path):
    user_text = (
        "난 사람들의 일을 줄이고 편의성을 주는 것을 만들고 싶은데 "
        "게임앱은 결국 사용자의 시간과 마음을 낭비한다는 생각이 들었어."
    )
    draft = {
        "event_summary": "사람들의 일을 줄이고 편의성을 주는 것을 만들고 싶다는 가치관을 확인했다.",
        "memory_type": "reflection_seed",
        "value_tags": ["사용자 시간 절약"],
    }

    record = failure_recorder.record_value_hidden_by_event_failure(
        user_text=user_text,
        draft=draft,
        conversation=[{"role": "user", "content": user_text}],
        log_path=log_path,
    )
    assert record is None
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_jsonl_append_appends_multiple_records(log_path: Path):
    recorder = failure_recorder.FailureRecorder(log_path)

    first = failure_recorder.record_interpretation_failure(
        failure_type="repeated_question",
        context=[{"role": "user", "content": "기억이 안 난다."}],
        user_correction="",
        assistant_output="어떤 장면이 떠오르나요?",
        expected_behavior=failure_recorder.DEFAULT_EXPECTED_BEHAVIOR["repeated_question"],
        root_cause=failure_recorder.DEFAULT_ROOT_CAUSE["repeated_question"],
        fixed_rule="Rule 4",
        conversation_id="conv-append-001",
        log_path=log_path,
    )
    second = failure_recorder.record_interpretation_failure(
        failure_type="korean_misparse",
        context=[{"role": "user", "content": "연이 팀장이 되면 힘들 것 같다."}],
        user_correction="조건문이야",
        assistant_output="팀장인 연이와의 관계가 힘들다.",
        expected_behavior=failure_recorder.DEFAULT_EXPECTED_BEHAVIOR["korean_misparse"],
        root_cause=failure_recorder.DEFAULT_ROOT_CAUSE["korean_misparse"],
        fixed_rule="Rule 2",
        conversation_id="conv-append-002",
        log_path=log_path,
    )

    entries = recorder.load_all()
    assert len(entries) == 2
    assert entries[0]["conversation_id"] == first["conversation_id"]
    assert entries[1]["conversation_id"] == second["conversation_id"]


def test_detect_correction_trigger_substring():
    assert failure_recorder.detect_correction_trigger("아, 그 뜻이 아니다.") == "그 뜻이 아니다"
    assert failure_recorder.detect_correction_trigger("왜 그렇게 해석했어?") == "왜 그렇게 해석했어"
    assert failure_recorder.detect_correction_trigger("그냥 기록해줘") is None


def test_user_said_memory_unavailable():
    assert failure_recorder.user_said_memory_unavailable("신규 때 기억이 안 난다.") is True
    assert failure_recorder.user_said_memory_unavailable("그때 회의가 있었다.") is False
