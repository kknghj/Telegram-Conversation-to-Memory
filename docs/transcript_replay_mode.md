# Transcript Replay / Bulk Memo Upload Mode

## 목적

Transcript replay mode는 휴대폰 메모장이나 JSON 파일에 모아 둔 기록을 나중에 한 번에 넣어, 기존 `dev_chat` 흐름과 같은 방식으로 draft 또는 final memory JSON을 만드는 기능입니다.

이 기능은 별도 기억 생성기가 아니라 파일 입력을 기존 session, draft persistence, memory extraction, final save 흐름에 주입하는 어댑터입니다.

## TXT 입력 예시

```txt
2026-06-21
오늘 자동 한글 연습장 생성기를 배포했다.
댓글 반응이 조금 있어서 하루 종일 은은하게 기분이 좋았다.
도움이 된다는 피드백이 돈보다 더 기뻤다.

---

2026-06-22
식생활교육 추첨제 개선 계획을 다시 생각했다.
참관인 구성을 어떻게 해야 할지 막막했다.
```

`---` 또는 `===` 한 줄을 구분자로 사용합니다. 빈 블록은 무시되며, 각 블록은 하나의 사용자 기록 단위로 처리됩니다.

## JSON 입력 예시

messages array:

```json
[
  {
    "role": "user",
    "content": "오늘 자동 한글 연습장을 배포했다."
  },
  {
    "role": "assistant",
    "content": "가장 기억에 남는 반응은 무엇이었나요?"
  },
  {
    "role": "user",
    "content": "도움됐다는 댓글을 봤을 때였다."
  }
]
```

sessions array:

```json
[
  {
    "session_id": "2026-06-21_sumukan_release",
    "messages": [
      {
        "role": "user",
        "content": "오늘 자동 한글 연습장을 배포했다."
      },
      {
        "role": "user",
        "content": "댓글 반응이 좋아서 기분이 좋았다."
      }
    ]
  }
]
```

## Dry Run

기본값은 dry-run입니다. final memory 저장소를 변경하지 않고, 파싱된 블록 수, 블록별 draft 요약, 저장될 JSON preview, validation 결과를 출력합니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --dry-run
```

`--dry-run`을 생략해도 같은 동작입니다.

## Save Draft

draft까지만 생성하고 final memory로 확정하지 않습니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --save-draft
```

저장 경로:

```text
data/replay_outputs/drafts/YYYY-MM-DD_001_draft.json
```

## Save Final

기존 final memory 저장 로직을 사용해 `data/memories/`에 저장합니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --save-final
```

replay로 저장된 기억에는 다음 metadata가 포함됩니다.

```json
{
  "metadata": {
    "source": "transcript_replay",
    "source_file": "data/replay/notes.txt",
    "replay_mode": true,
    "replay_hash": "sha256...",
    "source_text": "원문 블록"
  }
}
```

## 오염 방지 규칙

- `--save-final`을 명시하지 않으면 final memory 저장소를 변경하지 않습니다.
- 기본 실행은 dry-run입니다.
- `replay_hash`가 이미 저장된 final memory는 기본적으로 skip합니다.
- 같은 내용을 다시 final 저장해야 할 때만 `--force`를 사용합니다.
- txt 원문은 `metadata.source_text`에 보존됩니다.

## 후속 질문 처리

기본값은 실시간 답변을 요구하지 않는 모드입니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --followup-mode none
```

후속 질문을 생성하되 답변을 기다리지 않고 draft metadata에 남기려면 다음을 사용합니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --followup-mode generate-only
```

## 로컬호스트를 자주 켜기 어려운 주의 워크플로우

1. 휴대폰 메모장에 하루 기록을 적습니다.
2. 기록 사이에 `---`를 넣어 구분합니다.
3. 집에 돌아와 `data/replay/notes.txt`로 저장합니다.
4. dry-run으로 먼저 확인합니다.
5. 이상 없으면 `--save-draft`로 검토용 초안을 만들거나 `--save-final`로 확정 저장합니다.

이 흐름은 기록 누락을 줄이되, 무비판적 대량 저장이 아니라 검토 가능한 draft/final memory 생성을 돕기 위한 장치입니다.
