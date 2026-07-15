"""Static HTML comparison report (no server required)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _esc(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))
    return html.escape(str(value))


def _badge(label: str, kind: str = "neutral") -> str:
    return f'<span class="badge badge-{_esc(kind)}">{_esc(label)}</span>'


def collect_badges(result: dict[str, Any]) -> list[str]:
    badges: list[str] = []
    if result.get("error"):
        badges.append(_badge("실행 오류", "error"))
        return badges
    draft = result.get("draft") or {}
    q = result.get("question_result") or {}
    if not (draft.get("projects") or []):
        badges.append(_badge("프로젝트 태그 없음", "warn"))
    if q.get("needs_followup") and q.get("followup_question"):
        badges.append(_badge("후속 질문 생성", "ok"))
    elif q.get("skip_reason"):
        badges.append(_badge("후속 질문 생략", "muted"))
    rejected = q.get("rejected_candidates") or []
    if rejected and not q.get("followup_question"):
        badges.append(_badge("질문 후보 전부 거절", "warn"))
    risk = draft.get("interpretation_risk")
    if risk in ("medium", "high"):
        badges.append(_badge(f"해석 위험 {risk}", "warn" if risk == "medium" else "error"))
    if draft.get("unsupported_inferences"):
        badges.append(_badge("unsupported inference 존재", "warn"))
    return badges


def field_diff_keys(results_by_label: dict[str, dict[str, Any]]) -> set[str]:
    keys = (
        "event_summary",
        "model_interpretation",
        "projects",
        "tags",
        "user_emotions",
        "memory_candidate",
        "interpretation_risk",
        "followup_question",
        "question_mode",
        "skip_reason",
    )
    differing: set[str] = set()
    labels = list(results_by_label.keys())
    if len(labels) < 2:
        return differing
    for key in keys:
        values = []
        for label in labels:
            r = results_by_label[label]
            draft = r.get("draft") or {}
            q = r.get("question_result") or {}
            if key in draft:
                values.append(json.dumps(draft.get(key), ensure_ascii=False, sort_keys=True))
            else:
                values.append(json.dumps(q.get(key), ensure_ascii=False, sort_keys=True))
        if len(set(values)) > 1:
            differing.add(key)
    return differing


def render_model_column(
    label: str,
    result: dict[str, Any],
    *,
    differing: set[str],
) -> str:
    draft = result.get("draft") or {}
    q = result.get("question_result") or {}
    err = result.get("error")
    badges = "".join(collect_badges(result))

    def row(title: str, key: str, value: Any, section: str = "draft") -> str:
        cls = "field"
        if key in differing:
            cls += " field-diff"
        return (
            f'<div class="{cls}" data-field="{_esc(key)}">'
            f"<h4>{_esc(title)}</h4>"
            f"<pre>{_esc(value)}</pre></div>"
        )

    if err:
        body = (
            f'<div class="error-box"><strong>오류</strong>'
            f"<pre>{_esc(err)}</pre></div>"
        )
    else:
        body = "".join(
            [
                row("요약", "event_summary", draft.get("event_summary")),
                row("감정", "user_emotions", draft.get("user_emotions")),
                row("감정 근거", "emotion_evidence", draft.get("emotion_evidence")),
                row("프로젝트", "projects", draft.get("projects")),
                row("태그", "tags", draft.get("tags")),
                row("기억 후보", "memory_candidate", draft.get("memory_candidate")),
                row("해석", "model_interpretation", draft.get("model_interpretation")),
                row("해석 위험", "interpretation_risk", draft.get("interpretation_risk")),
                row("unsupported", "unsupported_inferences", draft.get("unsupported_inferences")),
                row("후속 질문", "followup_question", q.get("followup_question"), "question"),
                row("질문 모드", "question_mode", q.get("question_mode"), "question"),
                row("생략 사유", "skip_reason", q.get("skip_reason"), "question"),
                row("거절 후보", "rejected_candidates", q.get("rejected_candidates"), "question"),
                row("선택된 앵커", "selected_anchor", q.get("selected_anchor"), "question"),
            ]
        )

    return f"""
    <section class="model-col" data-label="{_esc(label)}">
      <header>
        <h3>모델 {_esc(label)} <span class="real-model hidden" data-model="{_esc(result.get('model'))}"></span></h3>
        <div class="badges">{badges}</div>
        <div class="meta muted">latency: {_esc(result.get('latency_ms'))} ms · cost: {_esc(result.get('estimated_cost_usd'))}</div>
      </header>
      {body}
      <div class="scores" data-label="{_esc(label)}">
        <label>원문 충실도 <input type="number" min="1" max="5" data-score="fidelity" /></label>
        <label>해석 유용성 <input type="number" min="1" max="5" data-score="interpretation" /></label>
        <label>질문 유용성 <input type="number" min="1" max="5" data-score="question" placeholder="없음=비움" /></label>
      </div>
    </section>
    """


def build_case_payload(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for row in results:
        by_case.setdefault(row["case_id"], {})[row["model"]] = row

    case_orders = manifest.get("case_model_order") or {}
    payload = []
    for case in cases:
        cid = case["case_id"]
        order = case_orders.get(cid) or list((by_case.get(cid) or {}).keys())
        labels = ["A", "B", "C", "D", "E"]
        label_map = {}
        labeled_results = {}
        for idx, model in enumerate(order):
            label = labels[idx]
            label_map[label] = model
            row = (by_case.get(cid) or {}).get(model)
            if row:
                labeled_results[label] = row
        payload.append(
            {
                "case": case,
                "label_map": label_map,
                "order": order,
                "results_by_label": labeled_results,
            }
        )
    return payload


def generate_comparison_html(
    *,
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    manifest: dict[str, Any],
    output_path: Path | str,
) -> Path:
    payload = build_case_payload(cases, results, manifest)
    out = Path(output_path)
    run_id = manifest.get("run_id") or out.parent.name
    # Escape < so user text cannot break out of the surrounding <script> tag.
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")

    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Model Comparison — {_esc(run_id)}</title>
<style>
:root {{
  --bg: #f3efe6;
  --ink: #1c1a17;
  --muted: #6b645a;
  --panel: #fffdf8;
  --line: #d9d0c2;
  --accent: #0f5c4c;
  --warn: #9a5b00;
  --error: #8b1e1e;
  --diff: #fff3bf;
  --ok: #1f6b3a;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "IBM Plex Sans KR", "Pretendard", "Noto Sans KR", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(1200px 600px at 10% -10%, #e7f2ee 0%, transparent 55%),
    linear-gradient(180deg, #efe8da, var(--bg));
}}
header.app {{
  position: sticky; top: 0; z-index: 5;
  backdrop-filter: blur(8px);
  background: rgba(243,239,230,.92);
  border-bottom: 1px solid var(--line);
  padding: 12px 20px;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}}
header.app h1 {{ font-size: 1.05rem; margin: 0 12px 0 0; }}
button, select {{
  border: 1px solid var(--line); background: var(--panel); color: var(--ink);
  padding: 8px 12px; border-radius: 8px; cursor: pointer;
}}
button.primary {{ background: var(--accent); color: white; border-color: var(--accent); }}
main {{ padding: 20px; max-width: 1400px; margin: 0 auto; }}
.case-meta {{ margin-bottom: 12px; }}
.source {{
  background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
  padding: 14px 16px; margin-bottom: 14px;
}}
.source pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; }}
.grid {{
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}}
@media (max-width: 1000px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.model-col {{
  background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
  padding: 12px; min-height: 200px;
}}
.model-col h3 {{ margin: 0 0 8px; }}
.field {{ border-top: 1px dashed var(--line); padding: 8px 0; }}
.field h4 {{ margin: 0 0 4px; font-size: .85rem; color: var(--muted); }}
.field pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-size: .92rem; }}
.field-diff {{ background: var(--diff); margin: 0 -8px; padding: 8px; border-radius: 8px; }}
.badge {{
  display: inline-block; font-size: .75rem; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--line); margin: 0 4px 4px 0;
}}
.badge-error {{ background: #f8e3e3; color: var(--error); }}
.badge-warn {{ background: #fff1d6; color: var(--warn); }}
.badge-ok {{ background: #e5f6ea; color: var(--ok); }}
.badge-muted {{ background: #eee; color: var(--muted); }}
.muted {{ color: var(--muted); font-size: .85rem; }}
.hidden {{ display: none !important; }}
.review {{
  margin-top: 16px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 14px;
}}
.review label {{ display: block; margin: 6px 0; }}
.scores label {{ display: block; margin: 4px 0; font-size: .85rem; }}
.scores input {{ width: 64px; }}
details.prod {{ margin-top: 10px; }}
.error-box {{ background: #f8e3e3; border-radius: 8px; padding: 8px; }}
.view-projects .field:not([data-field="projects"]):not([data-field="tags"]) {{ display: none; }}
.view-questions .field:not([data-field="followup_question"]):not([data-field="question_mode"]):not([data-field="skip_reason"]):not([data-field="rejected_candidates"]) {{ display: none; }}
</style>
</head>
<body>
<header class="app">
  <h1>모델 비교 평가 <span class="muted">{_esc(run_id)}</span></h1>
  <button id="prevBtn">이전 사례</button>
  <button id="nextBtn">다음 사례</button>
  <button id="unreviewedBtn">미평가 사례로 이동</button>
  <button id="revealBtn">모델명 공개</button>
  <button id="exportJsonBtn" class="primary">평가 JSON 내보내기</button>
  <button id="exportCsvBtn">평가 CSV 내보내기</button>
  <select id="filterSelect">
    <option value="all">전체</option>
    <option value="errors">오류 사례</option>
    <option value="cancelled">cancelled draft</option>
    <option value="short">짧은 기록</option>
    <option value="long">긴 기록</option>
    <option value="reviewed">평가 완료</option>
    <option value="unreviewed">미평가</option>
  </select>
  <select id="viewSelect">
    <option value="all">전체 필드</option>
    <option value="projects">프로젝트/태그만</option>
    <option value="questions">질문 결과만</option>
  </select>
</header>
<main>
  <div id="caseRoot"></div>
</main>
<script>
const RUN_ID = {json.dumps(run_id)};
const DATA = {data_json};
const STORAGE_KEY = "model_comparison_reviews:" + RUN_ID;
let index = 0;
let reveal = false;
let reviews = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{{}}");

function saveReviews() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
}}

function filteredIndexes() {{
  const mode = document.getElementById("filterSelect").value;
  const out = [];
  DATA.forEach((item, i) => {{
    const c = item.case;
    const results = Object.values(item.results_by_label || {{}});
    const hasError = results.some(r => r.error);
    const reviewed = !!reviews[c.case_id]?.best;
    const len = (c.categories && c.categories.length_bucket) || "";
    if (mode === "errors" && !hasError) return;
    if (mode === "cancelled" && c.status !== "cancelled") return;
    if (mode === "short" && len !== "short") return;
    if (mode === "long" && len !== "long") return;
    if (mode === "reviewed" && !reviewed) return;
    if (mode === "unreviewed" && reviewed) return;
    out.push(i);
  }});
  return out.length ? out : DATA.map((_, i) => i);
}}

function esc(s) {{
  return String(s ?? "").replace(/[&<>"']/g, ch => ({{
    "&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"
  }})[ch]);
}}

function render() {{
  const idxs = filteredIndexes();
  if (!idxs.includes(index)) index = idxs[0] || 0;
  const item = DATA[index];
  const c = item.case;
  const rev = reviews[c.case_id] || {{}};
  const labels = Object.keys(item.results_by_label);
  const differing = new Set();
  const keys = ["event_summary","model_interpretation","projects","tags","user_emotions","memory_candidate","interpretation_risk","followup_question","question_mode","skip_reason"];
  keys.forEach(k => {{
    const vals = labels.map(l => {{
      const r = item.results_by_label[l];
      const draft = r.draft || {{}};
      const q = r.question_result || {{}};
      return JSON.stringify(draft[k] ?? q[k] ?? null);
    }});
    if (new Set(vals).size > 1) differing.add(k);
  }});

  const cols = labels.map(label => {{
    const r = item.results_by_label[label];
    const draft = r.draft || {{}};
    const q = r.question_result || {{}};
    const err = r.error;
    const modelName = reveal ? (` · ${{esc(r.model)}}`) : "";
    const fields = err ? `<div class="error-box"><pre>${{esc(JSON.stringify(err, null, 2))}}</pre></div>` : [
      ["요약","event_summary", draft.event_summary],
      ["감정","user_emotions", draft.user_emotions],
      ["감정 근거","emotion_evidence", draft.emotion_evidence],
      ["프로젝트","projects", draft.projects],
      ["태그","tags", draft.tags],
      ["기억 후보","memory_candidate", draft.memory_candidate],
      ["해석","model_interpretation", draft.model_interpretation],
      ["해석 위험","interpretation_risk", draft.interpretation_risk],
      ["unsupported","unsupported_inferences", draft.unsupported_inferences],
      ["후속 질문","followup_question", q.followup_question],
      ["질문 모드","question_mode", q.question_mode],
      ["생략 사유","skip_reason", q.skip_reason],
      ["거절 후보","rejected_candidates", q.rejected_candidates],
      ["선택된 앵커","selected_anchor", q.selected_anchor],
    ].map(([title,key,val]) => {{
      const diff = differing.has(key) ? " field-diff" : "";
      return `<div class="field${{diff}}" data-field="${{key}}"><h4>${{title}}</h4><pre>${{esc(typeof val === "string" ? val : JSON.stringify(val, null, 2))}}</pre></div>`;
    }}).join("");
    const scores = rev.scores && rev.scores[label] || {{}};
    return `<section class="model-col" data-label="${{label}}">
      <header><h3>모델 ${{label}}${{modelName}}</h3>
      <div class="meta muted">latency: ${{esc(r.latency_ms)}} ms · cost: ${{esc(r.estimated_cost_usd)}}</div></header>
      ${{fields}}
      <div class="scores">
        <label>원문 충실도 <input type="number" min="1" max="5" data-label="${{label}}" data-score="fidelity" value="${{scores.fidelity ?? ""}}" /></label>
        <label>해석 유용성 <input type="number" min="1" max="5" data-label="${{label}}" data-score="interpretation" value="${{scores.interpretation ?? ""}}" /></label>
        <label>후속 질문 유용성 <input type="number" min="1" max="5" data-label="${{label}}" data-score="question" value="${{scores.question ?? ""}}" /></label>
      </div>
    </section>`;
  }}).join("");

  const prod = c.production_summary || {{}};
  document.getElementById("caseRoot").innerHTML = `
    <div class="case-meta">
      <strong>${{esc(c.case_id)}}</strong>
      <span class="muted"> · ${{esc(c.status)}} · ${{esc((c.categories||{{}}).length_bucket)}} · ${{esc((c.categories||{{}}).record_type)}}</span>
      <span class="muted"> (${{index+1}} / ${{DATA.length}})</span>
    </div>
    <section class="source">
      <h2>원문</h2>
      <h3>user_texts</h3>
      <pre>${{esc((c.user_texts||[]).join("\\n"))}}</pre>
      <h3>conversation</h3>
      <pre>${{esc(JSON.stringify(c.conversation || [], null, 2))}}</pre>
      <details class="prod"><summary>당시 저장 결과 (공정 비교 대상 아님)</summary>
        <pre>${{esc(JSON.stringify(prod, null, 2))}}</pre>
      </details>
    </section>
    <div class="grid" id="modelGrid">${{cols}}</div>
    <section class="review">
      <h2>평가</h2>
      <label>가장 좋은 결과
        <select id="bestSelect">
          <option value="">선택</option>
          ${{labels.map(l => `<option value="${{l}}" ${{rev.best===l?"selected":""}}>모델 ${{l}}</option>`).join("")}}
          <option value="tie" ${{rev.best==="tie"?"selected":""}}>비슷함</option>
          <option value="all_bad" ${{rev.best==="all_bad"?"selected":""}}>모두 부적절</option>
        </select>
      </label>
      <label>프로젝트 분류 정확성
        <select id="projectAccuracy">
          <option value="">선택</option>
          <option value="correct" ${{rev.project_accuracy==="correct"?"selected":""}}>맞음</option>
          <option value="partial" ${{rev.project_accuracy==="partial"?"selected":""}}>일부 맞음</option>
          <option value="wrong" ${{rev.project_accuracy==="wrong"?"selected":""}}>틀림</option>
        </select>
      </label>
      <label>과잉 해석
        <select id="overInterp">
          <option value="">선택</option>
          <option value="yes" ${{rev.over_interpretation==="yes"?"selected":""}}>있음</option>
          <option value="no" ${{rev.over_interpretation==="no"?"selected":""}}>없음</option>
        </select>
      </label>
      <label>이미 답한 내용 재질문
        <select id="reask">
          <option value="">선택</option>
          <option value="yes" ${{rev.answered_again==="yes"?"selected":""}}>있음</option>
          <option value="no" ${{rev.answered_again==="no"?"selected":""}}>없음</option>
        </select>
      </label>
      <label>메모<br/><textarea id="memo" rows="3" style="width:100%">${{esc(rev.memo||"")}}</textarea></label>
    </section>
  `;

  const view = document.getElementById("viewSelect").value;
  const grid = document.getElementById("modelGrid");
  grid.classList.toggle("view-projects", view === "projects");
  grid.classList.toggle("view-questions", view === "questions");

  function persist() {{
    const scores = {{}};
    document.querySelectorAll(".scores input").forEach(inp => {{
      const label = inp.dataset.label;
      scores[label] = scores[label] || {{}};
      const v = inp.value;
      scores[label][inp.dataset.score] = v === "" ? null : Number(v);
    }});
    reviews[c.case_id] = {{
      case_id: c.case_id,
      best: document.getElementById("bestSelect").value || null,
      project_accuracy: document.getElementById("projectAccuracy").value || null,
      over_interpretation: document.getElementById("overInterp").value || null,
      answered_again: document.getElementById("reask").value || null,
      memo: document.getElementById("memo").value || "",
      scores,
      label_map: reveal ? item.label_map : undefined,
      revealed: reveal,
    }};
    saveReviews();
  }}
  document.querySelectorAll(".review select, .review textarea, .scores input").forEach(el => {{
    el.addEventListener("change", persist);
    el.addEventListener("input", persist);
  }});
}}

document.getElementById("prevBtn").onclick = () => {{
  const idxs = filteredIndexes();
  const pos = idxs.indexOf(index);
  index = idxs[Math.max(0, pos - 1)] ?? index;
  render();
}};
document.getElementById("nextBtn").onclick = () => {{
  const idxs = filteredIndexes();
  const pos = idxs.indexOf(index);
  index = idxs[Math.min(idxs.length - 1, pos + 1)] ?? index;
  render();
}};
document.getElementById("unreviewedBtn").onclick = () => {{
  const idxs = DATA.map((item, i) => i).filter(i => !reviews[DATA[i].case.case_id]?.best);
  if (idxs.length) index = idxs[0];
  render();
}};
document.getElementById("revealBtn").onclick = () => {{ reveal = !reveal; render(); }};
document.getElementById("filterSelect").onchange = () => render();
document.getElementById("viewSelect").onchange = () => render();

function download(filename, text, type) {{
  const blob = new Blob([text], {{type}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}}

document.getElementById("exportJsonBtn").onclick = () => {{
  const enriched = {{
    run_id: RUN_ID,
    exported_at: new Date().toISOString(),
    reviews: reviews,
    label_maps: Object.fromEntries(DATA.map(d => [d.case.case_id, d.label_map])),
  }};
  download(`review_${{RUN_ID}}.json`, JSON.stringify(enriched, null, 2), "application/json");
}};

document.getElementById("exportCsvBtn").onclick = () => {{
  const rows = [["case_id","best","project_accuracy","over_interpretation","answered_again","memo"]];
  Object.values(reviews).forEach(r => {{
    rows.push([r.case_id, r.best||"", r.project_accuracy||"", r.over_interpretation||"", r.answered_again||"", (r.memo||"").replaceAll("\\n"," ")]);
  }});
  const csv = rows.map(r => r.map(v => `"${{String(v).replaceAll('"','""')}}"`).join(",")).join("\\n");
  download(`review_${{RUN_ID}}.csv`, csv, "text/csv");
}};

render();
</script>
</body>
</html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
