"""Decision trace 저장소·파이프라인 계측 테스트."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from conversation_to_memory.bot import save_service, session, states
from conversation_to_memory.bot.question_flow import maybe_followup_or_review
from conversation_to_memory.debug_trace import recorder as trace_recorder
from conversation_to_memory.debug_trace.file_store import FileDecisionTraceStore
from conversation_to_memory.debug_trace.models import DecisionTrace
from conversation_to_memory.debug_trace.store import (
    DecisionTraceStore,
    NoopDecisionTraceStore,
    create_trace_store,
    save_trace_safely,
)
from conversation_to_memory.debug_trace.supabase_store import SupabaseDecisionTraceStore
from conversation_to_memory.memory.fidelity import build_project_trace


class CapturingTraceStore(DecisionTraceStore):
    def __init__(self):
        self.traces: list[DecisionTrace] = []

    def save(self, trace: DecisionTrace) -> None:
        self.traces.append(trace)


class FailingTraceStore(DecisionTraceStore):
    def save(self, trace: DecisionTrace) -> None:
        raise RuntimeError("supabase down")


DRAFT_WITH_PROJECT = {
    "topic": "Cursor 작업",
    "event_summary": "Cursor로 하네스 작업을 진행했다.",
    "projects": ["Cursor", "Harness"],
    "tags": ["개발"],
    "value_tags": [],
}


def _session_user_data(draft: dict) -> dict:
    return {
        session.KEY_CURRENT_DRAFT: dict(draft),
        session.KEY_CURRENT_SESSION: {
            "user_texts": ["오늘 cursor로 하네스 작업을 했다"],
            "conversation": [{"role": "user", "content": "오늘 cursor로 하네스 작업을 했다"}],
        },
    }


# ---------------------------------------------------------------------------
# store 팩토리
# ---------------------------------------------------------------------------


def test_store_factory_returns_supabase_store(monkeypatch):
    monkeypatch.setenv("DECISION_TRACE_ENABLED", "true")
    monkeypatch.setenv("DECISION_TRACE_STORE", "supabase")
    store = create_trace_store()
    assert isinstance(store, SupabaseDecisionTraceStore)


def test_store_factory_returns_file_store_by_default(monkeypatch):
    monkeypatch.delenv("DECISION_TRACE_ENABLED", raising=False)
    monkeypatch.delenv("DECISION_TRACE_STORE", raising=False)
    store = create_trace_store()
    assert isinstance(store, FileDecisionTraceStore)


def test_store_factory_returns_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("DECISION_TRACE_ENABLED", "false")
    monkeypatch.setenv("DECISION_TRACE_STORE", "supabase")
    store = create_trace_store()
    assert isinstance(store, NoopDecisionTraceStore)


def test_store_factory_unknown_backend_falls_back_to_noop(monkeypatch):
    monkeypatch.setenv("DECISION_TRACE_ENABLED", "true")
    monkeypatch.setenv("DECISION_TRACE_STORE", "elasticsearch")
    store = create_trace_store()
    assert isinstance(store, NoopDecisionTraceStore)


# ---------------------------------------------------------------------------
# Supabase / file store 동작
# ---------------------------------------------------------------------------


def test_supabase_store_inserts_row():
    mock_client = MagicMock()
    store = SupabaseDecisionTraceStore(
        url="https://example.supabase.co",
        secret_key="secret",
        client=mock_client,
    )
    trace = DecisionTrace(
        memory_id="mem-1",
        question_trace={"evaluated": True, "need_followup": False},
    )
    store.save(trace)

    mock_client.table.assert_called_once_with("decision_traces")
    inserted = mock_client.table.return_value.insert.call_args[0][0]
    assert inserted["memory_id"] == "mem-1"
    assert inserted["question_trace"] == {"evaluated": True, "need_followup": False}
    mock_client.table.return_value.insert.return_value.execute.assert_called_once()


def test_file_store_appends_jsonl(tmp_path):
    path = tmp_path / "debug" / "decision_traces.jsonl"
    store = FileDecisionTraceStore(path=path)
    store.save(DecisionTrace(memory_id="mem-1"))
    store.save(DecisionTrace(memory_id="mem-2"))

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["memory_id"] == "mem-1"
    assert json.loads(lines[1])["memory_id"] == "mem-2"


def test_save_trace_safely_swallows_store_errors():
    assert save_trace_safely(DecisionTrace(), store=FailingTraceStore()) is False


# ---------------------------------------------------------------------------
# 질문 trace
# ---------------------------------------------------------------------------


def test_question_skip_reason_recorded(monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "true")
    user_data = _session_user_data(DRAFT_WITH_PROJECT)

    skipped = {
        "needs_followup": False,
        "followup_question": "",
        "skip_reason": "information_already_complete",
        "question_mode": "association",
        "open_questions": [],
    }
    with patch(
        "conversation_to_memory.bot.question_flow.question_service.generate_question",
        return_value=skipped,
    ):
        result = maybe_followup_or_review(
            "user-1",
            user_data,
            dict(DRAFT_WITH_PROJECT),
            review_message=lambda d: "review",
        )

    assert result.state == states.REVIEW
    trace = trace_recorder.get_question_trace(user_data)
    assert trace["evaluated"] is True
    assert trace["need_followup"] is False
    assert trace["reason"] == "information_already_complete"
    assert trace["generated"] is False
    assert trace["sent"] is False


def test_question_generation_json_failure_recorded(monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "true")
    user_data = _session_user_data(DRAFT_WITH_PROJECT)

    with patch(
        "conversation_to_memory.bot.question_flow.question_service.generate_question",
        side_effect=json.JSONDecodeError("bad", "{", 0),
    ):
        result = maybe_followup_or_review(
            "user-1",
            user_data,
            dict(DRAFT_WITH_PROJECT),
            review_message=lambda d: "review",
        )

    # 질문 생성이 실패해도 리뷰 흐름은 계속된다.
    assert result.state == states.REVIEW
    trace = trace_recorder.get_question_trace(user_data)
    assert trace["error"] == "json_parse_failed"
    assert trace["reason"] == "generation_failed"
    assert trace["llm_called"] is True
    assert trace["generated"] is False


def test_question_generation_llm_failure_recorded(monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "true")
    user_data = _session_user_data(DRAFT_WITH_PROJECT)

    with patch(
        "conversation_to_memory.bot.question_flow.question_service.generate_question",
        side_effect=RuntimeError("openai unavailable"),
    ):
        result = maybe_followup_or_review(
            "user-1",
            user_data,
            dict(DRAFT_WITH_PROJECT),
            review_message=lambda d: "review",
        )

    assert result.state == states.REVIEW
    trace = trace_recorder.get_question_trace(user_data)
    assert trace["error"] == "llm_call_failed"
    assert trace["generated"] is False


def test_question_sent_recorded_when_asked(monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "true")
    user_data = _session_user_data(DRAFT_WITH_PROJECT)

    generated = {
        "needs_followup": True,
        "followup_question": "그때 어떤 생각이 먼저 들었나요?",
        "skip_reason": "",
        "question_mode": "association",
        "open_questions": [],
    }
    with patch(
        "conversation_to_memory.bot.question_flow.question_service.generate_question",
        return_value=generated,
    ), patch("conversation_to_memory.bot.question_flow.db.save_active_draft"):
        result = maybe_followup_or_review(
            "user-1",
            user_data,
            dict(DRAFT_WITH_PROJECT),
            review_message=lambda d: "review",
        )

    assert result.state == states.FOLLOWUP
    trace = trace_recorder.get_question_trace(user_data)
    assert trace["need_followup"] is True
    assert trace["generated"] is True
    assert trace["sent"] is True


# ---------------------------------------------------------------------------
# project trace
# ---------------------------------------------------------------------------


def test_project_trace_detection_failure_reason():
    trace = build_project_trace({"projects": []}, "아무 프로젝트 언급 없는 하루였다")
    assert trace["detected"] is False
    assert trace["reason"] == "no_project_signal_in_source"


def test_project_trace_rule_confirmed_confidence():
    trace = build_project_trace(
        {"projects": ["Cursor"]}, "오늘 cursor로 작업했다"
    )
    assert trace["detected"] is True
    assert trace["selected_project"] == "Cursor"
    assert trace["confidence"] == 1.0


def test_project_trace_llm_only_confidence():
    trace = build_project_trace(
        {"projects": ["Telegram Memory Bot"]}, "오늘 봇 관련 작업을 했다"
    )
    assert trace["detected"] is True
    assert trace["confidence"] == 0.6


# ---------------------------------------------------------------------------
# 저장 흐름 통합
# ---------------------------------------------------------------------------


def test_supabase_trace_failure_does_not_block_memory_save(monkeypatch):
    user_data = _session_user_data(DRAFT_WITH_PROJECT)
    memory_storage = MagicMock()
    memory_storage.save.return_value = "mem-123"

    with patch("conversation_to_memory.bot.save_service.db.mark_draft_saved"):
        result = save_service.save_current_draft(
            "user-1",
            user_data,
            storage=memory_storage,
            trace_store=FailingTraceStore(),
        )

    assert result.saved is True
    assert result.storage_ref == "mem-123"
    memory_storage.save.assert_called_once()


def test_trace_saved_with_memory_id_and_tag_written(monkeypatch):
    user_data = _session_user_data(DRAFT_WITH_PROJECT)
    memory_storage = MagicMock()
    memory_storage.save.return_value = "mem-123"
    capture = CapturingTraceStore()

    with patch("conversation_to_memory.bot.save_service.db.mark_draft_saved"):
        result = save_service.save_current_draft(
            "user-1",
            user_data,
            storage=memory_storage,
            trace_store=capture,
        )

    assert result.saved is True
    assert len(capture.traces) == 1
    trace = capture.traces[0]
    assert trace.memory_id == "mem-123"
    assert trace.project_trace["tag_written"] is True
    assert trace.project_trace["selected_project"] == "Cursor"
    assert trace.tag_trace["written"] is True


def test_tag_save_failure_reason_recorded():
    user_data = _session_user_data(DRAFT_WITH_PROJECT)
    memory_storage = MagicMock()
    memory_storage.save.side_effect = RuntimeError("memories insert failed")
    capture = CapturingTraceStore()

    result = save_service.save_current_draft(
        "user-1",
        user_data,
        storage=memory_storage,
        trace_store=capture,
    )

    assert result.saved is False
    assert len(capture.traces) == 1
    trace = capture.traces[0]
    assert trace.memory_id is None
    assert trace.project_trace["tag_written"] is False
    assert trace.project_trace["reason"] == "tag_save_failed"
    assert trace.tag_trace["written"] is False
    assert "memory_save_failed" in trace.error


def test_pending_question_trace_included_in_final_trace(monkeypatch):
    user_data = _session_user_data(DRAFT_WITH_PROJECT)
    trace_recorder.record_question_trace(
        user_data,
        {
            "evaluated": True,
            "need_followup": False,
            "reason": "information_already_complete",
            "llm_called": True,
            "generated": False,
            "sent": False,
        },
    )
    memory_storage = MagicMock()
    memory_storage.save.return_value = "mem-123"
    capture = CapturingTraceStore()

    with patch("conversation_to_memory.bot.save_service.db.mark_draft_saved"):
        save_service.save_current_draft(
            "user-1",
            user_data,
            storage=memory_storage,
            trace_store=capture,
        )

    trace = capture.traces[0]
    assert trace.question_trace["reason"] == "information_already_complete"
    # 저장 후 세션이 초기화되며 pending trace도 제거된다.
    assert trace_recorder.get_question_trace(user_data) is None


def test_disabled_trace_does_not_write_file(monkeypatch, tmp_path):
    monkeypatch.setenv("DECISION_TRACE_ENABLED", "false")
    monkeypatch.setenv("DECISION_TRACE_STORE", "file")
    path = tmp_path / "decision_traces.jsonl"
    monkeypatch.setattr(
        "conversation_to_memory.debug_trace.file_store.DEFAULT_TRACE_PATH", path
    )

    assert save_trace_safely(DecisionTrace(memory_id="mem-1")) is True
    assert not path.exists()
