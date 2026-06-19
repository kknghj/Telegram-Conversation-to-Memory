"""Sync MVP round evaluation snapshots to Supabase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MVP_JSON = PROJECT_ROOT / "data" / "evaluation" / "mvp_round2_2026-06-19.json"
DEFAULT_PATTERN_CARDS = (
    PROJECT_ROOT / "data" / "evaluation" / "reflection_evaluations.jsonl"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mvp_evaluation_supabase import (  # noqa: E402
    is_supabase_configured,
    load_mvp_evaluation,
    sync_mvp_bundle_to_supabase,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync MVP round evaluation JSON to Supabase."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_MVP_JSON,
        help=f"MVP evaluation JSON path (default: {DEFAULT_MVP_JSON})",
    )
    parser.add_argument(
        "--pattern-cards-path",
        type=Path,
        default=DEFAULT_PATTERN_CARDS,
        help=f"Pattern card JSONL path (default: {DEFAULT_PATTERN_CARDS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print sync plan without writing to Supabase",
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"MVP evaluation JSON not found: {args.path}", file=sys.stderr)
        return 1

    mvp_data = load_mvp_evaluation(args.path)
    loaded = 1

    if args.dry_run:
        print(f"Loaded MVP evaluations: {loaded}")
        print(f"Would upsert evaluation_id: {mvp_data['evaluation_id']}")
        print(f"Would upsert table: mvp_evaluations")
        print(f"Upserted: {loaded}")
        print("Skipped: 0")
        print("Supabase sync completed.")
        return 0

    if not is_supabase_configured():
        print(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_SECRET_KEY.",
            file=sys.stderr,
        )
        return 1

    result = sync_mvp_bundle_to_supabase(
        mvp_json_path=args.path,
        pattern_cards_path=args.pattern_cards_path,
        dry_run=False,
    )

    upserted = result["upserted_mvp"]
    skipped = result["skipped_mvp"]
    print(f"Loaded MVP evaluations: {loaded}")
    print(f"Upserted: {upserted}")
    print(f"Skipped: {skipped}")

    pattern = result["pattern_cards"]
    print(
        "Pattern cards synced: "
        f"{pattern['synced']}/{pattern['total']} "
        f"(failed: {pattern['failed']})"
    )

    if skipped > 0 or pattern["failed"] > 0:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    print("Supabase sync completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
