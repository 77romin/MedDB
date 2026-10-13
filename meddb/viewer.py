"""KB를 브라우저로 살펴보는 한 파일짜리 화면을 만든다 (python -m meddb page).

서버 없이 열리는 HTML 하나에 데이터와 스크립트를 함께 넣는다. 화면의 감별 순위와 다음 행동은
api.py의 candidates / next_actions 와 같은 식을 JS로 옮긴 것이고(CORE_JS), tests에서 둘이 같은 답을 내는지 확인한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import __version__
from .api import (AGE_PENALTY, CONFIDENT_SHARE, NOTE_FIELDS, STAGE_ORDER, W_ABSENT, W_FREQ, W_PRESENT, W_PREV,
                  MedDB)


def export_data(db: MedDB) -> dict:
    """화면에 필요한 것만 추린 자료. 상병마스터 전체와 진료 통계 원자료는 넣지 않는다."""
    def prior_table(did: str) -> dict | None:
        if db.prior(did) is None:
            return None
        table = {}
        for sex in (None, "M", "F"):
            table[(sex or "A") + "0"] = db.prior(did, None, sex)
            for group in range(1, 19):
                table[(sex or "A") + str(group)] = db.prior(did, (group - 1) * 5, sex)
        return table

    diseases = {}
    for did, d in db.diseases.items():
        diseases[did] = {
            **{k: d[k] for k in ("ko", "en", "kcd", "urgency", "freq", "sex", "age_min", "age_max", "dispo")},
            "red_flag": bool(d["red_flag"]),
            "roles": {f: [role, db.sources[did][f]] for f, role in db.roles[did].items()},
            "rule_out": list(db.rule_out.get(did, [])),
            "plan": {k: list(v) for k, v in db.plans[did].items()},
            "guidelines": db.guideline_docs.get(did, []),
            "prior": prior_table(did),
        }
    return {
        "meta": {**db.meta, "code_version": __version__},
        "weights": {"present": W_PRESENT, "absent": W_ABSENT, "freq": W_FREQ, "prev": W_PREV,
                    "age_penalty": AGE_PENALTY, "confident_share": CONFIDENT_SHARE, "stages": list(STAGE_ORDER)},
        "note_fields": {k: list(v) for k, v in NOTE_FIELDS.items()},
        "slots": {i: {**{k: s[k] for k in ("ko", "ask", "sex", "age_min", "age_max")}, "note": db.note_field(i)}
                  for i, s in db.slots.items()},
        "exams": {i: {"ko": e["ko"], "action": e["action"], "findings": list(db.exam_findings.get(i, []))}
                  for i, e in db.exams.items()},
        "findings": {i: {**{k: f[k] for k in ("ko", "kind", "sys", "ask", "sex", "age_min", "age_max")},
                         "exam": f["exam_id"], "note": db.note_field(i)} for i, f in db.findings.items()},
        "diseases": diseases,
        "complaints": {cid: {"ko": c["ko"], "slots": list(db.items[cid]["slot"]), "ask": list(db.items[cid]["finding"]),
                             "exams": list(db.items[cid]["exam"]), "diseases": list(db.complaint_diseases[cid]),
                             "guidelines": db.guideline_docs.get(cid, [])} for cid, c in db.complaints.items()},
        "background": [ref for _kind, ref in db.background],
        "vital_findings": sorted({r["finding_id"] for r in db.vital_rules}),
    }


# api.py 의 계산을 그대로 옮긴 부분. 화면 코드와 분리해 두어 Node로 따로 시험한다.
CORE_JS = r"""
function fits(row, age, sex) {
  if (sex && row.sex && row.sex !== sex) return false;
  if (age != null) {
    if (row.age_min != null && age < row.age_min) return false;
    if (row.age_max != null && age > row.age_max) return false;
  }
  return true;
}
function priorOf(D, did, age, sex) {
  const table = D.diseases[did].prior;
  if (!table) return null;
  const group = age == null ? 0 : Math.min(Math.floor(age / 5) + 1, 18);
  const value = table[(sex || "A") + group];
  return value == null ? null : value;
}
function knownSet(D, present, absent, examsDone) {
  const known = new Set([...present, ...absent]);
  // An exam's completion does not establish all findings it could assess.
  return known;
}
function candidates(D, complaint, present, absent, age, sex, k) {
  const W = D.weights, P = new Set(present), A = new Set(absent), rows = [];
  for (const did of D.complaints[complaint].diseases) {
    const d = D.diseases[did];
    if (sex && d.sex && d.sex !== sex) continue;
    const prior = priorOf(D, did, age, sex);
    let score = W.freq * d.freq + W.prev * (prior || 0);
    const matched = [], against = [], unknownKey = [];
    for (const [fid, [role]] of Object.entries(d.roles)) {
      if (P.has(fid)) { score += W.present[role]; (role === "against" ? against : matched).push(fid); }
      else if (A.has(fid)) { score += W.absent[role]; if (role === "key") against.push(fid); }
      else if (role === "key") unknownKey.push(fid);
    }
    if (!fits(d, age, null)) score -= W.age_penalty;
    rows.push({id: did, ko: d.ko, kcd: d.kcd, score: Math.round(score * 100) / 100, prior, red_flag: d.red_flag,
               urgency: d.urgency, matched, against, unknown_key: unknownKey});
  }
  rows.sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : 1));
  const z = rows.reduce((s, r) => s + Math.exp(r.score / 2), 0) || 1;
  for (const r of rows) r.share = Math.round(Math.exp(r.score / 2) / z * 1000) / 1000;
  return rows.slice(0, k);
}
function redFlagsPending(D, complaint, present, absent, examsDone, age, sex) {
  const known = knownSet(D, present, absent, examsDone), out = [];
  for (const did of D.complaints[complaint].diseases) {
    const d = D.diseases[did];
    if (!d.red_flag || !fits(d, age, sex)) continue;
    const todo = d.rule_out.filter(f => !known.has(f) && fits(D.findings[f], age, sex));
    if (todo.length) out.push({id: did, ko: d.ko, unchecked: todo});
  }
  return out;
}
function actionFor(D, target, stage, why) {
  if (D.slots[target]) return {type: "SAY", text: D.slots[target].ask, stage, target, resolves: [], why};
  if (D.exams[target]) return {type: "EXAM", text: D.exams[target].action, stage, target,
                               resolves: D.exams[target].findings.slice(), why};
  const f = D.findings[target];
  if (f.kind === "sign") return actionFor(D, f.exam, stage, why);
  if (f.kind === "vital") return null;
  return {type: "SAY", text: f.ask, stage, target, resolves: [target], why};
}
function nextActions(D, complaint, present, absent, asked, examsDone, age, sex) {
  const C = D.complaints[complaint], known = knownSet(D, present, absent, examsDone);
  const askedSet = new Set(asked), doneSet = new Set(examsDone), out = [], seen = new Set();
  const push = (target, stage, why) => {
    const row = D.slots[target] || D.findings[target] || {};
    if (!fits(row, age, sex)) return;
    if (askedSet.has(target) || doneSet.has(target) || known.has(target)) return;
    const act = actionFor(D, target, stage, why);
    if (!act || doneSet.has(act.target) || seen.has(act.text)) return;
    seen.add(act.text); out.push(act);
  };
  for (const s of C.slots) push(s, "hpi", "현병력");
  for (const rf of redFlagsPending(D, complaint, present, absent, examsDone, age, sex))
    for (const f of rf.unchecked) push(f, "red_flag", rf.ko + " 배제");
  for (const f of C.ask) push(f, "core", "주호소 필수 문진");
  for (const e of C.exams) push(e, "exam", "주호소 필수 진찰");
  const top = candidates(D, complaint, present, absent, age, sex, 5);
  if (top.length && top[0].share >= D.weights.confident_share) {
    for (const f of top[0].unknown_key) push(f, "discriminate", "확인: " + top[0].ko);
  } else {
    const value = new Map();
    for (const c of top)
      for (const [fid, [role]] of Object.entries(D.diseases[c.id].roles))
        if (!known.has(fid) && role !== "against")
          value.set(fid, (value.get(fid) || 0) + c.share * (role === "key" ? 1.0 : 0.4));
    const total = top.reduce((s, c) => s + c.share, 0) || 1;
    const ranked = [...value].map(([fid, q]) => [(q / total) * (1 - q / total), fid])
      .sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? 1 : -1));
    for (const [split, fid] of ranked) {
      if (split < 0.08) continue;
      const owners = top.filter(c => ["key", "support"].includes((D.diseases[c.id].roles[fid] || [])[0])).map(c => c.ko);
      push(fid, "discriminate", "감별: " + owners.slice(0, 3).join(" / "));
    }
  }
  for (const ref of D.background) push(ref, "background", "과거력·사회력");
  const order = D.weights.stages;
  return out.map((a, i) => [a, i]).sort((x, y) => order.indexOf(x[0].stage) - order.indexOf(y[0].stage) || x[1] - y[1])
            .map(x => x[0]);
}
"""

PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MedDB 진료 흐름</title>
<style>
:root { --bg:#f6f5f1; --panel:#fff; --ink:#1d2330; --muted:#667085; --line:#e2e0d9; --accent:#1f5fbf; --accent-bg:#e8f0fc;
  --danger:#b42318; --danger-bg:#fdeceb; --ok:#127a4b; --ok-bg:#e6f4ec; --warn:#93580a; --warn-bg:#fdf1dc; --chip:#eeece6; }
:root:not([data-theme="light"]) { color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#14171d; --panel:#1c2029; --ink:#e6e8ee; --muted:#9aa3b5;
  --line:#2c323e; --accent:#7aa7ff; --accent-bg:#1d2b47; --danger:#ff8b82; --danger-bg:#3a1f1e; --ok:#63d29a; --ok-bg:#16322a;
  --warn:#f0b65a; --warn-bg:#3a2d17; --chip:#272c37; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.55 -apple-system,"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif; }
header { padding:14px 16px 10px; border-bottom:1px solid var(--line); background:var(--panel); }
h1 { font-size:18px; margin:0 0 2px; } h2 { font-size:15px; margin:0 0 8px; } h3 { font-size:13px; margin:14px 0 6px; color:var(--muted); font-weight:600; }
.sub { color:var(--muted); font-size:12.5px; }
.banner { margin-top:8px; padding:6px 10px; border-radius:6px; background:var(--warn-bg); color:var(--warn); font-size:12.5px; }
nav { display:flex; gap:4px; padding:8px 16px 0; background:var(--panel); border-bottom:1px solid var(--line); flex-wrap:wrap; }
nav button { border:0; background:none; color:var(--muted); padding:7px 12px; font:inherit; cursor:pointer; border-bottom:2px solid transparent; }
nav button[aria-selected="true"] { color:var(--accent); border-color:var(--accent); font-weight:600; }
main { padding:14px 16px 40px; max-width:1280px; margin:0 auto; }
.grid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:14px; }
@media (max-width:900px) { .grid { grid-template-columns:1fr; } }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; min-width:0; }
.row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
select, input[type=number], input[type=search] { font:inherit; padding:5px 8px; border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--ink); }
input[type=number] { width:72px; }
.chip { display:inline-block; padding:1px 7px; border-radius:99px; background:var(--chip); font-size:11.5px; white-space:nowrap; }
.chip.rf { background:var(--danger-bg); color:var(--danger); } .chip.ok { background:var(--ok-bg); color:var(--ok); }
.chip.src { background:var(--accent-bg); color:var(--accent); } .chip.warn { background:var(--warn-bg); color:var(--warn); }
.stage { font-size:11px; font-weight:700; letter-spacing:.02em; width:74px; flex:none; color:var(--muted); }
.stage.red_flag { color:var(--danger); }
.act { display:flex; gap:8px; align-items:flex-start; padding:7px 0; border-top:1px solid var(--line); }
.act:first-child { border-top:0; }
.act .body { flex:1; min-width:0; } .act .text { font-weight:600; overflow-wrap:anywhere; }
.btns { display:flex; gap:4px; flex:none; flex-wrap:wrap; justify-content:flex-end; }
button.b { font:inherit; font-size:12.5px; padding:3px 9px; border-radius:6px; border:1px solid var(--line); background:var(--panel); color:var(--ink); cursor:pointer; }
button.b:hover { border-color:var(--accent); } button.b.pos { color:var(--ok); } button.b.neg { color:var(--danger); }
button.link { border:0; background:none; color:var(--accent); cursor:pointer; font:inherit; padding:0; text-align:left; }
.bar { height:6px; border-radius:3px; background:var(--chip); overflow:hidden; margin-top:3px; } .bar i { display:block; height:100%; background:var(--accent); }
.cand { padding:7px 0; border-top:1px solid var(--line); } .cand:first-child { border-top:0; }
.log { font-size:12.5px; color:var(--muted); } .log b { color:var(--ink); font-weight:600; }
table { width:100%; border-collapse:collapse; font-size:12.5px; } th, td { text-align:left; vertical-align:top; padding:6px 8px; border-top:1px solid var(--line); }
th { color:var(--muted); font-weight:600; white-space:nowrap; } .scroll { overflow-x:auto; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:10px; margin:0; font:12.5px/1.5 ui-monospace,Menlo,Consolas,monospace; }
dialog { border:1px solid var(--line); border-radius:12px; background:var(--panel); color:var(--ink); max-width:720px; width:calc(100% - 32px); max-height:calc(100% - 32px); overflow:auto; padding:16px; }
dialog::backdrop { background:rgba(0,0,0,.45); }
ul.plain { margin:4px 0; padding-left:18px; } .muted { color:var(--muted); } .kv { display:grid; grid-template-columns:86px 1fr; gap:4px 10px; }
</style>
</head>
<body>
<header>
  <h1>MedDB 진료 흐름</h1>
  <div class="sub" id="summary"></div>
  <div class="banner" id="banner"></div>
</header>
<nav role="tablist">
  <button role="tab" data-tab="sim" aria-selected="true">진료 흐름 따라가기</button>
  <button role="tab" data-tab="review" aria-selected="false">검수용 표</button>
  <button role="tab" data-tab="about" aria-selected="false">구성과 출처</button>
</nav>
<main>
  <section id="tab-sim">
    <div class="card" style="margin-bottom:14px">
      <div class="row">
        <label>주호소 <select id="complaint"></select></label>
        <label>나이 <input type="number" id="age" min="0" max="120" value="58"></label>
        <label>성별 <select id="sex"><option value="M">남</option><option value="F">여</option><option value="">모름</option></select></label>
        <button class="b" id="reset">처음부터</button>
        <span class="chip" id="turns"></span><span class="chip" id="ready"></span>
      </div>
      <div class="row" style="margin-top:8px"><span class="sub">내원 시 활력징후 이상:</span><span id="vitals" class="row"></span></div>
    </div>
    <div class="grid">
      <div>
        <div class="card"><h2>다음에 할 행동</h2>
          <div class="sub" style="margin-bottom:6px">환자가 뭐라고 답했는지 눌러 보면 목록과 감별 순위가 바뀝니다. 괄호 안은 글자 수(한도 30자)입니다.</div>
          <div id="actions"></div></div>
        <div class="card" style="margin-top:14px"><h2>지금까지 한 것</h2><div id="history" class="log"></div></div>
      </div>
      <div>
        <div class="card"><h2>감별 순위</h2><div class="sub" style="margin-bottom:6px">점수는 소견 겹침과 성·연령별 흔한 정도를 더한 값이고, 확률이 아닙니다.</div><div id="cands"></div></div>
        <div class="card" style="margin-top:14px"><h2>아직 배제하지 못한 위험 질환</h2><div id="redflags"></div></div>
        <div class="card" style="margin-top:14px"><h2>이 주호소의 진료지침 문서</h2><div id="cdocs"></div></div>
      </div>
    </div>
  </section>
  <section id="tab-review" hidden>
    <div class="card"><div class="row"><label>주호소 <select id="rcomplaint"></select></label>
      <span class="sub">질환명을 누르면 계획과 출처까지 볼 수 있습니다. 고칠 곳은 <code>meddb/data/*.json</code>입니다.</span></div>
      <div id="rflow"></div><div class="scroll"><table id="rtable"></table></div></div>
  </section>
  <section id="tab-about" hidden><div class="card" id="about"></div></section>
</main>
<dialog id="dlg"><div id="dlgbody"></div><div style="text-align:right;margin-top:12px"><button class="b" id="dlgclose">닫기</button></div></dialog>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
__CORE__
const D = JSON.parse(document.getElementById("data").textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const STAGE = {hpi:"현병력", red_flag:"위험 배제", core:"필수 문진", exam:"필수 진찰", discriminate:"감별", background:"과거력"};
const SRC = {"team":"팀 작성", "team+ddxplus":"팀 + DDXPlus", "ddxplus":"DDXPlus"};
const name = id => (D.findings[id] || D.slots[id] || D.exams[id] || {}).ko || id;
let S;
function reset() { S = {present:[], absent:[], asked:[], exams:[], log:[]}; }
const ctx = () => ({c:$("complaint").value, age:$("age").value === "" ? null : +$("age").value, sex:$("sex").value || null});
function setFinding(fid, mark, turn) {
  S.present = S.present.filter(f => f !== fid); S.absent = S.absent.filter(f => f !== fid);
  if (mark === "+") S.present.push(fid); else if (mark === "-") S.absent.push(fid);
  if (turn) S.log.push({kind:"SAY", text:D.findings[fid].ask, result:name(fid) + " (" + mark + ")"});
}
function render() {
  const {c, age, sex} = ctx();
  const acts = nextActions(D, c, S.present, S.absent, S.asked, S.exams, age, sex);
  const required = acts.filter(a => a.stage !== "discriminate");
  $("turns").textContent = "쓴 턴 " + S.log.length + " / 남은 필수 행동 " + required.length;
  $("ready").textContent = required.length ? "필수 단계 진행 중" : "진단해도 되는 상태";
  $("ready").className = "chip " + (required.length ? "warn" : "ok");
  $("vitals").innerHTML = D.vital_findings.map(f => `<label><input type="checkbox" data-vital="${f}" ${S.present.includes(f) ? "checked" : ""}> ${esc(name(f))}</label>`).join(" ");
  $("actions").innerHTML = acts.length ? acts.map((a, i) => {
    let btns;
    if (a.type === "EXAM") btns = `<button class="b" data-do="exam" data-i="${i}">시행</button>`;
    else if (D.slots[a.target]) btns = `<button class="b" data-do="slot" data-i="${i}">물어봄</button>`;
    else btns = `<button class="b pos" data-do="yes" data-i="${i}">있음</button><button class="b neg" data-do="no" data-i="${i}">없음</button>`;
    return `<div class="act"><span class="stage ${a.stage}">${STAGE[a.stage]}</span><div class="body"><div class="text">${a.type} · ${esc(a.text)} <span class="muted">(${[...a.text.normalize("NFC")].length})</span></div>
      <div class="sub">${esc(a.why)} · ${esc(name(a.target))}</div></div><div class="btns">${btns}</div></div>`;
  }).join("") : '<div class="sub">남은 행동이 없습니다.</div>';
  $("actions").onclick = e => { const b = e.target.closest("button[data-do]"); if (!b) return; const a = acts[+b.dataset.i];
    if (b.dataset.do === "exam") { S.exams.push(a.target); S.log.push({kind:"EXAM", text:a.text, exam:a.target}); }
    else if (b.dataset.do === "slot") { S.asked.push(a.target); S.log.push({kind:"SAY", text:a.text, result:name(a.target) + " 확인"}); }
    else setFinding(a.target, b.dataset.do === "yes" ? "+" : "-", true);
    render(); };
  $("history").innerHTML = S.log.length ? S.log.map((l, i) => {
    let extra = l.result ? " → <b>" + esc(l.result) + "</b>" : "";
    if (l.exam) extra = " → " + D.exams[l.exam].findings.map(f => { const m = S.present.includes(f) ? "+" : "-";
      return `<button class="b ${m === "+" ? "pos" : ""}" data-sign="${f}">${esc(name(f))} (${m})</button>`; }).join(" ");
    return `<div>턴 ${i + 1} · ${l.kind} · ${esc(l.text)}${extra}</div>`; }).join("") : "아직 없습니다.";
  $("history").onclick = e => { const b = e.target.closest("button[data-sign]"); if (!b) return; const f = b.dataset.sign;
    setFinding(f, S.present.includes(f) ? "-" : "+", false); render(); };
  const top = candidates(D, c, S.present, S.absent, age, sex, 8), best = Math.max(...top.map(t => t.share), 0.001);
  $("cands").innerHTML = top.map((t, i) => `<div class="cand"><div class="row"><b>${i + 1}.</b> <button class="link" data-dis="${t.id}">${esc(t.ko)}</button>
    ${t.red_flag ? '<span class="chip rf">위험</span>' : ""}<span class="chip">${t.score.toFixed(2)}점</span><span class="chip">비중 ${(t.share * 100).toFixed(0)}%</span></div>
    <div class="bar"><i style="width:${(t.share / best * 100).toFixed(0)}%"></i></div>
    <div class="sub">${t.matched.length ? "맞는 소견: " + esc(t.matched.map(name).join(", ")) : "맞는 소견 없음"}${t.against.length ? " · 어긋남: " + esc(t.against.map(name).join(", ")) : ""}</div></div>`).join("");
  const rf = redFlagsPending(D, c, S.present, S.absent, S.exams, age, sex);
  $("redflags").innerHTML = rf.length ? rf.map(r => `<div class="cand"><button class="link" data-dis="${r.id}">${esc(r.ko)}</button>
    <div class="sub">확인할 것: ${esc(r.unchecked.map(name).join(", "))}</div></div>`).join("") : '<span class="chip ok">모두 확인함</span>';
  $("cdocs").innerHTML = docs(D.complaints[c].guidelines);
}
function docs(list) {
  return list && list.length ? '<ul class="plain">' + list.map(d => `<li>${esc(d.title)} <span class="muted">· ${esc(d.org || "")} ${esc(d.year || "")}</span>
    <span class="chip">${esc(d.license)}</span><div class="sub">${esc(d.file)}</div></li>`).join("") + "</ul>" : '<span class="sub">연결된 문서 없음</span>';
}
function findingChips(d, role) {
  const ids = Object.keys(d.roles).filter(f => d.roles[f][0] === role);
  return ids.length ? ids.map(f => `<span class="chip ${d.roles[f][1] === "team" ? "" : "src"}" title="${SRC[d.roles[f][1]]}">${esc(name(f))}${d.rule_out.includes(f) ? " ★" : ""}</span>`).join(" ") : '<span class="muted">—</span>';
}
function showDisease(id) {
  const d = D.diseases[id], P = d.plan, li = a => (a && a.length ? '<ul class="plain">' + a.map(x => "<li>" + esc(x) + "</li>").join("") + "</ul>" : '<span class="muted">—</span>');
  $("dlgbody").innerHTML = `<h2>${esc(d.ko)} <span class="muted" style="font-weight:400">${esc(d.en)}</span></h2>
    <div class="row">${d.red_flag ? '<span class="chip rf">반드시 배제</span>' : ""}<span class="chip">KCD ${esc(d.kcd || "없음")}</span><span class="chip">${esc(d.urgency)}</span>
      <span class="chip">흔한 정도 ${d.freq}/3</span>${d.sex ? `<span class="chip">${d.sex === "F" ? "여성" : "남성"}</span>` : ""}
      ${d.age_min != null || d.age_max != null ? `<span class="chip">${d.age_min ?? ""}~${d.age_max ?? ""}세</span>` : ""}</div>
    <h3>소견 <span style="font-weight:400">(파란색은 DDXPlus가 뒷받침, ★는 배제할 때 확인할 것)</span></h3>
    <div class="kv"><span class="muted">핵심</span><div>${findingChips(d, "key")}</div><span class="muted">보조</span><div>${findingChips(d, "support")}</div>
      <span class="muted">반대</span><div>${findingChips(d, "against")}</div></div>
    <h3>계획</h3><div class="kv"><span class="muted">검사</span><div>${li(P.test)}</div><span class="muted">치료</span><div>${li(P.treat)}</div>
      <span class="muted">처치 결정</span><div>${esc(d.dispo)}</div><span class="muted">교육·추적</span><div>${li(P.edu)}</div>
      <span class="muted">설명(SAY)</span><div>${li(P.explain)}</div><span class="muted">금기</span><div>${li(P.unsafe)}</div></div>
    <h3>진료지침 문서 <span style="font-weight:400">(제목으로 고른 것)</span></h3>${docs(d.guidelines)}`;
  $("dlg").showModal();
}
function renderReview() {
  const c = $("rcomplaint").value, C = D.complaints[c];
  const line = (label, ids, text) => `<div><span class="stage" style="display:inline-block">${label}</span> ${ids.map(i => `<span class="chip" title="${esc(text(i))}">${esc(name(i))}</span>`).join(" ") || '<span class="muted">—</span>'}</div>`;
  $("rflow").innerHTML = '<h3>항상 확인하는 것</h3>' + line("현병력", C.slots, i => D.slots[i].ask) + line("필수 문진", C.ask, i => D.findings[i].ask)
    + line("필수 진찰", C.exams, i => D.exams[i].action) + line("과거력", D.background, i => (D.slots[i] || D.findings[i]).ask) + '<h3>감별 질환</h3>';
  $("rtable").innerHTML = "<tr><th>질환</th><th>KCD</th><th>핵심 소견</th><th>보조 소견</th><th>반대 소견</th><th>처치 결정</th></tr>" + C.diseases.map(id => { const d = D.diseases[id];
    return `<tr><td><button class="link" data-dis="${id}">${esc(d.ko)}</button> ${d.red_flag ? '<span class="chip rf">위험</span>' : ""}</td><td>${esc(d.kcd || "—")}</td>
      <td>${findingChips(d, "key")}</td><td>${findingChips(d, "support")}</td><td>${findingChips(d, "against")}</td><td>${esc(d.dispo)}</td></tr>`; }).join("");
}
function renderAbout() {
  const n = o => Object.keys(o).length, links = Object.values(D.diseases).flatMap(d => Object.values(d.roles).map(r => r[1]));
  const count = s => links.filter(x => x === s).length, M = D.meta;
  $("about").innerHTML = `<h2>구성</h2><div class="kv"><span class="muted">주호소</span><div>${n(D.complaints)}개</div><span class="muted">질환</span><div>${n(D.diseases)}개 (반드시 배제할 질환 ${Object.values(D.diseases).filter(d => d.red_flag).length}개)</div>
    <span class="muted">소견</span><div>${n(D.findings)}개</div><span class="muted">진찰</span><div>${n(D.exams)}개</div>
    <span class="muted">연결</span><div>${links.length}건 — 팀 작성 ${count("team")}, 팀 작성 + DDXPlus 일치 ${count("team+ddxplus")}, DDXPlus에서만 ${count("ddxplus")}</div></div>
    <h2 style="margin-top:16px">무엇이 어디서 왔나</h2><ul class="plain">
    <li><b>팀 작성 (임상 검수 전)</b>: 감별 범위, 위험 질환 지정, 소견의 역할, 질문·진찰 문장, 검사·처치 계획</li>
    <li><b>건강보험심사평가원 상병마스터</b> (공공누리 제1유형): KCD 코드 검증</li>
    <li><b>건강보험심사평가원 진료 통계</b> (공공누리 제1유형): 성·연령별 흔한 정도</li>
    <li><b>DDXPlus</b> (CC BY 4.0, ${esc(M["ddxplus.citation"] || "")}): 질환–소견 연결 보강</li>
    <li><b>N.O.V.A. 2026 진료지침 코퍼스</b>: 문서의 제목·파일명·라이선스만 수록. 본문은 넣지 않음</li></ul>
    <h2 style="margin-top:16px">점수 계산</h2><pre>점수 = 흔한 정도(1~3) × ${D.weights.freq} + 사전확률(−2~1.5) × ${D.weights.prev}
     + 핵심 소견 있음 ${D.weights.present.key} / 없음 ${D.weights.absent.key}
     + 보조 소견 있음 ${D.weights.present.support} / 없음 ${D.weights.absent.support}
     + 반대 소견 있음 ${D.weights.present.against}
     − 나이 범위 밖 ${D.weights.age_penalty}
가중치는 팀이 임의로 정한 값이고 증례로 조정해야 합니다.</pre>
    <h2 style="margin-top:16px">제출 기록의 칸</h2><pre>${esc(Object.entries(D.note_fields).map(([k, v]) => k + ": " + v.join(", ")).join("\n"))}
주진단은 기록 밖의 별도 인자입니다.</pre>`;
}
for (const sel of ["complaint", "rcomplaint"]) $(sel).innerHTML = Object.entries(D.complaints).map(([id, c]) => `<option value="${id}">${esc(c.ko)}</option>`).join("");
$("summary").textContent = `KB ${D.meta.kb_version} · 주호소 ${Object.keys(D.complaints).length} · 질환 ${Object.keys(D.diseases).length} · 소견 ${Object.keys(D.findings).length} · ${D.meta.author || ""}`;
$("banner").textContent = "검수 상태: " + (D.meta.review || "") + ". 의학 내용은 초안이며 실제 진료에 쓰는 자료가 아닙니다.";
document.querySelector("nav").onclick = e => { const b = e.target.closest("button[data-tab]"); if (!b) return;
  for (const t of document.querySelectorAll("nav button")) t.setAttribute("aria-selected", t === b);
  for (const s of ["sim", "review", "about"]) $("tab-" + s).hidden = s !== b.dataset.tab; };
document.body.addEventListener("click", e => { const b = e.target.closest("[data-dis]"); if (b) showDisease(b.dataset.dis); });
$("dlgclose").onclick = () => $("dlg").close();
$("vitals").onchange = e => { const f = e.target.dataset.vital; if (!f) return; setFinding(f, e.target.checked ? "+" : "", false); render(); };
$("complaint").onchange = () => { reset(); render(); };
$("reset").onclick = () => { reset(); render(); };
$("age").oninput = render; $("sex").onchange = render; $("rcomplaint").onchange = renderReview;
reset(); render(); renderReview(); renderAbout();
</script>
</body>
</html>
"""


def render(db: MedDB | None = None) -> str:
    db = db or MedDB.open()
    data = json.dumps(export_data(db), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.replace("__CORE__", CORE_JS).replace("__DATA__", data)


def write(path: str | Path = "docs/viewer.html") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    return path
