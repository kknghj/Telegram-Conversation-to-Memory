"""원문 충실도 검사 — GPT 출력 후처리."""

from __future__ import annotations

import re

FORBIDDEN_INFERENCE_TERMS = (
    "견뎌",
    "성장",
    "칭찬",
    "교훈",
    "깨달음",
    "배운",
    "극복",
    "의미 있는",
    "소중한",
)

GROWTH_NARRATIVE_PHRASES = (
    "힘든 순간을 견뎌",
    "자신을 칭찬",
    "성장",
    "배운 점",
    "소중한 깨달음",
)

POSITIVE_REFRAMING_TERMS = (
    "지원",
    "배려",
    "격려",
    "응원",
    "도움",
    "도와",
)

ROLE_GENERALIZATION_RE = re.compile(r"관리자.{0,12}역할")
INFERRED_EMOTION_RE = re.compile(r"복잡한\s*감정")
ACTOR_POSITIVE_RE = re.compile(r"(팀장|상사|부모|교사|관리자).{0,12}(지원|배려|도움|격려)")

# 미래/미완료 사건을 나타내는 시제 표지. 이 표현이 있으면 완료된 사실처럼 요약하지 않는다.
FUTURE_TENSE_MARKERS: tuple[str, ...] = (
    "예정",
    "신청했",
    "신청할",
    "들을 예정",
    "다음 주",
    "다음주",
    "다음 달",
    "다음달",
    "계획이",
    "계획하",
    "할 예정",
    "하기로 했",
    "예약했",
    "앞두고",
)

# 반복 가능한 가치 판단 → value_tags. 키워드 하나라도 원문에 있으면 태그를 부여한다.
VALUE_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "사용자 시간 절약": ("시간을 줄이", "일을 줄이", "시간 절약", "수고를 덜", "시간과 마음을 낭비", "시간을 낭비"),
    "편의성": ("편의성", "편리", "편하게"),
    "생산성": ("생산성", "효율"),
    "다크패턴 거부": ("중간 광고", "상주시간", "상주 시간", "다크패턴", "다크 패턴", "무식하게"),
    "불안 마케팅 거부": ("불안을 이용", "불안 마케팅", "차단에 대한 불안", "불안을 자극"),
}

# 지속적으로 추적할 사용자 프로젝트 엔티티. 별칭을 정규화된 이름으로 매핑한다.
PROJECT_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "GPTERS": ("gpters", "지피터스", "지피터스 ai", "지피터스 강의"),
    "Harness": ("harness", "하네스", "하네스 구축"),
    "Cursor": ("cursor", "커서"),
    "Codex": ("codex", "코덱스"),
    "Telegram Conversation to Memory": (
        "conversation to memory",
        "conversation-to-memory",
        "대화를 기억으로",
    ),
    "토스 미니앱": ("토스 미니앱", "토스미니앱", "토스 앱 제작", "토스 앱"),
}

