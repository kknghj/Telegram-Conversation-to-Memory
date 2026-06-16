"""schema_version 마이그레이션 테스트."""

import json
import tempfile
from pathlib import Path

from conversation_to_memory.migration.schema import backfill_schema_version
from scripts.migrate_schema_version import migrate_schema_version


def _legacy_memory() -> dict:
    return {
        "topic": "구스키마",
        "emotion": "혼란",
        "summary": "요약",
        "memory_candidate": "후보",
        "conversation": [{"role": "user", "content": "원문 A"}],
    }


def _v2_without_version() -> dict:
    return {
        "topic": "신스키마",
        "event_summary": "요약",
        "user_emotions": ["불안"],
        "interpretation_risk": "low",
        "memory_candidate": "후보",
        "conversation": [{"role": "user", "content": "원문 B"}],
    }


class TestBackfillSchemaVersion:
    def test_legacy_gets_version_1_and_status(self):
        memory = _legacy_memory()
        migrated, version = backfill_schema_version(memory)
        assert migrated is True
        assert version == 1
        assert memory["schema_version"] == 1
        assert memory["migration_status"] == "backfilled"

    def test_v2_structured_gets_version_2(self):
        memory = _v2_without_version()
        migrated, version = backfill_schema_version(memory)
        assert migrated is True
        assert version == 2
        assert memory["migration_status"] == "backfilled"

    def test_already_versioned_is_skipped(self):
        memory = {**_legacy_memory(), "schema_version": 1}
        migrated, version = backfill_schema_version(memory)
        assert migrated is False
        assert version == 1
        assert "migration_status" not in memory


class TestMigrateSchemaVersionScript:
    def test_migrated_count_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memories"
            mem_dir.mkdir()
            legacy_path = mem_dir / "2026-06-09_test.json"
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(_legacy_memory(), f, ensure_ascii=False, indent=2)

            result = migrate_schema_version(mem_dir)
            assert result["migrated_count"] == 1
            assert result["skipped_count"] == 0
            assert result["migrated_ids"] == ["2026-06-09_test"]
            backup_dir = Path(result["backup_dir"])
            assert (backup_dir / legacy_path.name).exists()

            with open(legacy_path, encoding="utf-8") as f:
                migrated = json.load(f)
            assert migrated["schema_version"] == 1
            assert migrated["migration_status"] == "backfilled"

    def test_skipped_count_for_existing_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memories"
            mem_dir.mkdir()
            path = mem_dir / "2026-06-10_test.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump({**_v2_without_version(), "schema_version": 2}, f)

            result = migrate_schema_version(mem_dir)
            assert result["migrated_count"] == 0
            assert result["skipped_count"] == 1
            assert result["skipped_ids"] == ["2026-06-10_test"]

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memories"
            mem_dir.mkdir()
            path = mem_dir / "2026-06-09_test.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_legacy_memory(), f)

            result = migrate_schema_version(mem_dir, dry_run=True)
            assert result["dry_run"] is True
            assert result["backup_dir"] is None

            with open(path, encoding="utf-8") as f:
                unchanged = json.load(f)
            assert "schema_version" not in unchanged
