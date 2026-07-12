"""Apply interpretation_failures failure_type CHECK migration, then optionally sync.

Requires one of:
  - SUPABASE_DB_URL / DATABASE_URL (postgres connection string), or
  - manual run of supabase/migrations/010_*.sql in Supabase SQL Editor
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    PROJECT_ROOT
    / "supabase"
    / "migrations"
    / "010_extend_interpretation_failure_types_question_quality.sql"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _db_url() -> str:
    return (
        os.getenv("SUPABASE_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
        or os.getenv("POSTGRES_URL", "").strip()
    )


def apply_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    db_url = _db_url()
    if not db_url:
        raise SystemExit(
            "DB URL이 없습니다. Supabase SQL Editor에서 아래 SQL을 실행한 뒤 "
            "sync를 다시 돌려주세요.\n\n"
            f"--- {MIGRATION.name} ---\n{sql}\n"
            "또는 .env에 SUPABASE_DB_URL(또는 DATABASE_URL)을 넣고 이 스크립트를 다시 실행하세요."
        )

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "psycopg가 필요합니다: pip install psycopg[binary]\n"
            "또는 SQL Editor에서 마이그레이션을 실행하세요."
        ) from exc

    with psycopg.connect(db_url) as conn:
        conn.execute(sql)
        conn.commit()
    print(f"Applied migration: {MIGRATION.name}")


def sync_failures() -> int:
    from app.interpretation_failures_supabase import (
        is_supabase_configured,
        sync_jsonl_to_supabase,
    )

    if not is_supabase_configured():
        print("Set SUPABASE_URL and SUPABASE_SECRET_KEY.", file=sys.stderr)
        return 1
    path = PROJECT_ROOT / "data" / "evaluation" / "interpretation_failures.jsonl"
    result = sync_jsonl_to_supabase(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sync",
        action="store_true",
        help="마이그레이션 적용 후 interpretation_failures sync까지 실행",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="SQL만 출력 (SQL Editor 복붙용)",
    )
    args = parser.parse_args()

    if args.print_sql:
        print(MIGRATION.read_text(encoding="utf-8"))
        return 0

    apply_migration()
    if args.sync:
        return sync_failures()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
