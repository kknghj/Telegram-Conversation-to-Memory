"""Tests for transcript replay / bulk memo upload mode."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
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


def test_parse_block_header_datetime_space_format():
    recorded_at, body = replay.parse_block_header_datetime(
        "2026 06 23 0754\n\n오늘 출근 일찍 해서 업무를 정리했다."
    )

    assert recorded_at == datetime(2026, 6, 23, 7, 54)
    assert body == "오늘 출근 일찍 해서 업무를 정리했다."


def test_parse_block_header_datetime_dash_format():
    recorded_at, body = replay.parse_block_header_datetime("2026-06-21\n오늘 배포했다.")

    assert recorded_at == datetime(2026, 6, 21, 0, 0)
    assert body == "오늘 배포했다."


def test_txt_replay_block_uses_memo_timestamp(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text(
        "2026 06 23 0754\n\n오늘 출근 일찍 해서 업무를 정리했다.\n\n---\n\n"
        "2026 06 24 2235\n\n식생활교육 업무 자동화 추진이 영 부진하다.",
        encoding="utf-8",
    )

    blocks = replay.parse_replay_file(path)

    assert len(blocks) == 2
    assert blocks[0].recorded_at == datetime(2026, 6, 23, 7, 54)
    assert blocks[0].conversation[0]["content"] == "오늘 출근 일찍 해서 업무를 정리했다."
    assert blocks[0].source_text.startswith("2026 06 23 0754")
    assert blocks[1].recorded_at == datetime(2026, 6, 24, 22, 35)


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


def test_format_interactive_review_screen_includes_source_and_summary():
    block = replay.ReplayBlock(
        index=1,
        source_text="오늘 자동 한글 연습장을 배포했다.",
        conversation=[{"role": "user", "content": "오늘 자동 한글 연습장을 배포했다."}],
    )
    screen = replay.format_interactive_review_screen(block, SAMPLE_DRAFT)

    assert "원문" in screen
    assert "오늘 자동 한글 연습장을 배포했다." in screen
    assert "요약" in screen
    assert SAMPLE_DRAFT["event_summary"] in screen
    assert "Memory Preview" in screen
    assert "[y] 저장" in screen
    assert "[n] 건너뛰기" in screen
    assert "[e] 종료" in screen


def test_prompt_review_choice_accepts_y_n_e():
    assert replay.prompt_review_choice(lambda: "y") == "save"
    assert replay.prompt_review_choice(lambda: "n") == "skip"
    assert replay.prompt_review_choice(lambda: "e") == "exit"


def test_interactive_review_y_saves(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("2026-06-21\n오늘 배포했다.", encoding="utf-8")
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    saved_payloads: list[dict] = []
    outputs: list[str] = []

    def fake_save(memory):
        saved_payloads.append(memory)
        return str(memories_dir / "saved.json")

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            with patch(
                "conversation_to_memory.bot.chat_service.storage.save",
                side_effect=fake_save,
            ):
                result = replay.run_replay(
                    source,
                    mode="interactive-review",
                    memories_dir=memories_dir,
                    input_fn=lambda: "y",
                    output_fn=outputs.append,
                )

    assert result.results[0].saved is True
    assert saved_payloads
    assert saved_payloads[0]["metadata"]["source"] == "transcript_replay"
    assert any("원문" in output for output in outputs)


def test_interactive_review_n_skips(tmp_path):
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
            with patch("conversation_to_memory.bot.chat_service.storage.save") as save_mock:
                result = replay.run_replay(
                    source,
                    mode="interactive-review",
                    memories_dir=memories_dir,
                    input_fn=lambda: "n",
                    output_fn=lambda _: None,
                )

    assert result.results[0].saved is False
    assert result.results[0].skipped is True
    save_mock.assert_not_called()


def test_interactive_review_e_aborts_remaining_blocks(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    source = tmp_path / "notes.txt"
    source.write_text("첫 기록\n\n---\n\n둘째 기록", encoding="utf-8")
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    with patch("conversation_to_memory.replay.db.DEFAULT_DB_PATH", db_path):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_draft_copy,
        ):
            with patch("conversation_to_memory.bot.chat_service.storage.save") as save_mock:
                result = replay.run_replay(
                    source,
                    mode="interactive-review",
                    memories_dir=memories_dir,
                    input_fn=lambda: "e",
                    output_fn=lambda _: None,
                )

    assert result.aborted is True
    assert len(result.results) == 1
    assert result.parsed_blocks == 2
    assert result.results[0].skipped is True
    save_mock.assert_not_called()


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
    assert metadata["recorded_at"] == "2026-06-21T00:00:00"
    assert saved_payloads[0]["timestamp"] == "2026-06-21T00:00:00"
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
