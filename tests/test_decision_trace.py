"""Regression tests for Decision Trace Mode."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from conversation_to_memory.bot import question_flow, session, states
from conversation_to_memory.debug.decision_trace import (
    DecisionTraceCollector,
    build_project_trace,
    format_trace_cli,
    is_decision_trace_enabled,
)
from conversation_to_memory.debug.trace_store import (
    FileTraceStore,
    SupabaseTraceStore,
    create_trace_store,
)
from conversation_to_memory.debug.trace_store.factory import (
    UnknownTraceStorageBackendError,
    validate_trace_storage_backend,
)
from conversation_to_memory.memory import question as question_service
from conversation_to_memory.memory.fidelity import detect_project_entities


def test_is_decision_trace_enabled(monkeypatch):
    monkeypatch.delenv("DEBUG_DECISION_TRACE", raising=False)
    assert is_decision_trace_enabled() is False

    monkeypatch.setenv("DEBUG_DECISION_TRACE", "true")
    assert is_decision_trace_enabled() is True


def test_build_project_trace_no_project_detected():
    trace = build_project_trace(llm_projects=[], keyword_projects=[], final_projects=[])
    assert trace["evaluated"] is True
    assert trace["detected"] is False
    assert trace["reason"] == "no_project_detected"
    assert trace["tag_written"] is False


def test_build_project_trace_keyword_match():
    trace = build_project_trace(
        llm_projects=[],
        keyword_projects=["Telegram Conversation to Memory"],
        final_projects=["Telegram Conversation to Memory"],
    )
    assert trace["detected"] is True
    assert trace["selected_project"] == "Telegram Conversation to Memory"
    assert trace["confidence"] == 1.0
    assert trace["tag_written"] is True


def test_build_project_trace_llm_only():
    trace = build_project_trace(
        llm_projects=["Notion Visual Automation"],
        keyword_projects=[],
        final_projects=["Notion Visual Automation"],
    )
    assert trace["detected"] is True
    assert trace["confidence"] == 0.85
    assert trace["tag_written"] is True


def test_build_project_trace_json_parse_failed():
    trace = build_project_trace(parse_error="Expecting value")
    assert trace["reason"] == "json_parse_failed"
    assert trace["detected"] is False
    assert trace["tag_written"] is False


def test_build_project_trace_merge_failed():
    trace = build_project_trace(
        llm_projects=["Telegram Memory Bot"],
        keyword_projects=[],
        final_projects=[],
    )
    assert trace["detected"] is True
    assert trace["tag_written"] is False
    assert trace["reason"] == "merge_failed_or_empty_final"


def test_collector_legacy_complete_information_skips_question():
    collector = DecisionTraceCollector()
    collector.record_legacy_summary_question(
        needs_followup=False,
        followup_question="",
        llm_called=True,
    )
    collector.record_question_routing(
        sent=False,
        reason="information_already_complete",
        strategy="legacy_summary",
    )

    assert collector.question_trace["need_followup"] is False
    assert collector.question_trace["reason"] == "information_already_complete"
    assert collector.question_trace["llm_called"] is True
    assert collector.question_trace["sent"] is False


def test_collector_legacy_clarify_question_sent():
    collector = DecisionTraceCollector()
    collector.record_legacy_summary_question(
        needs_followup=True,
        followup_question="말씀하신 프로젝트가 텔레그램 기억 봇 프로젝트인가요?",
        llm_called=True,
    )
    collector.record_question_routing(
        sent=True,
        reason="clarify",
        strategy="legacy_summary",
    )

    assert collector.question_trace["need_followup"] is True
    assert collector.question_trace["generated"] is True
    assert collector.question_trace["sent"] is True
    assert "텔레그램" in collector.question_trace["question"]


def test_validate_question_records_skip_reason_for_complete_information():
    collector = DecisionTraceCollector()
    with patch(
        "conversation_to_memory.memory.question.should_skip_followup_after_summary",
        return_value=True,
    ):
        result = question_service.validate_question(
            {
                "needs_followup": True,
                "followup_question": "추가 질문?",
                "question_mode": "association",
            },
            draft={"interpretation_risk": "low", "unsupported_inferences": []},
            question_session={"questions_asked": 0, "meaning_check_count": 0, "last_question_mode": None},
            latest_user_text="요약",
            trace_collector=collector,
        )

    assert result["needs_followup"] is False
    assert collector.question_trace["reason"] == "information_already_complete"
    assert collector.question_trace["llm_called"] is True


def test_generate_question_records_max_questions_without_llm():
    collector = DecisionTraceCollector()
    with patch("conversation_to_memory.memory.question._get_client") as mock_get_client:
        result = question_service.generate_question(
            user_texts=["테스트"],
            draft={"interpretation_risk": "low", "unsupported_inferences": []},
            question_session={
                "questions_asked": 2,
                "question_modes_used": [],
                "meaning_check_count": 0,
                "last_question_mode": None,
            },
            trace_collector=collector,
        )

    assert result["needs_followup"] is False
    assert collector.question_trace["reason"] == "max_questions_reached"
    assert collector.question_trace["llm_called"] is False
    mock_get_client.assert_not_called()


@patch("conversation_to_memory.memory.question._get_client")
def test_generate_question_records_json_parse_failure(mock_get_client):
    collector = DecisionTraceCollector()
    message = MagicMock()
    message.content = "not-json"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_get_client.return_value = mock_client

    result = question_service.generate_question(
        user_texts=["프로젝트 작업 중"],
        draft={"interpretation_risk": "low", "unsupported_inferences": []},
        question_session={
            "questions_asked": 0,
            "question_modes_used": [],
            "meaning_check_count": 0,
            "last_question_mode": None,
        },
        trace_collector=collector,
    )

    assert result["needs_followup"] is False
    assert collector.question_trace["reason"] == "json_parse_failed"
    assert collector.question_trace["llm_called"] is True


def test_question_flow_legacy_skips_when_followup_already_asked():
    user_data: dict = {}
    session.ensure_session(user_data)
    user_data[session.KEY_FOLLOWUP_ASKED] = True
    draft = {
        "needs_followup": True,
        "followup_question": "이미 물어본 질문?",
        "event_summary": "요약",
    }

    with patch.dict("os.environ", {"DEBUG_DECISION_TRACE": "true"}):
        collector = session.get_decision_trace(user_data)
        result = question_flow.maybe_followup_or_review(
            "user-1",
            user_data,
            draft,
            review_message=lambda d: "review",
        )

    assert result.state == states.REVIEW
    assert collector is not None
    assert collector.question_trace["sent"] is False
    assert collector.question_trace["reason"] == "followup_already_asked"


def test_detect_project_entities_from_source_text():
    source = "conversation to memory 텔레그램 봇 작업 중"
    projects = detect_project_entities(source)
    assert "Telegram Conversation to Memory" in projects


def test_collector_save_writes_trace_file(tmp_path):
    store = FileTraceStore(directory=tmp_path)
    collector = DecisionTraceCollector(store=store)
    collector.set_project_trace(
        build_project_trace(
            llm_projects=["Telegram Conversation to Memory"],
            keyword_projects=["Telegram Conversation to Memory"],
            final_projects=["Telegram Conversation to Memory"],
        )
    )
    path = collector.save(telegram_user_id="dev-user")
    assert path.endswith(".trace.json")

    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["project_trace"]["tag_written"] is True
    assert payload["question_trace"]["evaluated"] is False
    assert payload["telegram_user_id"] == "dev-user"


def test_file_trace_store_respects_custom_directory(tmp_path):
    store = FileTraceStore(directory=tmp_path)
    path = store.save(
        {"question_trace": {"evaluated": True}, "project_trace": {"evaluated": False}},
        telegram_user_id="user-1",
    )
    assert str(tmp_path) in path
    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["question_trace"]["evaluated"] is True


def test_create_trace_store_defaults_to_file(monkeypatch):
    monkeypatch.delenv("TRACE_STORAGE_BACKEND", raising=False)
    store = create_trace_store()
    assert isinstance(store, FileTraceStore)


def test_create_trace_store_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("TRACE_STORAGE_BACKEND", "unknown")
    with pytest.raises(UnknownTraceStorageBackendError):
        create_trace_store()


def test_validate_trace_storage_backend_accepts_file(monkeypatch):
    monkeypatch.setenv("TRACE_STORAGE_BACKEND", "file")
    validate_trace_storage_backend()


def test_supabase_trace_store_not_implemented_yet():
    store = SupabaseTraceStore()
    with pytest.raises(NotImplementedError):
        store.save({"question_trace": {}, "project_trace": {}})


def test_format_trace_cli_contains_sections():
    collector = DecisionTraceCollector()
    collector.record_legacy_summary_question(
        needs_followup=True,
        followup_question="프로젝트가 무엇인가요?",
        llm_called=True,
    )
    collector.record_question_routing(sent=True, strategy="legacy_summary")
    collector.set_project_trace(
        build_project_trace(
            llm_projects=["Telegram Conversation to Memory"],
            keyword_projects=[],
            final_projects=["Telegram Conversation to Memory"],
        )
    )

    output = format_trace_cli(collector.as_dict())
    assert "Question Decision" in output
    assert "Project Detection" in output
    assert "Need Follow-up : YES" in output
    assert "Tag Saved      : YES" in output


@patch("conversation_to_memory.memory.service._get_client")
def test_analyze_recording_records_project_trace(mock_get_client, monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "false")
    payload = {
        "topic": "작업",
        "event_summary": "conversation to memory 작업을 진행했다.",
        "projects": [],
        "needs_followup": False,
        "followup_question": "",
    }
    message = MagicMock()
    message.content = json.dumps(payload, ensure_ascii=False)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_get_client.return_value = mock_client

    collector = DecisionTraceCollector()
    draft = __import__(
        "conversation_to_memory.memory.service",
        fromlist=["analyze_recording"],
    ).analyze_recording(
        user_texts=["conversation to memory 작업을 진행했다."],
        trace_collector=collector,
    )

    assert "Telegram Conversation to Memory" in draft["projects"]
    assert collector.project_trace["tag_written"] is True
    assert collector.project_trace["keyword_projects"] == ["Telegram Conversation to Memory"]
    assert collector.question_trace["reason"] == "information_already_complete"


@patch("conversation_to_memory.memory.service._get_client")
def test_analyze_recording_keeps_project_trace_on_json_parse_failure(mock_get_client):
    message = MagicMock()
    message.content = "{invalid json"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_get_client.return_value = mock_client

    collector = DecisionTraceCollector()
    service = __import__(
        "conversation_to_memory.memory.service",
        fromlist=["analyze_recording"],
    )
    with pytest.raises(json.JSONDecodeError):
        service.analyze_recording(
            user_texts=["conversation to memory"],
            trace_collector=collector,
        )

    assert collector.project_trace["reason"] == "json_parse_failed"
