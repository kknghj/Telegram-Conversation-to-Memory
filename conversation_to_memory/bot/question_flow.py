"""Follow-up question routing for the conversation flow."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from app import database as db
from conversation_to_memory.bot import failure_hooks, session, states
from conversation_to_memory.debug_trace import recorder as trace_recorder
from conversation_to_memory.memory import question as question_service

logger = logging.getLogger(__name__)


@dataclass
class FollowupResult:
    messages: list[str]
    state: int


ReviewMessageBuilder = Callable[[dict[str, Any]], str]


def _review(draft: dict[str, Any], review_message: ReviewMessageBuilder) -> FollowupResult:
    return FollowupResult(messages=[review_message(draft)], state=states.REVIEW)


def _question_trace(
    *,
    need_followup: bool | None,
    reason: str | None,
    strategy: str | None,
    llm_called: bool,
    generated: bool,
    sent: bool,
    engine: str,
    error: str | None = None,
    question_result: dict[str, Any] | None = None,
    question_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qsession = question_session or {}
    result = question_result or {}
    gate = qsession.get("second_question_gate") or {}
    asked = int(qsession.get("questions_asked") or 0)
    trace: dict[str, Any] = {
        "evaluated": True,
        "need_followup": need_followup,
        "reason": reason,
        "strategy": strategy,
        "llm_called": llm_called,
        "generated": generated,
        "sent": sent,
        "engine": engine,
        "question_round": asked + (0 if sent else 1) if asked else (1 if sent or generated else 0),
        "archive_gap": result.get("archive_gap"),
        "reflective_handle_strength": result.get("reflective_handle_strength"),
        "candidate_count": result.get("candidate_count"),
        "selected_anchor": result.get("selected_anchor") or "",
        "selected_question_mode": result.get("question_mode") or strategy,
        "rejected_candidates": list(result.get("rejected_candidates") or [])[:5],
        "second_question_allowed": gate.get("second_question_allowed"),
        "second_question_gate_reason": gate.get("second_question_gate_reason") or "",
        "final_reason": reason or "",
        "question_outcome": result.get("question_outcome")
        or ("question_sent" if sent else ""),
    }
    if sent:
        trace["question_round"] = asked  # record_question 이후라면 asked가 이미 증가
        trace["question_outcome"] = "question_sent"
    if error:
        trace["error"] = error
    return trace


def _maybe_reflection_followup_or_review(
    user_id: str,
    user_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    review_message: ReviewMessageBuilder,
) -> FollowupResult:
    qsession = session.ensure_question_session(user_data)
    if qsession["questions_asked"] >= question_service.get_max_questions():
        trace_recorder.record_question_trace(
            user_data,
            _question_trace(
                need_followup=False,
                reason="max_questions_reached",
                strategy="skip",
                llm_called=False,
                generated=False,
                sent=False,
                engine="reflection",
            ),
        )
        return _review(draft, review_message)

    current = session.ensure_session(user_data)
    try:
        result = question_service.generate_question(
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            draft=draft,
            question_session=qsession,
            recent_context=session.get_recent_context(user_data),
        )
    except json.JSONDecodeError:
        logger.exception("후속 질문 JSON 파싱 실패 — 질문 없이 리뷰로 진행")
        trace_recorder.record_question_trace(
            user_data,
            _question_trace(
                need_followup=None,
                reason="generation_failed",
                strategy=None,
                llm_called=True,
                generated=False,
                sent=False,
                engine="reflection",
                error="json_parse_failed",
            ),
        )
        return _review(draft, review_message)
    except Exception:
        logger.exception("후속 질문 생성 실패 — 질문 없이 리뷰로 진행")
        trace_recorder.record_question_trace(
            user_data,
            _question_trace(
                need_followup=None,
                reason="generation_failed",
                strategy=None,
                llm_called=True,
                generated=False,
                sent=False,
                engine="reflection",
                error="llm_call_failed",
            ),
        )
        return _review(draft, review_message)

    draft = question_service.merge_question_into_draft(draft, result)
    session.set_draft(user_data, draft)

    if result.get("needs_followup") and result.get("followup_question"):
        latest_user = current["user_texts"][-1] if current.get("user_texts") else ""
        failure_hooks.record_followup_violation(
            user_data,
            user_text=latest_user,
            followup_question=result["followup_question"],
        )
        session.record_question(user_data, draft, result)
        qsession = session.ensure_question_session(user_data)
        if qsession.get("questions_asked", 0) >= 2:
            result = dict(result)
            result["question_outcome"] = "second_question_gate_passed"
        else:
            result = dict(result)
            result["question_outcome"] = "question_sent"
        trace_recorder.record_question_trace(
            user_data,
            _question_trace(
                need_followup=True,
                reason=None,
                strategy=result.get("question_mode"),
                llm_called=True,
                generated=True,
                sent=True,
                engine="reflection",
                question_result=result,
                question_session=qsession,
            ),
        )
        current["conversation"].append(
            {"role": "assistant", "content": result["followup_question"]}
        )
        db.save_active_draft(
            user_id,
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            draft=draft,
        )
        return FollowupResult(
            messages=[result["followup_question"]],
            state=states.FOLLOWUP,
        )

    skip_reason = result.get("skip_reason") or "no_reflective_handle"
    if skip_reason == "information_already_complete":
        # 레거시 라벨을 세분화된 사유로 치환.
        skip_reason = result.get("question_outcome") or "no_reflective_handle"
        if result.get("reflective_handle_strength") == "strong":
            skip_reason = "low_expected_gain"
    trace_recorder.record_question_trace(
        user_data,
        _question_trace(
            need_followup=False,
            reason=skip_reason,
            strategy="skip",
            llm_called=skip_reason != "max_questions_reached",
            generated=False,
            sent=False,
            engine="reflection",
            question_result=result,
            question_session=qsession,
        ),
    )
    return _review(draft, review_message)

def maybe_followup_or_review(
    user_id: str,
    user_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    review_message: ReviewMessageBuilder,
) -> FollowupResult:
    if question_service.is_reflection_agent_enabled():
        return _maybe_reflection_followup_or_review(
            user_id,
            user_data,
            draft,
            review_message=review_message,
        )

    followup_asked = user_data.get(session.KEY_FOLLOWUP_ASKED, False)
    needs_followup = draft.get("needs_followup") and draft.get("followup_question")

    if needs_followup and not followup_asked:
        trace_recorder.record_question_trace(
            user_data,
            _question_trace(
                need_followup=True,
                reason="summary_llm_requested_followup",
                strategy="summary_embedded",
                llm_called=True,
                generated=True,
                sent=True,
                engine="legacy",
            ),
        )
        question = draft["followup_question"]
        current = session.ensure_session(user_data)
        latest_user = current["user_texts"][-1] if current.get("user_texts") else ""
        failure_hooks.record_followup_violation(
            user_data,
            user_text=latest_user,
            followup_question=question,
        )
        current["conversation"].append({"role": "assistant", "content": question})
        user_data[session.KEY_FOLLOWUP_ASKED] = True
        return FollowupResult(messages=[question], state=states.FOLLOWUP)

    trace_recorder.record_question_trace(
        user_data,
        _question_trace(
            need_followup=False,
            reason="followup_already_asked" if followup_asked else "information_already_complete",
            strategy="skip",
            llm_called=not followup_asked,
            generated=False,
            sent=False,
            engine="legacy",
        ),
    )
    return _review(draft, review_message)
