# Transcript Replay / Bulk Memo Upload Mode

## 목적

Transcript replay mode는 휴대폰 메모장이나 JSON 파일에 모아 둔 기록을 나중에 한 번에 넣어, 기존 `dev_chat` / Telegram과 같은 **요약 → 사용자 승인 → 저장** 흐름으로 final memory JSON을 만드는 기능입니다.

이 기능은 별도 기억 생성기가 아니라 파일 입력을 기존 session, memory extraction, review, final save 흐름에 주입하는 어댑터입니다.

## TXT 입력 예시

```txt
2026 06 23 0754

오늘 출근 일찍 해서 업무상 처리할 일 정리하고 남는 시간 동안 자동화에 집중하고 싶다.

---

2026-06-22

식생활교육 추첨제 개선 계획을 다시 생각했다.
```

블록 첫 줄에 메모 작성 시각을 적을 수 있습니다.

- 공백 구분: `YYYY MM DD HHmm` (예: `2026 06 23 0754` → 2026-06-23 07:54)
- 대시 구분: `YYYY-MM-DD` 또는 `YYYY-MM-DD HHmm`

날짜 줄은 기억 본문에서 분리되어 LLM 분석에 넘기고, 저장 시에는 아래처럼 반영됩니다.

- final JSON `timestamp` / `metadata.recorded_at`: 메모에 적은 시각
- final 파일명: `data/memories/YYYY-MM-DD_HHmmSS.json`

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

## Interactive Review

각 메모 블록마다 원문, 요약, Memory Preview를 터미널에 보여주고 저장 여부를 확인합니다. Telegram의 **요약 → 승인 → 저장** 흐름과 동일한 철학을 replay에서도 유지합니다.

```powershell
python -m app.dev_chat --replay data/replay/notes.txt --interactive-review
```

블록마다 다음 화면이 표시됩니다.

```
=================================

원문

오늘 자동 한글 연습장을 배포했다.

---------------------------------

요약

...

---------------------------------

Memory Preview

...

---------------------------------

저장하시겠습니까?

[y] 저장
[n] 건너뛰기
[e] 종료

>
```

| 입력 | 동작 |
|------|------|
| `y` | 기존 final save 로직으로 저장 |
| `n` | 해당 메모만 건너뛰고 다음 블록으로 진행 |
| `e` | replay 즉시 종료. 이후 블록은 처리하지 않음 |

## Save Final

모든 메모를 검토 없이 즉시 저장합니다.

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
    "recorded_at": "2026-06-23T07:54:00",
    "source_text": "원문 블록"
  }
}
```

## 오염 방지 규칙

- `--save-final` 또는 `--interactive-review`에서 `y`를 선택하지 않으면 final memory 저장소를 변경하지 않습니다.
- 기본 실행은 dry-run입니다.
- `replay_hash`가 이미 저장된 final memory는 기본적으로 skip합니다.
- 같은 내용을 다시 final 저장해야 할 때만 `--force`를 사용합니다.
- txt 원문은 `metadata.source_text`에 보존됩니다.

## 후속 질문

Replay는 배치 처리용이므로 후속 질문 단계를 건너뛰고 바로 검토로 진행합니다. 실시간 후속 질문은 `dev_chat` 대화 모드나 Telegram 봇에서만 사용합니다.

## 로컬호스트를 자주 켜기 어려운 주의 워크플로우

1. 휴대폰 메모장에 하루 기록을 적습니다.
2. 기록 사이에 `---`를 넣어 구분합니다.
3. 집에 돌아와 `data/replay/notes.txt`로 저장합니다.
4. dry-run으로 먼저 미리봅니다.
5. `--interactive-review`로 필요한 기록만 승인 저장합니다.
6. 또는 `--save-final`로 일괄 저장합니다.

이 흐름은 기록 누락을 줄이되, 무비판적 대량 저장이 아니라 사용자 승인 기반 저장을 돕기 위한 장치입니다.
