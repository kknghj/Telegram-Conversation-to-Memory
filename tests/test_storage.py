"""Storage tests."""

import json
import tempfile
from pathlib import Path

from conversation_to_memory.storage.local_json import LocalJsonStorage


def test_save_creates_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalJsonStorage(directory=Path(tmp))
        memory = {
            "topic": "테스트",
            "event_summary": "요약",
            "user_emotions": ["기쁨"],
            "emotion_evidence": ["좋았다"],
            "people": ["Alice"],
            "projects": [],
            "tags": ["test"],
            "conversation": [{"role": "user", "content": "hello"}],
            "memory_candidate": "후보",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "approved": True,
        }
        filepath = storage.save(memory)

        assert Path(filepath).exists()
        with open(filepath, encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["topic"] == "테스트"
        assert saved["approved"] is True
        assert "timestamp" in saved
