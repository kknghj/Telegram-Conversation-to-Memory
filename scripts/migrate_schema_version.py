"""schema_version 마이그레이션 — 백업 후 schema_version 필드 추가."""

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

from conversation_to_memory.reflection.schema import detect_schema_version, ensure_schema_version

DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"


def migrate_memories(
    memories_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    directory = memories_dir or DEFAULT_MEMORIES_DIR
    if not directory.exists():
        raise FileNotFoundError(f"메모 디렉터리가 없습니다: {directory}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = directory.parent / f"memories_backup_{timestamp}"

    files = sorted(directory.glob("*.json"))
    summary = {
        "total": len(files),
        "updated": 0,
        "already_versioned": 0,
        "backup_dir": str(backup_dir),
        "dry_run": dry_run,
        "details": [],
    }

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filepath in files:
            shutil.copy2(filepath, backup_dir / filepath.name)

    for filepath in files:
        with open(filepath, encoding="utf-8") as f:
            memory = json.load(f)

        before = memory.get("schema_version")
        ensure_schema_version(memory)
        after = memory["schema_version"]

        detail = {
            "file": filepath.name,
            "schema_version": after,
            "detected_from": detect_schema_version(memory),
        }
        summary["details"].append(detail)

        if before in (1, 2):
            summary["already_versioned"] += 1
        else:
            summary["updated"] += 1

        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="메모 JSON에 schema_version 추가")
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
    result = migrate_memories(args.memories_dir, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
