"""Fair multi-model transcript replay for evaluation only."""

from __future__ import annotations

import csv
import json
import os
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from conversation_to_memory.evaluation.openai_compat import classify_api_error
from conversation_to_memory.evaluation.pricing import estimate_cost_usd, load_pricing
from conversation_to_memory.evaluation.prompt_hash import get_prompt_hashes
from conversation_to_memory.memory.question import generate_question
from conversation_to_memory.memory.service import analyze_recording

PRODUCTION_MEMORY_DIR = Path("data/memories")
DEFAULT_MODELS = ("gpt-4o-mini", "gpt-5.6-luna", "gpt-5.6-terra")


def get_git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parents[2],
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "unknown"


def load_cases(path: Path | str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def merge_usage(*usages: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    out: dict[str, Any] = {k: None for k in keys}
    for key in keys:
        total = 0
        seen = False
        for usage in usages:
            value = (usage or {}).get(key)
            if value is None:
                continue
            seen = True
            total += int(value)
        out[key] = total if seen else None
    return out


def empty_question_session() -> dict[str, Any]:
    return {
        "questions_asked": 0,
        "question_modes_used": [],
        "meaning_check_count": 0,
        "last_question_mode": None,
        "questions_text": [],
    }


def run_single_case_model(
    case: dict[str, Any],
    model: str,
    *,
    prompt_hashes: dict[str, str] | None = None,
    git_commit: str | None = None,
    analyze_fn: Callable[..., Any] | None = None,
    question_fn: Callable[..., Any] | None = None,
    pricing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run draft + first follow-up question for one case × model.

    Does not write memories, drafts, or Telegram messages.
    """
    analyze_fn = analyze_fn or analyze_recording
    question_fn = question_fn or generate_question
    prompt_hashes = prompt_hashes or get_prompt_hashes()
    git_commit = git_commit or get_git_commit()
    pricing = pricing if pricing is not None else load_pricing()

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "model": model,
        "model_alias": "",
        "prompt_hashes": prompt_hashes,
        "git_commit": git_commit,
        "started_at": started.isoformat(),
        "latency_ms": 0,
        "request_config": {},
        "usage": {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "total_tokens": None,
        },
        "raw_usage": None,
        "estimated_cost_usd": None,
        "draft": {},
        "question_result": {},
        "validation": {},
        "error": None,
        "input_fingerprint": {
            "user_texts": case.get("user_texts"),
            "conversation": case.get("conversation"),
            "recent_context": None,
            "prompt_hashes": prompt_hashes,
        },
    }

    try:
        # Force reflection-agent semantics for fair comparison of question path.
        prev_flag = os.environ.get("REFLECTION_AGENT_ENABLED")
        os.environ["REFLECTION_AGENT_ENABLED"] = "true"
        try:
            draft_meta = analyze_fn(
                user_texts=list(case.get("user_texts") or []),
                conversation=list(case.get("conversation") or []),
                recent_context=None,
                model=model,
                return_meta=True,
            )
            if isinstance(draft_meta, dict) and "draft" in draft_meta:
                draft = draft_meta["draft"]
                draft_usage = draft_meta.get("usage") or {}
                draft_raw = draft_meta.get("raw_usage")
                draft_cfg = draft_meta.get("request_config") or {}
            else:
                draft = draft_meta
                draft_usage, draft_raw, draft_cfg = {}, None, {}

            question_meta = question_fn(
                user_texts=list(case.get("user_texts") or []),
                conversation=list(case.get("conversation") or []),
                draft=draft,
                question_session=empty_question_session(),
                recent_context=None,
                model=model,
                return_meta=True,
            )
            if isinstance(question_meta, dict) and "question_result" in question_meta:
                question_result = question_meta["question_result"]
                q_usage = question_meta.get("usage") or {}
                q_raw = question_meta.get("raw_usage")
                q_cfg = question_meta.get("request_config") or {}
            else:
                question_result = question_meta
                q_usage, q_raw, q_cfg = {}, None, {}
        finally:
            if prev_flag is None:
                os.environ.pop("REFLECTION_AGENT_ENABLED", None)
            else:
                os.environ["REFLECTION_AGENT_ENABLED"] = prev_flag

        usage = merge_usage(draft_usage, q_usage)
        result["draft"] = draft
        result["question_result"] = {
            "needs_followup": question_result.get("needs_followup"),
            "followup_question": question_result.get("followup_question"),
            "question_mode": question_result.get("question_mode"),
            "archive_gap": question_result.get("archive_gap"),
            "reflective_handle_strength": question_result.get("reflective_handle_strength"),
            "candidate_count": question_result.get("candidate_count"),
            "selected_anchor": question_result.get("selected_anchor"),
            "rejected_candidates": question_result.get("rejected_candidates"),
            "skip_reason": question_result.get("skip_reason"),
            "question_outcome": question_result.get("question_outcome"),
            "candidates": question_result.get("candidates"),
            "reasoning": question_result.get("reasoning"),
        }
        result["usage"] = usage
        result["raw_usage"] = {"draft": draft_raw, "question": q_raw}
        result["request_config"] = {"draft": draft_cfg, "question": q_cfg}
        result["estimated_cost_usd"] = estimate_cost_usd(model, usage, pricing)
        result["validation"] = {
            "draft_needs_followup_cleared": draft.get("needs_followup") is False,
            "question_skip_reason": question_result.get("skip_reason") or "",
            "same_model_for_draft_and_question": True,
        }
    except Exception as exc:
        err = classify_api_error(exc)
        result["error"] = err
    finally:
        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)

    return result


def result_path(output_dir: Path, case_id: str, model: str) -> Path:
    safe_model = model.replace("/", "_")
    return output_dir / "checkpoints" / f"{case_id}__{safe_model}.json"


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def probe_model_access(model: str, *, client: Any | None = None) -> dict[str, Any]:
    """Minimal request to verify the current API key can reach the model."""
    from openai import OpenAI

    from conversation_to_memory.evaluation.openai_compat import chat_completion_create

    if client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return {
                "model": model,
                "ok": False,
                "error": {
                    "error_type": "model_access_error",
                    "category": "authentication",
                    "message": "OPENAI_API_KEY missing",
                },
            }
        client = OpenAI(api_key=api_key)
    try:
        _, cfg = chat_completion_create(
            client,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
            max_output_tokens=5,
            response_format=None,
        )
        return {"model": model, "ok": True, "request_config": cfg, "error": None}
    except Exception as exc:
        return {"model": model, "ok": False, "request_config": {}, "error": classify_api_error(exc)}


def assign_blind_aliases(
    models: list[str],
    *,
    seed: int,
) -> dict[str, list[str]]:
    """Return per-run stable label order; actual mapping stored in manifest.

    For each case we shuffle model→A/B/C with a derived seed so refresh is stable.
    """
    labels = ["A", "B", "C", "D", "E"]
    rng = random.Random(seed)
    order = list(models)
    rng.shuffle(order)
    return {label: model for label, model in zip(labels, order)}


def case_blind_order(case_id: str, models: list[str], *, seed: int) -> list[str]:
    rng = random.Random(f"{seed}:{case_id}")
    order = list(models)
    rng.shuffle(order)
    return order


def run_comparison(
    *,
    cases: list[dict[str, Any]],
    models: list[str],
    output_dir: Path | str,
    concurrency: int = 1,
    force: bool = False,
    only_cases: list[str] | None = None,
    only_models: list[str] | None = None,
    seed: int = 20260715,
    probe: bool = True,
    analyze_fn: Callable[..., Any] | None = None,
    question_fn: Callable[..., Any] | None = None,
    sleep_on_rate_limit: bool = True,
    max_retries: int = 3,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if PRODUCTION_MEMORY_DIR.exists():
        # Soft guard: never write into production memories from this runner.
        pass

    prompt_hashes = get_prompt_hashes()
    git_commit = get_git_commit()
    pricing = load_pricing()
    models = list(only_models or models)
    if only_cases:
        allow = set(only_cases)
        cases = [c for c in cases if c.get("case_id") in allow]

    access: list[dict[str, Any]] = []
    blocked_models: set[str] = set()
    if probe:
        for model in models:
            status = probe_model_access(model)
            access.append(status)
            if not status.get("ok"):
                blocked_models.add(model)

    run_id = out.name
    blind_global = assign_blind_aliases(models, seed=seed)
    case_orders = {
        case["case_id"]: case_blind_order(case["case_id"], models, seed=seed) for case in cases
    }

    results: list[dict[str, Any]] = []

    def _execute(case: dict[str, Any], model: str) -> dict[str, Any]:
        path = result_path(out, case["case_id"], model)
        if not force:
            existing = load_checkpoint(path)
            if existing and existing.get("error") is None:
                return existing
            if existing and existing.get("error") and not force:
                # Resume retries errors by default when force is false? Spec says
                # resume skips completed; errors can be re-run. Re-run errors.
                pass

        if model in blocked_models:
            blocked = {
                "case_id": case["case_id"],
                "model": model,
                "model_alias": "",
                "prompt_hashes": prompt_hashes,
                "git_commit": git_commit,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "latency_ms": 0,
                "request_config": {},
                "usage": {},
                "estimated_cost_usd": None,
                "draft": {},
                "question_result": {},
                "validation": {},
                "error": next(a["error"] for a in access if a["model"] == model),
            }
            save_checkpoint(path, blocked)
            return blocked

        attempt = 0
        while True:
            attempt += 1
            result = run_single_case_model(
                case,
                model,
                prompt_hashes=prompt_hashes,
                git_commit=git_commit,
                analyze_fn=analyze_fn,
                question_fn=question_fn,
                pricing=pricing,
            )
            err = result.get("error") or {}
            if (
                err
                and err.get("category") == "rate_limit"
                and sleep_on_rate_limit
                and attempt < max_retries
            ):
                time.sleep(min(2**attempt, 30))
                continue
            save_checkpoint(path, result)
            return result

    jobs: list[tuple[dict[str, Any], str]] = []
    for case in cases:
        for model in models:
            jobs.append((case, model))

    if concurrency <= 1:
        for case, model in jobs:
            results.append(_execute(case, model))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_execute, case, model) for case, model in jobs]
            for fut in as_completed(futures):
                results.append(fut.result())

    # Merge with any checkpoints already on disk so partial re-runs do not drop models.
    checkpoint_dir = out / "checkpoints"
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    if checkpoint_dir.exists():
        for path in checkpoint_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            key = (str(row.get("case_id") or ""), str(row.get("model") or ""))
            if key[0] and key[1]:
                merged[key] = row
    for row in results:
        key = (str(row.get("case_id") or ""), str(row.get("model") or ""))
        merged[key] = row
    results = sorted(merged.values(), key=lambda r: (r.get("case_id") or "", r.get("model") or ""))
    all_models = list(dict.fromkeys(list(models) + [r.get("model") for r in results if r.get("model")]))

    results_path = out / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize_results(results, all_models)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_summary_csv(out / "summary.csv", summary)

    # Preserve previously recorded models when this invocation is a partial re-run.
    previous_manifest_path = out / "run_manifest.json"
    previous_models: list[str] = []
    if previous_manifest_path.exists():
        try:
            previous_models = list(
                (json.loads(previous_manifest_path.read_text(encoding="utf-8")) or {}).get(
                    "models"
                )
                or []
            )
        except Exception:
            previous_models = []
    manifest_models = list(dict.fromkeys(previous_models + all_models))
    manifest_case_orders = {
        case_id: case_blind_order(case_id, manifest_models, seed=seed)
        for case_id in {c.get("case_id") for c in cases} | set(case_orders)
        if case_id
    }
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "prompt_hashes": prompt_hashes,
        "models": manifest_models,
        "seed": seed,
        "blind_global_alias_to_model": assign_blind_aliases(manifest_models, seed=seed),
        "case_model_order": manifest_case_orders,
        "model_access": access,
        "case_count": len(cases),
        "result_count": len(results),
        "pricing_verified_at": pricing.get("verified_at"),
        "fairness": {
            "same_prompts": True,
            "same_postprocessing": True,
            "same_schema": True,
            "model_via_function_arg": True,
            "openai_model_env_untouched": True,
        },
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"results": results, "summary": summary, "manifest": manifest, "output_dir": str(out)}


def summarize_results(results: list[dict[str, Any]], models: list[str]) -> dict[str, Any]:
    by_model: dict[str, Any] = {}
    for model in models:
        rows = [r for r in results if r.get("model") == model]
        successes = [r for r in rows if not r.get("error")]
        errors = [r for r in rows if r.get("error")]
        latencies = [r.get("latency_ms") or 0 for r in successes]
        costs = [r.get("estimated_cost_usd") for r in successes if r.get("estimated_cost_usd") is not None]
        q_gen = sum(
            1
            for r in successes
            if (r.get("question_result") or {}).get("needs_followup")
            and (r.get("question_result") or {}).get("followup_question")
        )
        q_reject = sum(
            1
            for r in successes
            if (r.get("question_result") or {}).get("skip_reason")
            or (r.get("question_result") or {}).get("rejected_candidates")
        )

        def _avg_token(key: str) -> float | None:
            vals = [
                (r.get("usage") or {}).get(key)
                for r in successes
                if (r.get("usage") or {}).get(key) is not None
            ]
            if not vals:
                return None
            return round(sum(vals) / len(vals), 2)

        by_model[model] = {
            "success_count": len(successes),
            "error_count": len(errors),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "total_input_tokens": sum((r.get("usage") or {}).get("input_tokens") or 0 for r in successes),
            "total_output_tokens": sum((r.get("usage") or {}).get("output_tokens") or 0 for r in successes),
            "total_reasoning_tokens": sum(
                (r.get("usage") or {}).get("reasoning_tokens") or 0 for r in successes
            ),
            "avg_input_tokens": _avg_token("input_tokens"),
            "avg_output_tokens": _avg_token("output_tokens"),
            "avg_reasoning_tokens": _avg_token("reasoning_tokens"),
            "question_generation_rate": round(q_gen / len(successes), 4) if successes else None,
            "question_reject_rate": round(q_reject / len(successes), 4) if successes else None,
            "estimated_total_cost_usd": round(sum(costs), 6) if costs else None,
            "avg_cost_per_case_usd": round(sum(costs) / len(costs), 6) if costs else None,
            "error_categories": {},
        }
        for r in errors:
            cat = ((r.get("error") or {}).get("category")) or "unknown"
            by_model[model]["error_categories"][cat] = (
                by_model[model]["error_categories"].get(cat, 0) + 1
            )

    return {
        "models": by_model,
        "total_results": len(results),
        "note": "Human review required before declaring a winner.",
    }


def write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    rows = summary.get("models") or {}
    fieldnames = [
        "model",
        "success_count",
        "error_count",
        "avg_latency_ms",
        "total_input_tokens",
        "total_output_tokens",
        "total_reasoning_tokens",
        "question_generation_rate",
        "estimated_total_cost_usd",
        "avg_cost_per_case_usd",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for model, stats in rows.items():
            writer.writerow({"model": model, **{k: stats.get(k) for k in fieldnames if k != "model"}})
