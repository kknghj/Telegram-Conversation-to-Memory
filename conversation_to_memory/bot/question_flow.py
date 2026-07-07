"""Follow-up question routing for the conversation flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app import database as db
from conversation_to_memory.bot import failure_hooks, session, states
from conversation_to_memory.memory import question as question_service


@dataclass
class FollowupResult:
    messages: list[str]
    state: int


ReviewMessageBuilder = Callable[[dict[str, Any]], str]


def _review(draft: dict[str, Any], review_message: ReviewMessageBuilder) -> FollowupResult:
    return FollowupResult(messages=[review_message(draft)], state=states.REVIEW)


def _maybe_reflection_followup_or_review(
    user_id: str,
    user_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    review_message: ReviewMessageBuilder,
) -> FollowupResult:
    trace = session.get_decision_trace(user_data)
    qsession = session.ensure_question_session(user_data)
    if qsession["questions_asked"] >= question_service.get_max_questions():
        if trace is not None:
            trace.record_question_routing(
                sent=False,
                reason="max_questions_reached",
                strategy="reflection",
            )
        return _review(draft, review_message)

    current = session.ensure_session(user_data)
    result = question_service.generate_question(
        user_texts=current["user_texts"],
        conversation=current["conversation"],
        draft=draft,
        question_session=qsession,
        recent_context=session.get_recent_context(user_data),
        trace_collector=trace,
    )
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
        current["conversation"].append(
            {"role": "assistant", "content": result["followup_question"]}
        )
        db.save_active_draft(
            user_id,
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            draft=draft,
        )
        if trace is not None:
            trace.record_question_routing(
                sent=True,
                strategy=str(result.get("question_mode") or "reflection"),
            )
        return FollowupResult(
            messages=[result["followup_question"]],
            state=states.FOLLOWUP,
        )

    if trace is not None:
        reason = trace.question_trace.get("reason") or "information_already_complete"
        trace.record_question_routing(
            sent=False,
            reason=reason,
            strategy=str(result.get("question_mode") or "reflection"),
        )
    return _review(draft, review_message)


def maybe_followup_or_review(
    user_id: str,
    user_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    review_message: ReviewMessageBuilder,
) -> FollowupResult:
    trace = session.get_decision_trace(user_data)

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
        if trace is not None:
            trace.record_question_routing(
                sent=True,
                reason=trace.question_trace.get("reason") or "clarify",
                strategy="legacy_summary",
            )
        return FollowupResult(messages=[question], state=states.FOLLOWUP)

    if trace is not None:
        if followup_asked:
            reason = "followup_already_asked"
        elif not draft.get("needs_followup"):
            reason = trace.question_trace.get("reason") or "information_already_complete"
        else:
            reason = "empty_followup_question"
        trace.record_question_routing(
            sent=False,
            reason=reason,
            strategy="legacy_summary",
        )

    return _review(draft, review_message)
