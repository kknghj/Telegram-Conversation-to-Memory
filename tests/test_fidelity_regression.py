"""Regression tests for known fidelity failure cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation_to_memory.memory.fidelity import validate_draft

FIXTURES_PATH = Path(__file__).resolve().parent / "fidelity_failure_examples.json"


def _load_examples() -> list[dict]:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _base_draft(**overrides) -> dict:
    draft = {
        "topic": "",
        "event_summary": "",
        "user_emotions": [],
        "emotion_evidence": [],
        "people": [],
        "projects": [],
        "tags": [],
        "memory_candidate": "",
        "model_interpretation": "",
        "key_phrases": [],
        "emerging_themes": [],
        "open_questions": [],
        "reflection_value": "medium",
        "memory_type": "observation",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "needs_followup": False,
        "followup_question": "",
    }
    draft.update(overrides)
    return draft


EXAMPLES = _load_examples()

VIBECODING = next(e for e in EXAMPLES if e["id"] == "vibecoding_manager_role_shift")
TEAM_LEAD = next(e for e in EXAMPLES if e["id"] == "team_lead_non_interference")

VIBECODING_BAD = _base_draft(
    topic="바이브코딩과 관리자",
    event_summary="바이브코딩의 재미와 관리자의 역할에 대한 복잡한 감정을 느꼈다.",
    memory_candidate="AI와 함께하는 바이브코딩의 즐거움과 관리자의 역할에 대한 복잡한 감정.",
    model_interpretation=VIBECODING["incorrect_interpretation"],
    emerging_themes=["관리자의 역할"],
)

VIBECODING_GOOD = _base_draft(
    topic="바이브코딩의 재미",
    event_summary=(
        "바이브코딩은 AI에게 사람 눈치 보지 않고 마음께 시킬 수 있어서 재미있다. "
        "실제 관리자가 되어도 이런 경험은 누릴 수 없다."
    ),
    memory_candidate=(
        "AI에게 눈치 보지 않고 마음께 시킬 수 있어 바이브코딩이 재미있다. "
        "관리자가 되어도 같은 경험은 어렵다."
    ),
)

TEAM_LEAD_BAD = _base_draft(
    topic="업무 진행",
    event_summary="팀장의 지원 덕분에 일이 잘 풀렸다.",
    memory_candidate="팀장의 지원 덕분에 생각외로 일이 잘 풀렸다.",
    model_interpretation=TEAM_LEAD["incorrect_interpretation"],
    people=["팀장"],
)

TEAM_LEAD_GOOD = _base_draft(
    topic="업무 진행",
    event_summary="팀장이 딴지를 걸지 않아서 생각외로 일이 잘 풀렸다.",
    memory_candidate="팀장이 딴지를 안 걸어서 일이 생각보다 잘 풀렸다.",
    people=["팀장"],
)


@pytest.mark.parametrize(
    "example,bad_draft,forbidden_terms",
    [
        (
            VIBECODING,
            VIBECODING_BAD,
            ["관리자의 역할"],
        ),
        (
            TEAM_LEAD,
            TEAM_LEAD_BAD,
            ["지원"],
        ),
    ],
    ids=[VIBECODING["id"], TEAM_LEAD["id"]],
)
def test_bad_draft_detects_fidelity_failure(example, bad_draft, forbidden_terms):
    validated = validate_draft(bad_draft, example["user_text"])
    combined = " ".join(
        [
            validated.get("event_summary", ""),
            validated.get("memory_candidate", ""),
            validated.get("model_interpretation", ""),
            " ".join(validated.get("emerging_themes", [])),
        ]
    )

    assert validated["unsupported_inferences"]
    assert validated["interpretation_risk"] in ("medium", "high")

    for term in forbidden_terms:
        assert term in combined


@pytest.mark.parametrize(
    "example,good_draft,forbidden_terms",
    [
        (VIBECODING, VIBECODING_GOOD, ["관리자의 역할", "복잡한 감정"]),
        (TEAM_LEAD, TEAM_LEAD_GOOD, ["지원", "배려", "도움"]),
    ],
    ids=[f"{VIBECODING['id']}_good", f"{TEAM_LEAD['id']}_good"],
)
def test_good_draft_passes_fidelity(example, good_draft, forbidden_terms):
    validated = validate_draft(good_draft, example["user_text"])
    combined = " ".join(
        [
            validated.get("event_summary", ""),
            validated.get("memory_candidate", ""),
            validated.get("model_interpretation", ""),
        ]
    )

    assert validated["interpretation_risk"] == "low"
    assert not validated["unsupported_inferences"]

    for term in forbidden_terms:
        assert term not in combined


def test_fixtures_file_has_required_fields():
    for example in EXAMPLES:
        for key in (
            "id",
            "user_text",
            "incorrect_interpretation",
            "failure_type",
            "correct_interpretation",
            "principle",
        ):
            assert key in example
