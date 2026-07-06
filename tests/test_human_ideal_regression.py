"""Regression tests for human-ideal / current-oriented memory extraction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from conversation_to_memory.memory.fidelity import (
    apply_edit_patches,
    enforce_consistency,
    infer_temporal_status,
    naturalize_event_summary,
    parse_edit_checklist,
    validate_draft,
    verify_edit_requests,
)
from conversation_to_memory.memory.service import analyze_recording

HUMAN_IDEAL_INPUT = (
    "다른 사람들에게 보여질 모습, 평가에 신경쓰지 않는 사람이 되고 싶다."
)

INITIAL_BAD_DRAFT = {
    "topic": "자기 모습에 대한 고민",
    "event_summary": (
        "사용자는 다른 사람들에게 보여질 모습이나 평가에 신경 쓰지 않는 "
        "사람이 되고 싶다고 말했다."
    ),
    "user_emotions": [],
    "emotion_evidence": [],
    "people": [],
    "projects": [],
    "tags": [],
    "value_tags": [],
    "memory_candidate": HUMAN_IDEAL_INPUT,
    "model_interpretation": "",
    "key_phrases": ["다른 사람들에게 보여질 모습", "평가에 신경쓰지 않는 사람"],
    "emerging_themes": [],
    "open_questions": [],
    "reflection_value": "low",
    "memory_type": "event",
    "reflection_seed_candidate": False,
    "temporal_status": "past",
    "interpretation_risk": "low",
    "unsupported_inferences": [],
    "needs_followup": False,
    "followup_question": "",
}

EDIT_INSTRUCTION = (
    "reflection_value를 높이고 temporal_status는 current로 바꿔줘."
)


def test_infer_temporal_status_current_for_aspiration():
    assert infer_temporal_status(HUMAN_IDEAL_INPUT) == "current"
    assert infer_temporal_status("어제 화가 났다") == "past"
    assert infer_temporal_status("회의를 했다") == "past"


def test_validate_draft_human_ideal_extraction():
    validated = validate_draft(dict(INITIAL_BAD_DRAFT), HUMAN_IDEAL_INPUT)

    assert validated["memory_type"] == "reflection_seed"
    assert validated["reflection_seed_candidate"] is True
    assert validated["reflection_value"] == "medium"
    assert validated["temporal_status"] == "current"
    assert "라고 말했다" not in validated["event_summary"]
    assert "바람을 기록했다" in validated["event_summary"]


def test_naturalize_event_summary_preserves_meaning():
    summary = (
        "사용자는 다른 사람들에게 보여질 모습이나 평가에 신경 쓰지 않는 "
        "사람이 되고 싶다고 말했다."
    )
    improved = naturalize_event_summary(HUMAN_IDEAL_INPUT, summary)
    assert "라고 말했다" not in improved
    assert "되고 싶" in improved
    assert "바람을 기록했다" in improved


def test_parse_edit_checklist_detects_dual_requests():
    checklist = parse_edit_checklist(EDIT_INSTRUCTION)
    assert checklist.get("reflection_value_increase") is True
    assert checklist.get("temporal_status") == "current"


def test_verify_edit_requests_fails_when_partially_applied():
    before = dict(INITIAL_BAD_DRAFT)
    after = {
        **INITIAL_BAD_DRAFT,
        "reflection_value": "medium",
        "memory_type": "reflection_seed",
        "reflection_seed_candidate": True,
        "temporal_status": "past",
    }
    unfulfilled = verify_edit_requests(EDIT_INSTRUCTION, before, after, HUMAN_IDEAL_INPUT)
    assert any("temporal_status" in item for item in unfulfilled)


def test_apply_edit_patches_applies_all_requested_changes():
    before = dict(INITIAL_BAD_DRAFT)
    partial = {
        **INITIAL_BAD_DRAFT,
        "reflection_value": "medium",
        "memory_type": "reflection_seed",
        "reflection_seed_candidate": True,
        "temporal_status": "past",
    }
    patched = apply_edit_patches(
        EDIT_INSTRUCTION,
        partial,
        HUMAN_IDEAL_INPUT,
        before=before,
    )
    assert patched["reflection_value"] == "medium"
    assert patched["temporal_status"] == "current"
    assert verify_edit_requests(EDIT_INSTRUCTION, before, patched, HUMAN_IDEAL_INPUT) == []


def _mock_openai_response(data: dict):
    message = MagicMock()
    message.content = json.dumps(data, ensure_ascii=False)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@patch("conversation_to_memory.memory.service._get_client")
def test_analyze_recording_edit_applies_both_fields(mock_get_client):
    """LLM이 temporal_status만 놓쳐도 코드 보정으로 두 항목 모두 반영."""
    mock_client = MagicMock()
    partial_after_edit = {
        **INITIAL_BAD_DRAFT,
        "reflection_value": "medium",
        "memory_type": "reflection_seed",
        "reflection_seed_candidate": True,
        "temporal_status": "past",
        "topic": "인간상",
    }
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        partial_after_edit
    )
    mock_get_client.return_value = mock_client

    result = analyze_recording(
        user_texts=[HUMAN_IDEAL_INPUT],
        edit_instruction=EDIT_INSTRUCTION,
        previous_draft=INITIAL_BAD_DRAFT,
    )

    assert result["reflection_value"] == "medium"
    assert result["temporal_status"] == "current"
    assert verify_edit_requests(
        EDIT_INSTRUCTION, INITIAL_BAD_DRAFT, result, HUMAN_IDEAL_INPUT
    ) == []



def test_enforce_consistency_fixes_reflection_seed_low_value():
    draft = enforce_consistency(
        {
            "memory_type": "reflection_seed",
            "reflection_value": "low",
            "reflection_seed_candidate": True,
            "temporal_status": "past",
            "event_summary": "사용자는 되고 싶다고 말했다.",
        },
        HUMAN_IDEAL_INPUT,
    )
    assert draft["reflection_value"] == "medium"
    assert draft["temporal_status"] == "current"
