"""Sync all evaluation mirrors (MVP round, pattern cards, interpretation failures) to Supabase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "data" / "evaluation"

DEFAULT_MVP_JSON = EVAL_DIR / "mvp_round3_2026-07-04.json"
DEFAULT_PATTERN_CARDS = EVAL_DIR / "reflection_evaluations.jsonl"
DEFAULT_FAILURES = EVAL_DIR / "interpretation_failures.jsonl"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation_supabase import is_supabase_configured, sync_jsonl_to_supabase  # noqa: E402
from app.interpretation_failures_supabase import (  # noqa: E402
    sync_jsonl_to_supabase as sync_failures_jsonl,
)
from app.mvp_evaluation_supabase import sync_mvp_bundle_to_supabase  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync MVP snapshot, pattern cards, and interpretation failures to Supabase."
    )
    parser.add_argument(
        "--mvp-path",
        type=Path,
        default=DEFAULT_MVP_JSON,
        help=f"MVP evaluation JSON (default: {DEFAULT_MVP_JSON.name})",
    )
    parser.add_argument(
        "--pattern-cards-path",
        type=Path,
        default=DEFAULT_PATTERN_CARDS,
        help="Pattern card JSONL path",
    )
    parser.add_argument(
        "--failures-path",
        type=Path,
        default=DEFAULT_FAILURES,
        help="interpretation_failures.jsonl path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate paths only; do not write to Supabase",
    )
    args = parser.parse_args()

    missing = [p for p in (args.mvp_path, args.pattern_cards_path, args.failures_path) if not p.exists()]
    if missing:
        for path in missing:
            print(f"File not found: {path}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(
            {
                "dry_run": True,
                "mvp_path": str(args.mvp_path),
                "pattern_cards_path": str(args.pattern_cards_path),
                "failures_path": str(args.failures_path),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    if not is_supabase_configured():
        print(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_SECRET_KEY in .env",
            file=sys.stderr,
        )
        return 1

    mvp_result = sync_mvp_bundle_to_supabase(
        mvp_json_path=args.mvp_path,
        pattern_cards_path=args.pattern_cards_path,
        dry_run=False,
    )
    cards_result = sync_jsonl_to_supabase(args.pattern_cards_path)
    failures_result = sync_failures_jsonl(args.failures_path)

    summary = {
        "mvp": mvp_result,
        "all_pattern_cards": cards_result,
        "interpretation_failures": failures_result,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    failed = (
        mvp_result.get("skipped_mvp", 0)
        + mvp_result["pattern_cards"]["failed"]
        + cards_result["failed"]
        + failures_result["failed"]
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
