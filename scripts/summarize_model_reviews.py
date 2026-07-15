"""Summarize human review JSON against model comparison results."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    results_path = Path(args.results)
    reviews_path = Path(args.reviews)
    output_dir = Path(args.output_dir) if args.output_dir else results_path.parent

    results = load_jsonl(results_path)
    review_payload = json.loads(reviews_path.read_text(encoding="utf-8"))
    reviews = review_payload.get("reviews") or review_payload
    label_maps = review_payload.get("label_maps") or {}

    wins: dict[str, int] = defaultdict(int)
    fidelity: dict[str, list[float]] = defaultdict(list)
    interpretation: dict[str, list[float]] = defaultdict(list)
    question_scores: dict[str, list[float]] = defaultdict(list)
    project_correct = 0
    project_total = 0
    over_interp = 0
    over_total = 0
    reask = 0
    reask_total = 0

    for case_id, rev in reviews.items():
        if not isinstance(rev, dict):
            continue
        label_map = rev.get("label_map") or label_maps.get(case_id) or {}
        best = rev.get("best")
        if best in label_map:
            wins[label_map[best]] += 1
        elif best == "tie":
            wins["tie"] += 1
        elif best == "all_bad":
            wins["all_bad"] += 1

        scores = rev.get("scores") or {}
        for label, score in scores.items():
            model = label_map.get(label)
            if not model or not isinstance(score, dict):
                continue
            if score.get("fidelity") is not None:
                fidelity[model].append(float(score["fidelity"]))
            if score.get("interpretation") is not None:
                interpretation[model].append(float(score["interpretation"]))
            if score.get("question") is not None:
                question_scores[model].append(float(score["question"]))

        if rev.get("project_accuracy"):
            project_total += 1
            if rev["project_accuracy"] == "correct":
                project_correct += 1
        if rev.get("over_interpretation"):
            over_total += 1
            if rev["over_interpretation"] == "yes":
                over_interp += 1
        if rev.get("answered_again"):
            reask_total += 1
            if rev["answered_again"] == "yes":
                reask += 1

    by_model: dict[str, dict] = {}
    models = sorted({r["model"] for r in results})
    for model in models:
        rows = [r for r in results if r["model"] == model]
        ok = [r for r in rows if not r.get("error")]
        q_gen = sum(
            1
            for r in ok
            if (r.get("question_result") or {}).get("needs_followup")
            and (r.get("question_result") or {}).get("followup_question")
        )
        q_reject = sum(
            1
            for r in ok
            if (r.get("question_result") or {}).get("skip_reason")
            or (r.get("question_result") or {}).get("rejected_candidates")
        )
        lat = [r.get("latency_ms") or 0 for r in ok]
        costs = [r["estimated_cost_usd"] for r in ok if r.get("estimated_cost_usd") is not None]

        def avg(xs: list[float]) -> float | None:
            return round(statistics.mean(xs), 3) if xs else None

        by_model[model] = {
            "wins": wins.get(model, 0),
            "avg_fidelity": avg(fidelity.get(model, [])),
            "avg_interpretation_usefulness": avg(interpretation.get(model, [])),
            "avg_question_usefulness": avg(question_scores.get(model, [])),
            "question_generation_rate": round(q_gen / len(ok), 4) if ok else None,
            "question_reject_rate": round(q_reject / len(ok), 4) if ok else None,
            "error_rate": round(len([r for r in rows if r.get("error")]) / len(rows), 4) if rows else None,
            "avg_latency_ms": avg(lat),
            "avg_input_tokens": avg(
                [(r.get("usage") or {}).get("input_tokens") for r in ok if (r.get("usage") or {}).get("input_tokens") is not None]
            ),
            "avg_output_tokens": avg(
                [(r.get("usage") or {}).get("output_tokens") for r in ok if (r.get("usage") or {}).get("output_tokens") is not None]
            ),
            "avg_reasoning_tokens": avg(
                [
                    (r.get("usage") or {}).get("reasoning_tokens")
                    for r in ok
                    if (r.get("usage") or {}).get("reasoning_tokens") is not None
                ]
            ),
            "avg_cost_per_case_usd": avg(costs) if costs else None,
            "total_estimated_cost_usd": round(sum(costs), 6) if costs else None,
        }

    summary = {
        "human_reviews_present": bool(reviews),
        "wins": dict(wins),
        "project_accuracy_rate": round(project_correct / project_total, 4) if project_total else None,
        "over_interpretation_rate": round(over_interp / over_total, 4) if over_total else None,
        "answered_again_rate": round(reask / reask_total, 4) if reask_total else None,
        "models": by_model,
        "note": "No automatic winner without human reviews.",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "human_review_summary.json"
    md_path = output_dir / "human_review_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Human Review Summary",
        "",
        f"- reviews: {len(reviews)}",
        f"- project_accuracy_rate: {summary['project_accuracy_rate']}",
        f"- over_interpretation_rate: {summary['over_interpretation_rate']}",
        f"- answered_again_rate: {summary['answered_again_rate']}",
        "",
        "| model | wins | fidelity | interpretation | question | error_rate | avg_latency_ms | avg_cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, stats in by_model.items():
        lines.append(
            f"| {model} | {stats['wins']} | {stats['avg_fidelity']} | "
            f"{stats['avg_interpretation_usefulness']} | {stats['avg_question_usefulness']} | "
            f"{stats['error_rate']} | {stats['avg_latency_ms']} | {stats['avg_cost_per_case_usd']} |"
        )
    lines.append("")
    lines.append("사람 평가가 충분하기 전에는 최종 승자를 선언하지 않는다.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"json={json_path}")
    print(f"md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
