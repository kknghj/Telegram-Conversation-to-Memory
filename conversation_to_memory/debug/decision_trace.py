"""Decision Trace Mode — structured observability for question and project decisions."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TRACE_DIR = PROJECT_ROOT / "data" / "debug_traces"

QUESTION_TRACE_DEFAULT: dict[str, Any] = {
    "evaluated": False,
    "need_followup": False,
    "reason": "",
    "strategy": "",
    "llm_called": False,
    "generated": False,
    "question": "",
    "sent": False,
}

PROJECT_TRACE_DEFAULT: dict[str, Any] = {
    "evaluated": False,
    "detected": False,
    "candidate_projects": [],
    "llm_projects": [],
    "keyword_projects": [],
    "selected_project": "",
    "confidence": None,
    "tag_written": False,
    "reason": "",
}


def is_decision_trace_enabled() -> bool:
    return os.getenv("DEBUG_DECISION_TRACE", "false").lower() in ("true", "1", "yes")


def _trace_dir() -> Path:
    raw = os.getenv("DEBUG_TRACE_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_TRACE_DIR


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "-"
    return "YES" if value else "NO"


def format_trace_cli(trace: dict[str, Any]) -> str:
    """Format question and project traces for terminal output."""
    question = trace.get("question_trace") or {}
    project = trace.get("project_trace") or {}

    lines = [
        "========================",
        "Question Decision",
        "",
        f"Need Follow-up : {_yes_no(question.get('need_followup'))}",
    ]

    if question.get("reason"):
        lines.append(f"Reason         : {question['reason']}")
    if question.get("strategy"):
        lines.append(f"Strategy       : {question['strategy']}")
    if question.get("evaluated"):
        lines.append(f"LLM Called     : {_yes_no(question.get('llm_called'))}")
        lines.append(f"Generated      : {_yes_no(question.get('generated'))}")
        lines.append(f"Question Sent  : {_yes_no(question.get('sent'))}")
        if question.get("question"):
            lines.append(f"Question       : {question['question']}")

    lines.extend(
        [
            "",
            "========================",
            "",
            "Project Detection",
            "",
            f"Detected       : {_yes_no(project.get('detected'))}",
        ]
    )

    candidates = project.get("candidate_projects") or []
    if candidates:
        lines.append(f"Candidates     : {', '.join(candidates)}")
    if project.get("selected_project"):
        lines.append(f"Selected       : {project['selected_project']}")
    confidence = project.get("confidence")
    if confidence is not None:
        lines.append(f"Confidence     : {confidence}")
    if project.get("evaluated"):
        lines.append(f"Tag Saved      : {_yes_no(project.get('tag_written'))}")
    if project.get("reason"):
        lines.append(f"Reason         : {project['reason']}")

    lines.append("")
    lines.append("========================")
    return "\n".join(lines)


def build_project_trace(
    *,
    llm_projects: list[str] | None = None,
    keyword_projects: list[str] | None = None,
    final_projects: list[str] | None = None,
    parse_error: str | None = None,
    llm_called: bool = True,
) -> dict[str, Any]:
    """Build a project detection trace from pipeline inputs and outputs."""
    llm_list = list(llm_projects or [])
    keyword_list = list(keyword_projects or [])
    final_list = list(final_projects or [])

    candidates: list[str] = []
    for project in llm_list + keyword_list:
        if project and project not in candidates:
            candidates.append(project)

    trace = {**PROJECT_TRACE_DEFAULT, "evaluated": True, "llm_called": llm_called}
    trace["llm_projects"] = llm_list
    trace["keyword_projects"] = keyword_list
    trace["candidate_projects"] = candidates

    if parse_error:
        trace.update(
            {
                "detected": False,
                "tag_written": False,
                "reason": "json_parse_failed",
                "parse_error": parse_error,
            }
        )
        return trace

    if not candidates and not final_list:
        trace.update(
            {
                "detected": False,
                "tag_written": False,
                "reason": "no_project_detected",
            }
        )
        return trace

    detected = bool(final_list)
    selected = final_list[0] if final_list else (candidates[0] if candidates else "")

    if selected in keyword_list:
        confidence = 1.0
    elif selected in llm_list:
        confidence = 0.85
    elif selected:
        confidence = 0.7
    else:
        confidence = None

    trace.update(
        {
            "detected": detected or bool(candidates),
            "selected_project": selected,
            "confidence": confidence,
            "tag_written": bool(final_list),
        }
    )

    if candidates and not final_list:
        trace["reason"] = "merge_failed_or_empty_final"
    elif not candidates and final_list:
        trace["reason"] = "unexpected_final_without_candidates"

    return trace


class DecisionTraceCollector:
    """Accumulates decision traces for one memo session."""

    def __init__(self) -> None:
        self.question_trace: dict[str, Any] = dict(QUESTION_TRACE_DEFAULT)
        self.project_trace: dict[str, Any] = dict(PROJECT_TRACE_DEFAULT)
        self.trace_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "question_trace": self.question_trace,
            "project_trace": self.project_trace,
            "trace_path": self.trace_path,
        }

    def set_project_trace(self, trace: dict[str, Any]) -> None:
        self.project_trace = {**PROJECT_TRACE_DEFAULT, **trace}

    def update_question_trace(self, **fields: Any) -> None:
        self.question_trace.update(fields)

    def record_legacy_summary_question(
        self,
        *,
        needs_followup: bool,
        followup_question: str,
        llm_called: bool = True,
    ) -> None:
        """Record LLM question decision from the summary/analyze step (legacy mode)."""
        generated = bool(needs_followup and followup_question)
        reason = ""
        if not generated:
            reason = "information_already_complete"

        self.update_question_trace(
            evaluated=True,
            need_followup=needs_followup,
            reason=reason,
            strategy="legacy_summary",
            llm_called=llm_called,
            generated=generated,
            question=followup_question if generated else "",
            sent=False,
        )

    def record_question_routing(
        self,
        *,
        sent: bool,
        reason: str = "",
        strategy: str = "",
    ) -> None:
        """Record whether the follow-up question was actually sent to the user."""
        updates: dict[str, Any] = {"sent": sent}
        if reason:
            updates["reason"] = reason
        if strategy:
            updates["strategy"] = strategy
        if sent:
            updates["need_followup"] = True
            updates["generated"] = True
        self.update_question_trace(**updates)

    def record_reflection_question_result(
        self,
        *,
        result: dict[str, Any],
        llm_called: bool,
        skip_reason: str = "",
    ) -> None:
        """Record reflection-agent question generation outcome."""
        generated = bool(result.get("needs_followup") and result.get("followup_question"))
        reason = skip_reason
        if not reason and not generated:
            reason = "information_already_complete"

        self.update_question_trace(
            evaluated=True,
            need_followup=bool(result.get("needs_followup")),
            reason=reason,
            strategy=result.get("question_mode") or "reflection",
            llm_called=llm_called,
            generated=generated,
            question=str(result.get("followup_question") or ""),
            sent=False,
        )

    def save(self, *, timestamp: datetime | None = None) -> str:
        """Persist trace to disk and return the file path."""
        when = timestamp or datetime.now()
        trace_dir = _trace_dir()
        trace_dir.mkdir(parents=True, exist_ok=True)
        filename = when.strftime("%Y-%m-%d_%H%M%S") + ".trace.json"
        filepath = trace_dir / filename

        payload = {
            "timestamp": when.isoformat(),
            "question_trace": self.question_trace,
            "project_trace": self.project_trace,
        }
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        self.trace_path = str(filepath)
        return self.trace_path


def save_decision_trace(
    collector: DecisionTraceCollector,
    *,
    timestamp: datetime | None = None,
) -> str:
    """Save a decision trace if debug mode is enabled."""
    if not is_decision_trace_enabled():
        return ""
    return collector.save(timestamp=timestamp)
