"""One-off analysis script for MVP reflection evaluation."""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEM_DIR = PROJECT_ROOT / "data" / "memories"


def main() -> None:
    files = sorted(MEM_DIR.glob("*.json"))
    print(f"Total memories: {len(files)}")

    all_data = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
            d["_id"] = f.stem
            all_data.append(d)

    dates = [d["_id"][:10] for d in all_data]
    print(f"Date range: {min(dates)} ~ {max(dates)}")
    span = (
        datetime.strptime(max(dates), "%Y-%m-%d")
        - datetime.strptime(min(dates), "%Y-%m-%d")
    ).days + 1
    print(f"Days span: {span} days")

    day_counts = Counter(dates)
    print("\n=== Records per day ===")
    for day in sorted(day_counts):
        print(f"  {day}: {day_counts[day]}")

    schema = Counter(d.get("schema_version", "missing") for d in all_data)
    print("\n=== schema_version ===")
    for k, v in sorted(schema.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v} ({v / len(all_data) * 100:.1f}%)")

    mt = Counter(d.get("memory_type", "missing") for d in all_data)
    print("\n=== memory_type ===")
    for k, v in mt.most_common():
        print(f"  {k}: {v}")

    emotions = Counter()
    for d in all_data:
        for e in d.get("user_emotions", []) or []:
            if isinstance(e, dict):
                emotions[e.get("emotion", e.get("label", str(e)))] += 1
            else:
                emotions[str(e)] += 1
        if d.get("emotion") and not d.get("user_emotions"):
            emotions[d["emotion"]] += 1
    print("\n=== user_emotions (top 15) ===")
    for k, v in emotions.most_common(15):
        print(f"  {k}: {v}")

    themes = Counter()
    for d in all_data:
        for t in d.get("emerging_themes", []) or []:
            themes[t.lower().strip()] += 1
    print("\n=== emerging_themes (top 25) ===")
    for k, v in themes.most_common(25):
        print(f"  {k}: {v}")

    people_keywords = [
        "팀장", "상사", "동료", "부장", "과장", "대표", "엄마", "아빠",
        "친구", "남편", "아내", "선배", "후배", "멘토", "채", "지수",
    ]
    people = Counter()
    for d in all_data:
        text = " ".join(
            m.get("content", "")
            for m in d.get("conversation", [])
            if m.get("role") == "user"
        )
        for p in people_keywords:
            if p in text:
                people[p] += 1
    print("\n=== People mentions in conversation ===")
    for k, v in people.most_common():
        if v > 0:
            print(f"  {k}: {v}")

    project_kw = [
        "프로젝트", "회의", "발표", "보고", "과제", "업무", "일", "회사",
        "직장", "팀", "개발", "코딩", "앱", "봇", "텔레그램", "메모",
        "기록", "독서", "모임", "책", "면접", "전화", "통화",
    ]
    project = Counter()
    for d in all_data:
        text = " ".join(
            m.get("content", "")
            for m in d.get("conversation", [])
            if m.get("role") == "user"
        )
        for p in project_kw:
            if p in text:
                project[p] += 1
    print("\n=== Project/topic keywords in conversation ===")
    for k, v in project.most_common(25):
        if v > 0:
            print(f"  {k}: {v}")

    has_conv = sum(
        1
        for d in all_data
        if d.get("conversation")
        and any(
            m.get("role") == "user" and m.get("content")
            for m in d["conversation"]
        )
    )
    print("\n=== Primary evidence ===")
    print(f"  Has user conversation: {has_conv}/{len(all_data)}")
    print(f"  Missing conversation: {len(all_data) - has_conv}")

    rv = Counter(d.get("reflection_value", "missing") for d in all_data)
    print("\n=== reflection_value ===")
    for k, v in rv.most_common():
        print(f"  {k}: {v}")

    ir = Counter(d.get("interpretation_risk", "missing") for d in all_data)
    print("\n=== interpretation_risk ===")
    for k, v in ir.most_common():
        print(f"  {k}: {v}")

    print("\n=== Full user quotes index ===")
    for d in all_data:
        uid = d["_id"]
        sv = d.get("schema_version", "?")
        mt = d.get("memory_type", "?")
        print(f"\n--- {uid} (sv={sv}, type={mt}) ---")
        for m in d.get("conversation", []):
            if m.get("role") == "user" and m.get("content"):
                content = m["content"].replace("\n", " ")[:200]
                print(f"  > {content}")


if __name__ == "__main__":
    main()
