"""Local JSON memories → Supabase migration service."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from conversation_to_memory.storage.local_json import DEFAULT_MEMORIES_DIR
from conversation_to_memory.storage.supabase import (
    SupabaseStorageError,
    _build_row,
    get_memories_table_name,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "migration" / "latest_migration_report.md"
PREVIEW_LIMIT = 5
PAGE_SIZE = 1000


class MigrationStatus(str, Enum):
    INSERTED = "inserted"
    SKIPPED = "skipped"
    INVALID = "invalid"
    FAILED = "failed"
    WOULD_INSERT = "would_insert"


@dataclass
class FileMigrationResult:
    path: Path
    status: MigrationStatus
    reason: str = ""
    topic: str = ""
    timestamp: str = ""
    tags: list[str] = field(default_factory=list)
    source_hash: str = ""


@dataclass
class MigrationSummary:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    would_insert: int = 0
    elapsed_seconds: float = 0.0
    dry_run: bool = True
    log_path: Path | None = None
    report_path: Path | None = None
    results: list[FileMigrationResult] = field(default_factory=list)

    @property
    def invalid_results(self) -> list[FileMigrationResult]:
        return [r for r in self.results if r.status == MigrationStatus.INVALID]

    @property
    def skipped_results(self) -> list[FileMigrationResult]:
        return [r for r in self.results if r.status == MigrationStatus.SKIPPED]

    @property
    def failed_results(self) -> list[FileMigrationResult]:
        return [r for r in self.results if r.status == MigrationStatus.FAILED]


@dataclass
class DuplicateIndex:
    source_hashes: set[str] = field(default_factory=set)
    memory_ids: set[str] = field(default_factory=set)
    composite_keys: set[tuple[str, str, str]] = field(default_factory=set)


def calculate_source_hash(memory: dict) -> str:
    """raw_memory 전체의 SHA256 해시."""
    canonical = json.dumps(memory, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_memory(memory: dict) -> tuple[bool, str]:
    """Migration 대상 memory 검증."""
    if memory.get("approved") is not True:
        return False, "approved is not true"

    timestamp = memory.get("timestamp")
    if not timestamp or not str(timestamp).strip():
        return False, "timestamp is missing"

    topic = memory.get("topic")
    if not topic or not str(topic).strip():
        return False, "topic is missing"

    candidate = memory.get("memory_candidate")
    if not candidate or not str(candidate).strip():
        return False, "memory_candidate is missing"

    return True, ""


def build_row(memory: dict, *, source_file: str, source_hash: str) -> dict[str, Any]:
    """Supabase insert row with migration tracking fields."""
    row = _build_row(memory)
    row["source"] = "local_json_migration"
    row["source_hash"] = source_hash
    row["source_file"] = source_file
    row["migrated_at"] = datetime.now(timezone.utc).isoformat()
    return row


def check_duplicate(
    memory: dict,
    source_hash: str,
    index: DuplicateIndex,
    *,
    session_hashes: set[str] | None = None,
    session_composites: set[tuple[str, str, str]] | None = None,
) -> tuple[bool, str]:
    """중복 판단. (is_duplicate, reason)"""
    if source_hash in index.source_hashes:
        return True, "source_hash exists in Supabase"

    if session_hashes is not None and source_hash in session_hashes:
        return True, "source_hash duplicate in batch"

    memory_id = memory.get("id")
    if memory_id is not None:
        memory_id_str = str(memory_id).strip()
        if memory_id_str and memory_id_str in index.memory_ids:
            return True, "memory id exists in Supabase"

    composite = _composite_key(memory)
    if composite is not None:
        if composite in index.composite_keys:
            return True, "timestamp+topic+memory_candidate exists in Supabase"
        if session_composites is not None and composite in session_composites:
            return True, "timestamp+topic+memory_candidate duplicate in batch"

    return False, ""


def _composite_key(memory: dict) -> tuple[str, str, str] | None:
    timestamp = memory.get("timestamp")
    topic = memory.get("topic")
    candidate = memory.get("memory_candidate")
    if not timestamp or not topic or not candidate:
        return None
    return (str(timestamp).strip(), str(topic).strip(), str(candidate).strip())


def _extract_date_label(timestamp: str) -> str:
    if not timestamp:
        return ""
    return str(timestamp)[:10]


class MigrationRepository:
    """Supabase read/write for migration (independent from MemoryStorage)."""

    def __init__(self, client: Any, table_name: str):
        self._client = client
        self._table_name = table_name

    def fetch_duplicate_index(self) -> DuplicateIndex:
        index = DuplicateIndex()
        offset = 0

        while True:
            response = (
                self._client.table(self._table_name)
                .select("source_hash, timestamp, topic, memory_candidate, raw_memory")
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                break

            for row in rows:
                source_hash = row.get("source_hash")
                if source_hash:
                    index.source_hashes.add(str(source_hash))

                raw = row.get("raw_memory") or {}
                if isinstance(raw, dict):
                    raw_id = raw.get("id")
                    if raw_id is not None and str(raw_id).strip():
                        index.memory_ids.add(str(raw_id).strip())

                composite = (
                    str(row.get("timestamp") or "").strip(),
                    str(row.get("topic") or "").strip(),
                    str(row.get("memory_candidate") or "").strip(),
                )
                if all(composite):
                    index.composite_keys.add(composite)

            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return index

    def insert(self, row: dict[str, Any]) -> str:
        response = self._client.table(self._table_name).insert(row).execute()
        data = response.data or []
        if not data:
            raise SupabaseStorageError("Insert succeeded but returned no row.")
        row_id = data[0].get("id")
        if not row_id:
            raise SupabaseStorageError("Insert succeeded but row id is missing.")
        return str(row_id)


class MigrationService:
    """Local JSON → Supabase migration orchestrator."""

    def __init__(
        self,
        source_dir: Path | None = None,
        *,
        dry_run: bool = True,
        client: Any | None = None,
        table_name: str | None = None,
        log_dir: Path | None = None,
        report_path: Path | None = None,
        preview_limit: int = PREVIEW_LIMIT,
    ):
        self.source_dir = source_dir or DEFAULT_MEMORIES_DIR
        self.dry_run = dry_run
        self.table_name = table_name or get_memories_table_name()
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.report_path = report_path or DEFAULT_REPORT_PATH
        self.preview_limit = preview_limit
        self._client = client
        self._summary = MigrationSummary(dry_run=dry_run)

    def discover_files(self) -> list[Path]:
        if not self.source_dir.exists():
            return []
        return sorted(self.source_dir.glob("*.json"))

    def _get_repository(self) -> MigrationRepository:
        if self._client is None:
            url = os.getenv("SUPABASE_URL", "").strip()
            secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
            if not url or not secret_key:
                raise SupabaseStorageError(
                    "SUPABASE_URL and SUPABASE_SECRET_KEY are required for migration."
                )
            from supabase import create_client

            self._client = create_client(url, secret_key)
        return MigrationRepository(self._client, self.table_name)

    def _setup_logger(self) -> tuple[logging.Logger, Path]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"migration_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
        logger = logging.getLogger(f"migration.{log_path.stem}")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger, log_path

    def _load_memory(self, filepath: Path) -> tuple[dict | None, str]:
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f), ""
        except json.JSONDecodeError as exc:
            return None, f"JSON parse error: {exc}"
        except OSError as exc:
            return None, f"File read error: {exc}"

    def _record(
        self,
        logger: logging.Logger,
        filepath: Path,
        status: MigrationStatus,
        *,
        reason: str = "",
        memory: dict | None = None,
        source_hash: str = "",
    ) -> FileMigrationResult:
        topic = str((memory or {}).get("topic") or "")
        timestamp = str((memory or {}).get("timestamp") or "")
        tags = list((memory or {}).get("tags") or [])

        result = FileMigrationResult(
            path=filepath,
            status=status,
            reason=reason,
            topic=topic,
            timestamp=timestamp,
            tags=tags,
            source_hash=source_hash,
        )
        self._summary.results.append(result)

        logger.info(
            "%s | %s | %s | %s",
            status.value.upper(),
            filepath,
            reason or "-",
            source_hash or "-",
        )
        return result

    def migrate(self) -> MigrationSummary:
        started = datetime.now()
        logger, log_path = self._setup_logger()
        self._summary = MigrationSummary(dry_run=self.dry_run, log_path=log_path)

        files = self.discover_files()
        self._summary.total = len(files)

        repo = self._get_repository()
        try:
            duplicate_index = repo.fetch_duplicate_index()
        except Exception as exc:
            message = str(exc)
            if "source_hash" in message and "does not exist" in message:
                raise SupabaseStorageError(
                    "memories.source_hash column not found. "
                    "Run supabase/migrations/006_add_migration_tracking_columns.sql first."
                ) from exc
            raise

        session_hashes: set[str] = set()
        session_composites: set[tuple[str, str, str]] = set()
        preview_count = 0

        for index, filepath in enumerate(files, start=1):
            memory, load_error = self._load_memory(filepath)
            if memory is None:
                self._record(
                    logger,
                    filepath,
                    MigrationStatus.INVALID,
                    reason=load_error,
                )
                continue

            valid, validation_error = validate_memory(memory)
            if not valid:
                self._record(
                    logger,
                    filepath,
                    MigrationStatus.INVALID,
                    reason=validation_error,
                    memory=memory,
                )
                continue

            self._summary.valid += 1
            source_hash = calculate_source_hash(memory)

            is_dup, dup_reason = check_duplicate(
                memory,
                source_hash,
                duplicate_index,
                session_hashes=session_hashes,
                session_composites=session_composites,
            )
            if is_dup:
                self._record(
                    logger,
                    filepath,
                    MigrationStatus.SKIPPED,
                    reason=dup_reason,
                    memory=memory,
                    source_hash=source_hash,
                )
                self._summary.skipped += 1
                if not self.dry_run:
                    print(f"[{index}/{len(files)}]")
                    print("Skipped duplicate")
                    print(_extract_date_label(str(memory.get("timestamp", ""))))
                    print(memory.get("topic", ""))
                    print()
                continue

            row = build_row(
                memory,
                source_file=filepath.name,
                source_hash=source_hash,
            )

            if self.dry_run:
                self._record(
                    logger,
                    filepath,
                    MigrationStatus.WOULD_INSERT,
                    memory=memory,
                    source_hash=source_hash,
                )
                self._summary.would_insert += 1
                if preview_count < self.preview_limit:
                    print("[INSERT]")
                    print(_extract_date_label(str(memory.get("timestamp", ""))))
                    print(memory.get("topic", ""))
                    print("tags")
                    for tag in memory.get("tags") or []:
                        print(tag)
                    print()
                    preview_count += 1
                continue

            try:
                repo.insert(row)
                session_hashes.add(source_hash)
                composite = _composite_key(memory)
                if composite is not None:
                    session_composites.add(composite)
                duplicate_index.source_hashes.add(source_hash)
                if composite is not None:
                    duplicate_index.composite_keys.add(composite)

                self._record(
                    logger,
                    filepath,
                    MigrationStatus.INSERTED,
                    memory=memory,
                    source_hash=source_hash,
                )
                self._summary.inserted += 1
                print(f"[{index}/{len(files)}]")
                print("Inserted")
                print(_extract_date_label(str(memory.get("timestamp", ""))))
                print(memory.get("topic", ""))
                print()
            except Exception as exc:
                self._record(
                    logger,
                    filepath,
                    MigrationStatus.FAILED,
                    reason=str(exc),
                    memory=memory,
                    source_hash=source_hash,
                )
                self._summary.failed += 1
                print(f"[{index}/{len(files)}]")
                print("Failed")
                print(_extract_date_label(str(memory.get("timestamp", ""))))
                print(memory.get("topic", ""))
                print(str(exc))
                print()

        self._summary.invalid = len(self._summary.invalid_results)
        self._summary.elapsed_seconds = (datetime.now() - started).total_seconds()
        self._summary.report_path = self.report_path
        generate_migration_report(self._summary)
        return self._summary

    def summary(self) -> MigrationSummary:
        return self._summary


def generate_migration_report(summary: MigrationSummary) -> str:
    """reports/migration/latest_migration_report.md 생성."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed = f"{summary.elapsed_seconds:.1f}s"
    mode = "Dry Run" if summary.dry_run else "Apply"

    lines = [
        "# Migration Report",
        "",
        f"**Mode:** {mode}",
        f"**Date:** {now}",
        f"**Elapsed Time:** {elapsed}",
        "",
        "## Summary",
        "",
        f"- **Total Files:** {summary.total}",
        f"- **Valid:** {summary.valid}",
        f"- **Invalid:** {summary.invalid}",
    ]

    if summary.dry_run:
        lines.append(f"- **Will Insert:** {summary.would_insert}")
    else:
        lines.append(f"- **Inserted:** {summary.inserted}")

    lines.extend([
        f"- **Skipped:** {summary.skipped}",
        f"- **Failed:** {summary.failed}",
        "",
    ])

    if summary.log_path:
        lines.extend([
            f"**Log:** `{summary.log_path}`",
            "",
        ])

    def _results_table(title: str, results: list[FileMigrationResult]) -> None:
        lines.extend([f"## {title}", ""])
        if not results:
            lines.extend(["_None_", ""])
            return
        lines.extend([
            "| File | Reason |",
            "|------|--------|",
        ])
        for item in results:
            lines.append(f"| `{item.path.name}` | {item.reason or '-'} |")
        lines.append("")

    _results_table("Invalid", summary.invalid_results)
    _results_table("Skipped", summary.skipped_results)
    _results_table("Failed", summary.failed_results)

    content = "\n".join(lines)
    report_path = summary.report_path or DEFAULT_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    return content


def print_dry_run_summary(summary: MigrationSummary) -> None:
    print(f"Found: {summary.total}")
    print(f"Valid: {summary.valid}")
    print(f"Invalid: {summary.invalid}")
    print(f"Will Insert: {summary.would_insert}")
    print(f"Skipped: {summary.skipped}")


def print_apply_summary(summary: MigrationSummary) -> None:
    print("Migration Complete")
    print()
    print("Inserted")
    print(summary.inserted)
    print()
    print("Skipped")
    print(summary.skipped)
    print()
    print("Invalid")
    print(summary.invalid)
    print()
    print("Failed")
    print(summary.failed)
