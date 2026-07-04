"""Backfill interpretation_failures.jsonl to Supabase mirror."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = PROJECT_ROOT / "data" / "evaluation" / "interpretation_failures.jsonl"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.interpretation_failures_supabase import (  # noqa: E402
    is_supabase_configured,
    sync_jsonl_to_supabase,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync interpretation_failures.jsonl to Supabase."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_JSONL,
        help=f"JSONL path (default: {DEFAULT_JSONL})",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"JSONL not found: {args.path}", file=sys.stderr)
        return 1

    if not is_supabase_configured():
        print(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_SECRET_KEY.",
            file=sys.stderr,
        )
        return 1

    result = sync_jsonl_to_supabase(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
