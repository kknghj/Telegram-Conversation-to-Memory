"""마이그레이션 리포트 생성."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{count / total * 100:.1f}%"


def _format_counter_table(counter: dict, total: int) -> list[str]:
    lines = ["| 값 | 건수 | 비율 |", "|---|---:|---:|"]
    for key, count in sorted(counter.items(), key=lambda x: str(x[0])):
        lines.append(f"| {key} | {count} | {_pct(count, total)} |")
    return lines


def generate_migration_report(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    migration_summary: dict[str, Any],
    output_path: Path,
) -> str:
    """reports/schema_migration_report.md 생성."""
    total = after["total"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Schema Migration Report",
        "",
        f"생성 시각: {now}",
        "",
        "## 요약",
        "",
        f"- 총 메모: **{total}**건",
        f"- schema_version 백필: **{migration_summary.get('schema_migrated', 0)}**건",
        f"- memory_type 백필: **{migration_summary.get('memory_type_migrated', 0)}**건",
        f"- evidence_quality 갱신: **{migration_summary.get('evidence_quality_updated', 0)}**건",
        "",
        "## Before / After",
        "",
        "### schema_version",
        "",
        "**Before**",
        "",
        *_format_counter_table(before["schema_version"], before["total"]),
        "",
        "**After**",
        "",
        *_format_counter_table(after["schema_version"], after["total"]),
        "",
        "### memory_type",
        "",
        "**Before**",
        "",
        *_format_counter_table(before["memory_type"], before["total"]),
        "",
        "**After**",
        "",
        *_format_counter_table(after["memory_type"], after["total"]),
        "",
        "### evidence_quality",
        "",
        *_format_counter_table(after["evidence_quality"], after["total"]),
        "",
        "## derived text 비율",
        "",
        f"- `contains_derived_text`: {after['derived_text_count']}건 ({_pct(after['derived_text_count'], total)})",
        f"- `primary_only`: {after['evidence_quality'].get('primary_only', 0)}건",
        "",
        "## Retrieval 영향 분석",
        "",
        "| 용도 | 건수 | 설명 |",
        "|---|---:|---|",
        f"| 근거 인용 가능 (primary_only) | {after['retrieval']['citable_for_evidence']} | conversation primary 인용 허용 |",
        f"| derived 인용 차단 | {after['retrieval']['blocked_for_derived_citation']} | memory_candidate/summary 인용 금지 |",
        f"| 존재·표본 판단 | {after['retrieval']['available_for_existence']} | sample_size 계산에 포함 |",
        "",
        "## 마이그레이션 ID",
        "",
    ]

    for key in ("schema_migrated_ids", "memory_type_migrated_ids"):
        ids = migration_summary.get(key, [])
        label = "schema_version" if "schema" in key else "memory_type"
        lines.append(f"### {label} ({len(ids)}건)")
        lines.append("")
        for mid in ids:
            lines.append(f"- `{mid}`")
        lines.append("")

    derived_ids = migration_summary.get("derived_text_ids", [])
    lines.extend([
        f"### contains_derived_text ({len(derived_ids)}건)",
        "",
    ])
    for mid in derived_ids:
        lines.append(f"- `{mid}`")
    lines.append("")

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content
