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
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "evaluated": True,
        "need_followup": need_followup,
        "reason": reason,
        "strategy": strategy,
        "llm_called": llm_called,
        "generated": generated,
        "sent": sent,
        "engine": engine,
    }
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
            ),
        )
        latest_user = current["user_texts"][-1] if current.get("user_texts") else ""
        failure_hooks.record_followup_violation(
            user_data,
            user_text=latest_user,
            followup_question=result["followup_question"],
        )
        session.record_question(user_data, draft, result)
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

    skip_reason = result.get("skip_reason") or "information_already_complete"
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
