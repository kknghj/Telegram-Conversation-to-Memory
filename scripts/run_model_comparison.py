"""Run fair multi-model draft+question comparison (evaluation only)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversation_to_memory.evaluation.html_report import generate_comparison_html
from conversation_to_memory.evaluation.model_comparison import (
    DEFAULT_MODELS,
    load_cases,
    run_comparison,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run model comparison replay")
    parser.add_argument("--dataset", required=True, help="Path to cases.jsonl")
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: reports/model_comparison/<run_id>)",
    )
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--cases", nargs="*", default=None, help="Optional case_id filter")
    parser.add_argument("--only-models", nargs="*", default=None)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--no-html", action="store_true")
    args = parser.parse_args(argv)

    dataset = Path(args.dataset)
    cases = load_cases(dataset)
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else ROOT / "reports" / "model_comparison" / run_id

    # Never mutate OPENAI_MODEL; models are passed as function args.
    result = run_comparison(
        cases=cases,
        models=list(args.models),
        output_dir=output,
        concurrency=args.concurrency,
        force=args.force,
        only_cases=args.cases,
        only_models=args.only_models,
        seed=args.seed,
        probe=not args.skip_probe,
    )

    if not args.no_html:
        generate_comparison_html(
            cases=cases,
            results=result["results"],
            manifest=result["manifest"],
            output_path=output / "comparison.html",
        )
        print(f"html={output / 'comparison.html'}")

    print(f"output={output}")
    print(f"results={output / 'results.jsonl'}")
    print(f"summary={output / 'summary.json'}")
    access = result["manifest"].get("model_access") or []
    for row in access:
        if not row.get("ok"):
            err = row.get("error") or {}
            print(
                f"model_access_error model={row.get('model')} "
                f"category={err.get('category')} message={err.get('message')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
