"""Load verified model pricing; never invent prices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[2] / "config" / "model_pricing.json"


def load_pricing(path: Path | str | None = None) -> dict[str, Any]:
    pricing_path = Path(path) if path else DEFAULT_PRICING_PATH
    if not pricing_path.exists():
        return {"verified_at": None, "models": {}}
    return json.loads(pricing_path.read_text(encoding="utf-8"))


def estimate_cost_usd(model: str, usage: dict[str, Any], pricing: dict[str, Any] | None = None) -> float | None:
    pricing = pricing or load_pricing()
    model_pricing = (pricing.get("models") or {}).get(model)
    if not model_pricing:
        return None
    input_rate = model_pricing.get("input_per_million")
    output_rate = model_pricing.get("output_per_million")
    cached_rate = model_pricing.get("cached_input_per_million")
    if input_rate is None or output_rate is None:
        return None

    input_tokens = usage.get("input_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0
    cached_tokens = usage.get("cached_input_tokens") or 0
    # Prefer splitting cached vs uncached when both present.
    billable_input = max(0, int(input_tokens) - int(cached_tokens))
    cost = (billable_input / 1_000_000.0) * float(input_rate)
    cost += (int(output_tokens) / 1_000_000.0) * float(output_rate)
    if cached_rate is not None and cached_tokens:
        cost += (int(cached_tokens) / 1_000_000.0) * float(cached_rate)
    return round(cost, 8)