# 개발 철학·일에 대한 관점·인간관계 가치관·반복 가능한 판단 기준·프로젝트 선택 기준 신호.
# 이 신호가 있으면 reflection_seed 후보(장기 패턴)로 표시한다.
REFLECTION_SEED_SIGNALS: tuple[str, ...] = (
    "만들고 싶",
    "중요하게 여기",
    "중요하다고 생각",
    "가치관",
    "철학",
    "신념",
    "지향",
    "추구",
    "원칙",
    "기준으로",
    "판단 기준",
    "거리낌",
    "거부감",
    "낭비한다는 생각",
    "낭비라고",
    "옳지 않다",
    "하고 싶지 않",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def term_in_source(term: str, source_text: str) -> bool:
    return term in source_text


def _combined_output_text(draft: dict) -> str:
    searchable_fields = [
        draft.get("topic", ""),
        draft.get("event_summary", ""),
        draft.get("memory_candidate", ""),
        draft.get("model_interpretation", ""),
        " ".join(draft.get("user_emotions", [])),
        " ".join(draft.get("emerging_themes", [])),
    ]
    return " ".join(str(v) for v in searchable_fields)


def _detect_positive_reframing(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    for term in POSITIVE_REFRAMING_TERMS:
        if term in combined_output and term not in source:
            label = f"unsupported_positive_reframing: '{term}' (원문에 없음)"
            if label not in found:
                found.append(label)
    return found


def _detect_role_generalization(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    if ROLE_GENERALIZATION_RE.search(combined_output) and "역할" not in source:
        found.append("topic_shift: 관리자의 역할 일반화")
    if INFERRED_EMOTION_RE.search(combined_output) and "복잡한" not in source:
        found.append("unsupported_motivation: 복잡한 감정 (원문에 없음)")
    return found


def _detect_actor_evaluation(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    match = ACTOR_POSITIVE_RE.search(combined_output)
    if match:
        term = match.group(2)
        if term not in source:
            found.append(f"actor_evaluation_inference: '{match.group(0)}' (원문에 없음)")
    return found


def detect_unsupported_inferences(draft: dict, source_text: str) -> list[str]:
    """원문에 없는 긍정적 재해석·성장 서사·역할 일반화를 탐지."""
    source = _normalize_text(source_text)
    found: list[str] = []
    combined_output = _combined_output_text(draft)

    for phrase in GROWTH_NARRATIVE_PHRASES:
        if phrase in combined_output and phrase not in source:
            found.append(phrase)

    for term in FORBIDDEN_INFERENCE_TERMS:
        if term in combined_output and not term_in_source(term, source):
            label = {
                "견뎌": "자기칭찬/견딤 서사",
                "성장": "성장",
                "칭찬": "자기칭찬",
                "교훈": "교훈",
                "깨달음": "깨달음",
                "배운": "교훈",
            }.get(term, term)
            if label not in found:
                found.append(label)

    for detector in (
        _detect_positive_reframing,
        _detect_role_generalization,
        _detect_actor_evaluation,
    ):
        for item in detector(combined_output, source):
            if item not in found:
                found.append(item)

    existing = draft.get("unsupported_inferences", [])
    for item in existing:
        if item not in found:
            found.append(item)

    return found


def detect_future_tense(source_text: str) -> list[str]:
    """미래/미완료 사건 시제 표지를 탐지."""
    source = _normalize_text(source_text)
    return [marker for marker in FUTURE_TENSE_MARKERS if marker in source]


def infer_temporal_status(source_text: str) -> str:
    """원문 시제를 past/future/mixed로 분류.

    미래 표지가 있으면 완료 사건으로 단정하지 않도록 future/mixed로 표시한다.
    """
    source = _normalize_text(source_text)
    has_future = bool(detect_future_tense(source))
    # 완료된 과거 사건 표지 (했다/였다/봤다 등 종결).
    has_past = bool(re.search(r"(했어|했다|였어|였다|봤어|봤다|됐어|됐다|드러났)", source))
    if has_future and has_past:
        return "mixed"
    if has_future:
        return "future"
    return "past"


def detect_value_tags(source_text: str) -> list[str]:
    """반복 가능한 가치 판단을 value_tags로 추출."""
    source = _normalize_text(source_text)
    found: list[str] = []
    for tag, keywords in VALUE_TAG_KEYWORDS.items():
        if any(keyword in source for keyword in keywords) and tag not in found:
            found.append(tag)
    return found


def detect_project_entities(source_text: str) -> list[str]:
    """지속 프로젝트 엔티티를 정규화된 이름으로 추출."""
    source = _normalize_text(source_text).lower()
    found: list[str] = []
    for canonical, aliases in PROJECT_ENTITY_ALIASES.items():
        if any(alias.lower() in source for alias in aliases) and canonical not in found:
            found.append(canonical)
    return found


def detect_reflection_seed_signals(source_text: str) -> list[str]:
    """개발 철학·가치관·판단 기준 등 reflection_seed 신호를 탐지."""
    source = _normalize_text(source_text)
    return [signal for signal in REFLECTION_SEED_SIGNALS if signal in source]


def is_reflection_seed_candidate(draft: dict, source_text: str) -> bool:
    """장기 패턴(가치관·철학) 후보인지 판단."""
    if draft.get("memory_type") == "reflection_seed":
        return True
    if draft.get("reflection_seed_candidate"):
        return True
    return bool(detect_reflection_seed_signals(source_text) or detect_value_tags(source_text))


def draft_hides_value(draft: dict, source_text: str) -> bool:
    """가치관이 핵심인데 사건 위주 요약으로 가치가 가려졌는지 판단.

    원문에 가치관·판단 기준 신호가 있는데도 draft가 이를 반영하지 못하면 True.
    """
    has_value = bool(
        detect_reflection_seed_signals(source_text) or detect_value_tags(source_text)
    )
    if not has_value:
        return False

    if draft.get("memory_type") == "reflection_seed":
        return False
    if draft.get("reflection_seed_candidate"):
        return False
    if draft.get("value_tags"):
        return False

    # 가치 신호가 event_summary에 반영되어 있으면 가려지지 않은 것으로 본다.
    summary = _normalize_text(str(draft.get("event_summary", "")))
    signals = detect_reflection_seed_signals(source_text)
    if any(signal in summary for signal in signals):
        return False
    return True


def assess_interpretation_risk(draft: dict, source_text: str) -> str:
    unsupported = detect_unsupported_inferences(draft, source_text)
    if unsupported:
        return "high" if len(unsupported) >= 2 else "medium"
    current = draft.get("interpretation_risk", "low")
    if current in ("low", "medium", "high"):
        return current
    return "low"


def validate_draft(draft: dict, source_text: str) -> dict:
    """후처리: unsupported_inferences 보강 및 interpretation_risk 재평가.

    추가로 가치관 태그, 프로젝트 엔티티, 시제, reflection_seed 후보를 보강한다.
    """
    unsupported = detect_unsupported_inferences(draft, source_text)
    risk = assess_interpretation_risk(draft, source_text)

    validated = dict(draft)
    validated["unsupported_inferences"] = unsupported
    validated["interpretation_risk"] = risk

    # 가치관 태그 병합 (원문 근거 있는 것만).
    value_tags = list(validated.get("value_tags") or [])
    for tag in detect_value_tags(source_text):
        if tag not in value_tags:
            value_tags.append(tag)
    validated["value_tags"] = value_tags

    # 프로젝트 엔티티 병합.
    projects = list(validated.get("projects") or [])
    for project in detect_project_entities(source_text):
        if project not in projects:
            projects.append(project)
    validated["projects"] = projects

    # 시제 분류: 미래 사건을 완료 사실로 단정하지 않도록 표시.
    validated["temporal_status"] = infer_temporal_status(source_text)

    # reflection_seed 후보 표시 및 memory_type 승격.
    seed_candidate = is_reflection_seed_candidate(validated, source_text)
    validated["reflection_seed_candidate"] = seed_candidate
    if seed_candidate and validated.get("memory_type") == "event" and draft_hides_value(
        draft, source_text
    ):
        validated["memory_type"] = "reflection_seed"

    return validated


def contains_forbidden_growth_narrative(draft: dict) -> bool:
    """테스트용: 금지 성장 서사 포함 여부."""
    text = " ".join(
        [
            draft.get("event_summary", ""),
            draft.get("memory_candidate", ""),
        ]
    )
    return any(phrase in text for phrase in GROWTH_NARRATIVE_PHRASES)
