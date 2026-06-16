"""전체 memory schema migration 파이프라인."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conversation_to_memory.migration.evidence_quality import backfill_evidence_quality
from conversation_to_memory.migration.memory_type import backfill_memory_type
from conversation_to_memory.migration.report import generate_migration_report
from conversation_to_memory.migration.schema import backfill_schema_version
from conversation_to_memory.migration.stats import collect_migration_stats

DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "schema_migration_report.md"


def _load_memories(directory: Path) -> list[tuple[Path, dict]]:
    result = []
    for filepath in sorted(directory.glob("*.json")):
        with open(filepath, encoding="utf-8") as f:
            result.append((filepath, json.load(f)))
    return result


def run_full_migration(
    memories_dir: Path | None = None,
    *,
    report_path: Path | None = None,
    dry_run: bool = False,
) -> dict:
    directory = memories_dir or DEFAULT_MEMORIES_DIR
    if not directory.exists():
        raise FileNotFoundError(f"메모 디렉터리가 없습니다: {directory}")

    entries = _load_memories(directory)
    before_stats = collect_migration_stats([m for _, m in entries])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = directory.parent / f"memories_backup_{timestamp}"

    schema_migrated_ids: list[str] = []
    memory_type_migrated_ids: list[str] = []
    evidence_updated_ids: list[str] = []
    derived_text_ids: list[str] = []

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filepath, _ in entries:
            shutil.copy2(filepath, backup_dir / filepath.name)

    for filepath, memory in entries:
        memory_id = filepath.stem

        if backfill_schema_version(memory)[0]:
            schema_migrated_ids.append(memory_id)

        if backfill_memory_type(memory, memory_id=memory_id)[0]:
            memory_type_migrated_ids.append(memory_id)

        if backfill_evidence_quality(memory)[0]:
            evidence_updated_ids.append(memory_id)

        if memory.get("evidence_quality") == "contains_derived_text":
            derived_text_ids.append(memory_id)

        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)

    after_stats = collect_migration_stats([m for _, m in entries])

    summary = {
        "schema_migrated": len(schema_migrated_ids),
        "memory_type_migrated": len(memory_type_migrated_ids),
        "evidence_quality_updated": len(evidence_updated_ids),
        "schema_migrated_ids": schema_migrated_ids,
        "memory_type_migrated_ids": memory_type_migrated_ids,
        "derived_text_ids": derived_text_ids,
        "backup_dir": str(backup_dir) if not dry_run else None,
        "dry_run": dry_run,
    }

    if not dry_run:
        report = report_path or DEFAULT_REPORT_PATH
        generate_migration_report(
            before=before_stats,
            after=after_stats,
            migration_summary=summary,
            output_path=report,
        )
        summary["report_path"] = str(report)

    summary["before"] = before_stats
    summary["after"] = after_stats
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="memory schema 전체 마이그레이션")
    parser.add_argument("--memories-dir", type=Path, default=DEFAULT_MEMORIES_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_full_migration(
        args.memories_dir,
        report_path=args.report_path,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
