"""과거 메모의 open_questions 휴리스틱 백필.

사용법:
    python scripts/backfill_open_questions.py                # dry-run: 후보 목록만 출력
    python scripts/backfill_open_questions.py --apply        # 백업 후 실제 반영
    python scripts/backfill_open_questions.py --apply --exclude 2026-06-18_194719:0
        (특정 메모의 n번째 후보 제외. "memory_id:index" 형식, 쉼표로 복수 지정)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conversation_to_memory.migration.open_questions import (
    backfill_open_questions,
    extract_open_question_candidates,
    find_noise_entries,
)

DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"
SOURCE_TAG = f"backfill_{datetime.now().strftime('%Y-%m-%d')}_user_approved"


def collect_candidates(memories_dir: Path) -> list[dict]:
    """메모별 신규 후보·노이즈 목록 수집."""
    rows: list[dict] = []
    for filepath in sorted(memories_dir.glob("*.json")):
        with open(filepath, encoding="utf-8") as f:
            memory = json.load(f)
        existing = memory.get("open_questions") or []
        candidates = [
            q for q in extract_open_question_candidates(memory) if q not in existing
        ]
        noise = find_noise_entries(memory)
        if candidates or noise:
            rows.append(
                {
                    "memory_id": filepath.stem,
                    "filepath": filepath,
                    "memory": memory,
                    "topic": memory.get("topic", ""),
                    "candidates": candidates,
                    "noise": noise,
                }
            )
    return rows


def apply_exclusions(rows: list[dict], exclusions: set[tuple[str, int]]) -> None:
    for row in rows:
        row["candidates"] = [
            q
            for idx, q in enumerate(row["candidates"])
            if (row["memory_id"], idx) not in exclusions
        ]


def run(memories_dir: Path, *, apply: bool, exclusions: set[tuple[str, int]]) -> None:
    rows = collect_candidates(memories_dir)
    apply_exclusions(rows, exclusions)
    rows = [r for r in rows if r["candidates"] or r["noise"]]

    total_candidates = sum(len(r["candidates"]) for r in rows)
    total_noise = sum(len(r["noise"]) for r in rows)
    print(f"대상 메모 {len(rows)}건 / 신규 후보 {total_candidates}건 / 노이즈 제거 {total_noise}건")
    print()

    for row in rows:
        print(f"[{row['memory_id']}] {row['topic']}")
        for idx, question in enumerate(row["candidates"]):
            print(f"  + ({idx}) {question}")
        for question in row["noise"]:
            print(f"  - (노이즈 제거) {question}")
    print()

    if not apply:
        print("dry-run 모드입니다. 반영하려면 --apply 를 붙이세요.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = memories_dir.parent / f"memories_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for filepath in memories_dir.glob("*.json"):
        shutil.copy2(filepath, backup_dir / filepath.name)
    print(f"백업 완료: {backup_dir}")

    changed = 0
    for row in rows:
        memory = row["memory"]
        did_change, _ = backfill_open_questions(
            memory,
            row["candidates"],
            source=SOURCE_TAG,
            remove=row["noise"],
        )
        if did_change:
            with open(row["filepath"], "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
            changed += 1
    print(f"반영 완료: {changed}건 수정 (source={SOURCE_TAG})")


def parse_exclusions(raw: str) -> set[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    for token in filter(None, (t.strip() for t in raw.split(","))):
        memory_id, _, index = token.rpartition(":")
        result.add((memory_id, int(index)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="open_questions 백필")
    parser.add_argument("--memories-dir", type=Path, default=DEFAULT_MEMORIES_DIR)
    parser.add_argument("--apply", action="store_true", help="실제 파일에 반영")
    parser.add_argument(
        "--exclude",
        default="",
        help='제외할 후보: "memory_id:index" 쉼표 구분',
    )
    args = parser.parse_args()
    run(
        args.memories_dir,
        apply=args.apply,
        exclusions=parse_exclusions(args.exclude),
    )


if __name__ == "__main__":
    main()
