"""Export read-only evaluation cases from Supabase drafts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversation_to_memory.evaluation.draft_case_loader import (
    DEFAULT_LIMIT,
    DEFAULT_SEED,
    DEFAULT_STATUSES,
    build_dataset,
    fetch_draft_rows,
    write_dataset,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Export model comparison cases from drafts")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--statuses",
        nargs="+",
        default=list(DEFAULT_STATUSES),
        help="Draft statuses to include (default: saved cancelled)",
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "data" / "evaluation" / "model_comparison"),
    )
    parser.add_argument("--dataset-id", default=None)
    args = parser.parse_args(argv)

    dataset_id = args.dataset_id or datetime.now(timezone.utc).strftime("ds_%Y%m%d_%H%M%S")
    rows = fetch_draft_rows(statuses=args.statuses)
    cases, manifest = build_dataset(
        rows,
        limit=args.limit,
        seed=args.seed,
        statuses=args.statuses,
        dataset_id=dataset_id,
    )
    out_dir = Path(args.output_root) / dataset_id
    paths = write_dataset(cases, manifest, out_dir)
    print(f"dataset_id={dataset_id}")
    print(f"case_count={len(cases)}")
    print(f"cases={paths['cases']}")
    print(f"manifest={paths['manifest']}")
    print(f"status_counts={manifest.get('status_counts')}")
    scarcity = (manifest.get("selection_rules") or {}).get("scarcity") or {}
    if scarcity.get("shortfall"):
        print(f"warning: shortfall={scarcity['shortfall']} (not enough unique cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
