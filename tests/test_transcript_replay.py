"""Tests for transcript replay / bulk memo upload mode."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app import database as db
from conversation_to_memory import replay


SAMPLE_DRAFT = {
    "topic": "배포 기록",
    "event_summary": "자동 한글 연습장 생성기를 배포했고 댓글 반응이 기뻤다.",
    "user_emotions": ["기쁨"],
    "emotion_evidence": ["기분이 좋았다"],
    "people": [],
    "projects": ["자동 한글 연습장"],
    "tags": ["배포", "피드백"],
    "memory_candidate": "자동 한글 연습장 생성기 배포 후 도움이 됐다는 댓글을 보고 기뻤다.",
    "needs_followup": False,
    "followup_question": "",
    "interpretation_risk": "low",
    "unsupported_inferences": [],
}


def _draft_copy(*args, **kwargs):
    return dict(SAMPLE_DRAFT)


def test_txt_file_is_split_into_blocks():
    text = "첫 기록\n\n---\n\n둘째 기록\n\n===\n\n셋째 기록"

    assert replay.parse_txt_blocks(text) == ["첫 기록", "둘째 기록", "셋째 기록"]


def test_txt_parser_ignores_empty_blocks():
    text = "\n---\n\n첫 기록\n\n===\n\n"

    assert replay.parse_txt_blocks(text) == ["첫 기록"]


def test_json_messages_array_is_read(tmp_path):
    path = tmp_path / "conversation.json"
    path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "오늘 배포했다."},
                {"role": "assistant", "content": "무엇이 기억에 남았나요?"},
                {"role": "user", "content": "도움됐다는 댓글이다."},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    blocks = replay.parse_replay_file(path)

    assert len(blocks) == 1
    assert blocks[0].source_text == "오늘 배포했다.\n도움됐다는 댓글이다."
    assert len(blocks[0].conversation) == 3


def test_json_sessions_array_is_read(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "session_id": "2026-06-21_release",
                    "messages": [
                        {"role": "user", "content": "오늘 배포했다."},
                        {"role": "user", "content": "댓글 반응이 좋았다."},
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    blocks = replay.parse_replay_file(path)

    assert len(blocks) == 1
    assert blocks[0].session_id == "2026-06-21_release"
    assert blocks[0].source_text == "오늘 배포했다.\n댓글 반응이 좋았다."


def test_dry_run_does_not_write_final_memory(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("2026-06-21\n오늘 배포했다.", encoding="utf-8")
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            result = replay.run_replay(source, memories_dir=memories_dir)

    assert result.mode == "dry-run"
    assert result.results[0].saved is False
    assert list(memories_dir.glob("*.json")) == []


def test_save_draft_writes_draft_output(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("2026-06-21\n오늘 배포했다.", encoding="utf-8")

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            result = replay.run_replay(
                source,
                mode="save-draft",
                draft_output_dir=tmp_path / "drafts",
            )

    output = Path(result.results[0].output_path)
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["approved"] is False
    assert payload["metadata"]["source"] == "transcript_replay"


def test_save_final_adds_transcript_replay_metadata(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("2026-06-21\n오늘 배포했다.", encoding="utf-8")
    saved_payloads: list[dict] = []

    def fake_save(memory):
        saved_payloads.append(memory)
        return str(tmp_path / "saved.json")

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            with patch("conversation_to_memory.bot.chat_service.storage.save", side_effect=fake_save):
                result = replay.run_replay(source, mode="save-final", memories_dir=tmp_path / "memories")

    assert result.results[0].saved is True
    metadata = saved_payloads[0]["metadata"]
    assert metadata["source"] == "transcript_replay"
    assert metadata["replay_mode"] is True
    assert metadata["source_text"].startswith("2026-06-21")


def test_duplicate_replay_hash_is_skipped_by_default(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("오늘 배포했다.", encoding="utf-8")
    block = replay.parse_replay_file(source)[0]
    replay_hash = replay.compute_replay_hash(source, block)
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    (memories_dir / "existing.json").write_text(
        json.dumps({"metadata": {"replay_hash": replay_hash}}, ensure_ascii=False),
        encoding="utf-8",
    )

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch("conversation_to_memory.bot.chat_service.storage.save") as save_mock:
            result = replay.run_replay(source, mode="save-final", memories_dir=memories_dir)

    assert result.results[0].skipped is True
    save_mock.assert_not_called()


def test_force_allows_duplicate_final_save(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("오늘 배포했다.", encoding="utf-8")
    block = replay.parse_replay_file(source)[0]
    replay_hash = replay.compute_replay_hash(source, block)
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    (memories_dir / "existing.json").write_text(
        json.dumps({"metadata": {"replay_hash": replay_hash}}, ensure_ascii=False),
        encoding="utf-8",
    )

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            with patch(
                "conversation_to_memory.bot.chat_service.storage.save",
                return_value=str(tmp_path / "saved.json"),
            ) as save_mock:
                result = replay.run_replay(
                    source,
                    mode="save-final",
                    force=True,
                    memories_dir=memories_dir,
                )

    assert result.results[0].saved is True
    save_mock.assert_called_once()
