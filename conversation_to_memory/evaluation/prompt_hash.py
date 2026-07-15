"""Stable hashes for runtime prompts used in model comparison."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MEMORY_PROMPT = "memory_archive_system_prompt.txt"
QUESTION_PROMPT = "question_generation_prompt.txt"
LEGACY_DIR = PROMPTS_DIR / "legacy"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_prompt_hashes() -> dict[str, str]:
    return {
        "memory": sha256_file(PROMPTS_DIR / MEMORY_PROMPT),
        "question": sha256_file(PROMPTS_DIR / QUESTION_PROMPT),
    }


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def legacy_prompt_paths() -> list[Path]:
    if not LEGACY_DIR.exists():
        return []
    return sorted(p for p in LEGACY_DIR.iterdir() if p.is_file() and p.suffix == ".txt")
