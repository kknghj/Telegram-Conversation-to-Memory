"""Migrate local JSON memories to Supabase."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conversation_to_memory.migration.migration_service import (  # noqa: E402
    MigrationService,
    print_apply_summary,
    print_dry_run_summary,
)
from conversation_to_memory.storage.local_json import DEFAULT_MEMORIES_DIR  # noqa: E402
from conversation_to_memory.storage.supabase import SupabaseStorageError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate approved local JSON memories to Supabase."
    )
    parser.add_argument(
        "--memories-dir",
        type=Path,
        default=DEFAULT_MEMORIES_DIR,
        help=f"Source directory (default: {DEFAULT_MEMORIES_DIR})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform actual inserts (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without inserting (default behavior)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    try:
        service = MigrationService(
            source_dir=args.memories_dir,
            dry_run=dry_run,
        )
        summary = service.migrate()
    except SupabaseStorageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if dry_run:
        print_dry_run_summary(summary)
    else:
        print_apply_summary(summary)

    if summary.report_path:
        print()
        print(f"Report: {summary.report_path}")
    if summary.log_path:
        print(f"Log: {summary.log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
