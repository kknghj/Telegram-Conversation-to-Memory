"""schema_version 마이그레이션 — 백업 후 schema_version·migration_status 추가."""

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

from conversation_to_memory.migration.schema import backfill_schema_version

DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"


def migrate_schema_version(
    memories_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    """schema_version 백필. migrated_count / skipped_count / ids 반환."""
    directory = memories_dir or DEFAULT_MEMORIES_DIR
    if not directory.exists():
        raise FileNotFoundError(f"메모 디렉터리가 없습니다: {directory}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = directory.parent / f"memories_backup_{timestamp}"

    files = sorted(directory.glob("*.json"))
    migrated_ids: list[str] = []
    skipped_ids: list[str] = []

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filepath in files:
            shutil.copy2(filepath, backup_dir / filepath.name)

    for filepath in files:
        with open(filepath, encoding="utf-8") as f:
            memory = json.load(f)

        migrated, version = backfill_schema_version(memory)
        memory_id = filepath.stem

        if migrated:
            migrated_ids.append(memory_id)
        else:
            skipped_ids.append(memory_id)

        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)

    return {
        "total": len(files),
        "migrated_count": len(migrated_ids),
        "skipped_count": len(skipped_ids),
        "migrated_ids": migrated_ids,
        "skipped_ids": skipped_ids,
        "backup_dir": str(backup_dir) if not dry_run else None,
        "dry_run": dry_run,
    }


# 하위 호환 alias
migrate_memories = migrate_schema_version


def main() -> None:
    parser = argparse.ArgumentParser(description="메모 JSON schema_version 백필")
    parser.add_argument(
        "--memories-dir",
        type=Path,
        default=DEFAULT_MEMORIES_DIR,
        help="메모 JSON 디렉터리",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="백업·쓰기 없이 판별 결과만 출력",
    )
    args = parser.parse_args()
    result = migrate_schema_version(args.memories_dir, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
