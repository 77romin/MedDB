"""Replay completed E2 ledger traces through the deterministic shadow engine.

The replay never calls an API or an LLM.  If the dictionary cannot determine a
targeted answer's assertion, it records unknown rather than guessing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/meddb"))

from examples.hybrid_agent import Tracker
from examples.consult_skeleton import demographics
from examples.hybrid_care import prepare
from meddb.coverage import CareCoverage
from nova_agent.e2_convergence import ConvergenceEngine


def _events(trace):
    initial = None
    ledger = None
    rows = [json.loads(line) for line in Path(trace).read_text(encoding="utf-8").splitlines()]
    responses = {row.get("request_id"): row.get("response") for row in rows if row.get("event") == "http_response"}
    answer_verdicts, exam_verdicts = {}, {}
    for row in rows:
        if row.get("event") == "http_response":
            response = row.get("response") or {}
            if isinstance(response, dict) and response.get("initial"):
                initial = response["initial"]
        elif row.get("event") == "e2_ledger_audit":
            ledger = ((row.get("result") or {}).get("ledger") or {}).get("entries")
        elif row.get("event") == "http_request" and row.get("path") == "/v1/chat/completions":
            body = row.get("body") or {}
            messages = body.get("messages") or []
            prompt = messages[-1].get("content", "") if messages else ""
            response = responses.get(body.get("request_id")) or {}
            try:
                verdict = response["choices"][0]["message"]["content"].strip()[:1]
            except (KeyError, IndexError, TypeError, AttributeError):
                continue
            if verdict not in "+-?":
                continue
            exam = re.match(r"진찰 결과: (.*?)\s+이 결과에 '(.+?)' 소견", prompt, re.S)
            answer = re.match(r"의사: (.*?)\n환자: (.*?)\n\[소견\] (.*?)\n", prompt, re.S)
            if exam:
                exam_verdicts[(exam.group(1).strip(), exam.group(2).strip())] = verdict
            elif answer:
                answer_verdicts[tuple(part.strip() for part in answer.groups())] = verdict
    if not initial or ledger is None:
        raise ValueError("trace must contain a completed E2 ledger run")
    return initial, ledger, answer_verdicts, exam_verdicts


def _answer_verdict(question, answer, finding, saved):
    text = answer.strip()
    if any(word in text for word in ("모르", "기억 안", "기억이 안", "확실하지", "글쎄")):
        return "?"
    no = ("아니", "없", "안 ", "못 ", "전혀", "한 적 없")
    yes = ("네", "예", "맞", "있", "그렇")
    if any(text.startswith(word) for word in no) or (len(text) <= 12 and any(word in text for word in no)):
        return "-"
    if any(text.startswith(word) for word in yes):
        return "+"
    return saved.get((question.strip(), answer.strip(), finding.strip()), "?")


def replay(trace):
    initial, entries, answer_verdicts, exam_verdicts = _events(trace)
    db = prepare()
    opening, vitals = initial["opening"], initial["vital_signs"]
    age, sex = demographics(opening)
    matched = db.match_complaint(opening)
    complaint = matched[0]["id"] if matched else None
    kb = Tracker(db, complaint, age, sex, opening, vitals, "clinical", "reviewed")
    care = CareCoverage(db, complaint, age, sex)
    engine = ConvergenceEngine(db, complaint)
    classified, unknown = 0, 0

    for entry in entries:
        target = entry.get("target") or None
        observed = entry.get("observed_text") or ""
        turn = int(entry.get("turn") or 0)
        if entry.get("action") == "SAY":
            care.observe(target, entry.get("clinician_text", ""), observed, turn)
            if target:
                kb.asked.add(target)
                kb.turns.setdefault(target, turn)
                if target in db.slots:
                    kb.answers[target] = observed
                    classified += 1
                elif target in db.findings:
                    verdict = _answer_verdict(entry.get("clinician_text", ""), observed,
                                              db.findings[target]["ko"], answer_verdicts)
                    kb.mark(target, verdict, turn, observed)
                    classified += verdict != "?"
                    unknown += verdict == "?"
            kb.note_seen(observed, turn)
        elif entry.get("action") == "EXAM":
            target = target or kb.exam_id(entry.get("clinician_text", ""))
            if target:
                kb.exams_done.add(target)
                kb.exam_results[target] = observed
                kb.turns.setdefault(target, turn)
                for fid in db.exam_findings.get(target, []):
                    finding = db.findings.get(fid, {})
                    verdict = exam_verdicts.get((observed.strip(), finding.get("ko", "").strip()))
                    if verdict:
                        kb.mark(fid, verdict, turn, observed, "exam")
        actions = care.needed(kb)
        engine.observe(kb, actions, care.records)

    trajectory = engine.snapshot()
    encoded = json.dumps(trajectory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    final = trajectory[-1] if trajectory else {}
    first_converged = next((row["step"] for row in trajectory if row.get("converged")), None)
    return {
        "trace": str(Path(trace)),
        "entries": len(entries),
        "classified_targets": classified,
        "unknown_target_assertions": unknown,
        "snapshots": len(trajectory),
        "trajectory_sha256": hashlib.sha256(encoded).hexdigest(),
        "final_top": (final.get("candidates") or [{}])[0].get("name"),
        "final_margin": final.get("margin"),
        "final_converged": final.get("converged"),
        "first_converged_snapshot": first_converged,
        "final_unknown_top_key": final.get("unknown_top_key"),
        "final_pending_red_flags": final.get("pending_red_flags"),
        "final_conflicts": final.get("conflicts"),
        "final_safety_missing": final.get("safety_missing"),
        "final_convergence_reasons": final.get("convergence_reasons"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+")
    parser.add_argument("--out")
    args = parser.parse_args()
    result = [replay(path) for path in args.traces]
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
