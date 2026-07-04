"""Tests for local JSON → Supabase migration service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conversation_to_memory.migration.migration_service import (
    DuplicateIndex,
    MigrationRepository,
    MigrationService,
    MigrationStatus,
    build_row,
    calculate_source_hash,
    check_duplicate,
    generate_migration_report,
    validate_memory,
)


def _valid_memory(**overrides) -> dict:
    base = {
        "timestamp": "2026-06-11T17:56:09.123456",
        "topic": "부서 내 관계",
        "event_summary": "요약",
        "user_emotions": ["답답함"],
        "emotion_evidence": ["원문"],
        "people": [],
        "projects": [],
        "tags": ["업무", "관계"],
        "memory_candidate": "후보 본문",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "conversation": [{"role": "user", "content": "hello"}],
        "approved": True,
        "schema_version": 2,
    }
    base.update(overrides)
    return base


def _write_json(directory: Path, name: str, memory: dict) -> Path:
    path = directory / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    return path


def _mock_repo_client(existing_rows: list[dict] | None = None):
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table

    select_chain = MagicMock()
    table.select.return_value = select_chain
    select_chain.range.return_value.execute.return_value = MagicMock(data=existing_rows or [])

    insert_chain = MagicMock()
    table.insert.return_value = insert_chain
    insert_chain.execute.return_value = MagicMock(data=[{"id": "new-row-id"}])

    return client, table


def test_discover_files_finds_all_json(tmp_path):
    _write_json(tmp_path, "a.json", _valid_memory())
    _write_json(tmp_path, "b.json", _valid_memory(topic="두번째"))
    (tmp_path / "note.txt").write_text("skip", encoding="utf-8")

    service = MigrationService(source_dir=tmp_path, client=MagicMock())
    files = service.discover_files()

    assert len(files) == 2
    assert files[0].name == "a.json"
    assert files[1].name == "b.json"


def test_validate_memory_accepts_valid():
    ok, reason = validate_memory(_valid_memory())
    assert ok is True
    assert reason == ""


@pytest.mark.parametrize(
    "overrides, expected_reason",
    [
        ({"approved": False}, "approved is not true"),
        ({"timestamp": ""}, "timestamp is missing"),
        ({"topic": ""}, "topic is missing"),
        ({"memory_candidate": ""}, "memory_candidate is missing"),
    ],
)
def test_validate_memory_rejects_invalid(overrides, expected_reason):
    ok, reason = validate_memory(_valid_memory(**overrides))
    assert ok is False
    assert reason == expected_reason


def test_check_duplicate_by_source_hash():
    memory = _valid_memory()
    source_hash = calculate_source_hash(memory)
    index = DuplicateIndex(source_hashes={source_hash})

    is_dup, reason = check_duplicate(memory, source_hash, index)
    assert is_dup is True
    assert "source_hash" in reason


def test_check_duplicate_by_composite_key():
    memory = _valid_memory()
    source_hash = calculate_source_hash(memory)
    composite = (
        memory["timestamp"],
        memory["topic"],
        memory["memory_candidate"],
    )
    index = DuplicateIndex(composite_keys={composite})

    is_dup, reason = check_duplicate(memory, source_hash, index)
    assert is_dup is True
    assert "timestamp+topic+memory_candidate" in reason


def test_check_duplicate_by_memory_id():
    memory = _valid_memory(id="mem-001")
    source_hash = calculate_source_hash(memory)
    index = DuplicateIndex(memory_ids={"mem-001"})

    is_dup, reason = check_duplicate(memory, source_hash, index)
    assert is_dup is True
    assert "memory id" in reason


def test_build_row_includes_migration_fields():
    memory = _valid_memory()
    source_hash = calculate_source_hash(memory)
    row = build_row(memory, source_file="2026-06-11_175609.json", source_hash=source_hash)

    assert row["source_hash"] == source_hash
    assert row["source_file"] == "2026-06-11_175609.json"
    assert row["source"] == "local_json_migration"
    assert row["migrated_at"]
    assert row["raw_memory"] == memory


def test_dry_run_does_not_insert(tmp_path):
    _write_json(tmp_path, "one.json", _valid_memory())
    client, table = _mock_repo_client([])

    service = MigrationService(source_dir=tmp_path, dry_run=True, client=client)
    summary = service.migrate()

    assert summary.would_insert == 1
    assert summary.inserted == 0
    table.insert.assert_not_called()


def test_dry_run_summary_counts(tmp_path):
    _write_json(tmp_path, "valid.json", _valid_memory())
    _write_json(tmp_path, "invalid.json", _valid_memory(approved=False))
    client, _ = _mock_repo_client([])

    summary = MigrationService(source_dir=tmp_path, dry_run=True, client=client).migrate()

    assert summary.total == 2
    assert summary.valid == 1
    assert summary.invalid == 1
    assert summary.would_insert == 1


def test_apply_inserts_valid_memories(tmp_path):
    _write_json(tmp_path, "one.json", _valid_memory())
    client, table = _mock_repo_client([])

    summary = MigrationService(source_dir=tmp_path, dry_run=False, client=client).migrate()

    assert summary.inserted == 1
    table.insert.assert_called_once()
    inserted = table.insert.call_args[0][0]
    assert inserted["topic"] == "부서 내 관계"
    assert inserted["source_file"] == "one.json"
    assert inserted["source_hash"]


def test_apply_skips_duplicate(tmp_path):
    memory = _valid_memory()
    source_hash = calculate_source_hash(memory)
    _write_json(tmp_path, "one.json", memory)
    client, table = _mock_repo_client([{"source_hash": source_hash}])

    summary = MigrationService(source_dir=tmp_path, dry_run=False, client=client).migrate()

    assert summary.skipped == 1
    assert summary.inserted == 0
    table.insert.assert_not_called()


def test_invalid_json_does_not_stop_migration(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write_json(tmp_path, "good.json", _valid_memory())
    client, table = _mock_repo_client([])

    summary = MigrationService(source_dir=tmp_path, dry_run=False, client=client).migrate()

    assert summary.invalid == 1
    assert summary.inserted == 1
    table.insert.assert_called_once()


def test_insert_failure_continues(tmp_path):
    _write_json(tmp_path, "fail.json", _valid_memory(topic="실패"))
    _write_json(tmp_path, "ok.json", _valid_memory(topic="성공"))
    client, table = _mock_repo_client([])

    def insert_side_effect(row):
        chain = MagicMock()
        if row["topic"] == "실패":
            chain.execute.side_effect = RuntimeError("network down")
        else:
            chain.execute.return_value = MagicMock(data=[{"id": "ok-id"}])
        return chain

    table.insert.side_effect = insert_side_effect

    summary = MigrationService(source_dir=tmp_path, dry_run=False, client=client).migrate()

    assert summary.failed == 1
    assert summary.inserted == 1
    assert table.insert.call_count == 2


def test_migration_creates_log_file(tmp_path):
    log_dir = tmp_path / "logs"
    _write_json(tmp_path, "one.json", _valid_memory())
    client, _ = _mock_repo_client([])

    summary = MigrationService(
        source_dir=tmp_path,
        dry_run=True,
        client=client,
        log_dir=log_dir,
        report_path=tmp_path / "report.md",
    ).migrate()

    assert summary.log_path is not None
    assert summary.log_path.exists()
    content = summary.log_path.read_text(encoding="utf-8")
    assert "WOULD_INSERT" in content
    assert "one.json" in content


def test_migration_generates_markdown_report(tmp_path):
    report_path = tmp_path / "reports" / "latest_migration_report.md"
    _write_json(tmp_path, "one.json", _valid_memory())
    _write_json(tmp_path, "bad.json", _valid_memory(approved=False))
    client, _ = _mock_repo_client([])

    summary = MigrationService(
        source_dir=tmp_path,
        dry_run=True,
        client=client,
        log_dir=tmp_path / "logs",
        report_path=report_path,
    ).migrate()

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "# Migration Report" in content
    assert "Total Files" in content
    assert "Invalid" in content
    assert "bad.json" in content
    assert summary.report_path == report_path


def test_generate_migration_report_apply_mode(tmp_path):
    from conversation_to_memory.migration.migration_service import FileMigrationResult, MigrationSummary

    summary = MigrationSummary(
        total=2,
        valid=2,
        invalid=0,
        inserted=1,
        skipped=1,
        failed=0,
        dry_run=False,
        results=[
            FileMigrationResult(
                path=Path("skip.json"),
                status=MigrationStatus.SKIPPED,
                reason="source_hash exists",
            )
        ],
    )
    report_path = tmp_path / "report.md"
    summary.report_path = report_path
    generate_migration_report(summary)

    content = report_path.read_text(encoding="utf-8")
    assert "**Inserted:** 1" in content
    assert "Skipped" in content


def test_repository_fetch_duplicate_index_paginates():
    page1 = [{"source_hash": f"hash-{i}"} for i in range(1000)]
    page2 = [{"source_hash": "hash-last"}]

    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    select_chain = MagicMock()

    table.select.return_value = select_chain
    select_chain.range.return_value.execute.side_effect = [
        MagicMock(data=page1),
        MagicMock(data=page2),
    ]

    index = MigrationRepository(client, "memories").fetch_duplicate_index()
    assert len(index.source_hashes) == 1001


def test_calculate_source_hash_is_stable():
    memory = _valid_memory()
    assert calculate_source_hash(memory) == calculate_source_hash(memory.copy())
