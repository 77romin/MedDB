"""Deterministically reconcile an E2 evidence ledger with its SOAP draft."""
from copy import deepcopy
import re

from .e2_evidence_ledger import is_nonclinical

FIELDS = {"hpi", "pmh", "fh", "sh", "ros"}
TARGET_FIELDS = {
    "pmh": "pmh", "meds": "pmh", "med_name": "pmh", "med_schedule": "pmh",
    "med_duration": "pmh", "med_strength": "pmh", "med_last_taken": "pmh",
    "med_total_24h": "pmh", "med_sources": "pmh", "other_sedatives": "pmh",
    "allergy": "pmh", "family": "fh", "smoking": "sh", "heavy_alcohol": "sh",
    "caffeine": "sh",
}
SOCIAL = re.compile(r"담배|흡연|술|음주|커피|카페인|직업")
FAMILY = re.compile(r"가족|부모|어머니|아버지|엄마|아빠|형제|자매")
COMMUNICATION_QUESTION = re.compile(r"더 궁금|집에서 어떻게|이해하|말씀해 주시겠")
QUESTION_CUE = re.compile(r"\?|나요|세요|습니까|언제|어디|무엇|어떤|얼마|몇 ")
SUBSTANTIVE_CONCERN = re.compile(r"두렵|무서|걱정|불안|아프|힘들|증상|못 자|잠")
PATIENT_QUESTION = re.compile(r"\?|(?:인가요|나요|가요|까요|있나요|되나요)[.!?。\s]*$")
CLINICIAN_QUESTION_END = re.compile(r"\?|(?:나요|까요|습니까|있나요|하셨나요)[.!?。\s]*$")
SAFETY_INSTRUCTION = re.compile(r"응급실|즉시 진료|바로 진료|바로 오세요|즉시 도움|위험")


def _separate_planned_education(note):
    """Make planned education distinguishable from words actually delivered."""
    value = note.get("P", {}).get("education", "")
    if not value or value.startswith("교육 계획(실제 전달 여부 미확인):"):
        return
    marker = "환자에게 설명함:"
    if marker in value:
        planned, delivered = value.split(marker, 1)
        planned = planned.strip(" |\n")
        delivered = delivered.strip()
        parts = []
        if planned:
            parts.append(f"교육 계획(실제 전달 여부 미확인): {planned}")
        if delivered:
            parts.append(f"실제 전달 근거: {delivered}")
        note["P"]["education"] = "\n".join(parts)
    else:
        note["P"]["education"] = f"교육 계획(실제 전달 여부 미확인): {value.strip()}"


def _norm(text):
    return re.sub(r"\s+|[.,!?。]", "", str(text or "")).casefold()


def route(entry):
    if entry.soap_field in FIELDS:
        return entry.soap_field
    if entry.target in TARGET_FIELDS:
        return TARGET_FIELDS[entry.target]
    text = entry.clinician_text + " " + entry.observed_text
    if FAMILY.search(text):
        return "fh"
    if SOCIAL.search(text):
        return "sh"
    return "hpi"


def reconcile(note, ledger, field_limit=5900):
    repaired = deepcopy(note)
    _separate_planned_education(repaired)
    seen = set()
    prior_by_target = {}
    for entry in ledger.entries:
        if is_nonclinical(entry):
            entry.disposition, entry.reason = "nonclinical", "단순 동의·인사"
            continue
        signature = (entry.action, _norm(entry.clinician_text), _norm(entry.observed_text))
        if signature in seen:
            entry.disposition, entry.reason = "duplicate", "동일 질문과 응답 중복"
            continue
        seen.add(signature)
        conflict_key = entry.target or _norm(entry.clinician_text)
        prior = prior_by_target.get((entry.action, conflict_key))
        conflicting = prior is not None and _norm(prior.observed_text) != _norm(entry.observed_text)
        if prior is None:
            prior_by_target[(entry.action, conflict_key)] = entry
        elif conflicting:
            prior.disposition, prior.reason = "conflict", "같은 항목의 상충 원문 보존"
        all_note_text = "\n".join(value for section in repaired.values() for value in section.values())
        if _norm(entry.observed_text) and _norm(entry.observed_text) in _norm(all_note_text):
            entry.disposition = "conflict" if conflicting else "included"
            entry.reason = "같은 항목의 상충 원문 보존" if conflicting else "SOAP 다른 필드에 원문 포함"
            continue
        patient_question = (entry.action == "SAY"
                            and bool(PATIENT_QUESTION.search(entry.observed_text))
                            and not bool(CLINICIAN_QUESTION_END.search(entry.clinician_text)))
        safety_confirmation = (entry.action == "SAY"
                               and bool(SAFETY_INSTRUCTION.search(entry.clinician_text)))
        if entry.action == "SAY" and (COMMUNICATION_QUESTION.search(entry.clinician_text)
                                      or patient_question or safety_confirmation):
            current = repaired["P"]["education"]
            if patient_question or "궁금" in entry.clinician_text:
                label = "환자 질문"
            elif safety_confirmation:
                label = "안전계획 확인"
            else:
                label = "이해 확인 응답"
            line = f"[{entry.evidence_id}, 턴 {entry.turn}] {label}: {entry.observed_text}"
            proposed = (current.rstrip() + ("\n" if current.strip() else "") + line).strip()
            if len(proposed.encode("utf-8")) <= field_limit:
                repaired["P"]["education"] = proposed
                entry.disposition, entry.reason = "included", "P.education 의사소통 근거"
            else:
                entry.disposition, entry.reason = "excluded_with_reason", "P.education 길이 제한"
            continue
        if (entry.action == "SAY" and not entry.target
                and not QUESTION_CUE.search(entry.clinician_text)
                and not SUBSTANTIVE_CONCERN.search(entry.observed_text)):
            entry.disposition, entry.reason = "nonclinical", "설명 뒤 단순 수용 응답"
            continue
        if entry.action == "EXAM":
            section, field = "O", "exam"
        else:
            section, field = "S", route(entry)
        current = repaired[section][field]
        if _norm(entry.observed_text) and _norm(entry.observed_text) in _norm(current):
            entry.disposition = "conflict" if conflicting else "included"
            entry.reason = "같은 항목의 상충 원문 보존" if conflicting else f"{section}.{field} 원문 포함"
            continue
        line = f"[{entry.evidence_id}, 턴 {entry.turn}] {entry.clinician_text} → {entry.observed_text}"
        proposed = (current.rstrip() + ("\n" if current.strip() else "") + line).strip()
        if len(proposed.encode("utf-8")) > field_limit:
            entry.disposition, entry.reason = "excluded_with_reason", f"{section}.{field} 길이 제한"
            continue
        repaired[section][field] = proposed
        entry.disposition = "conflict" if conflicting else "included"
        entry.reason = "같은 항목의 상충 원문 보존" if conflicting else f"{section}.{field} 결정론적 보완"
    return repaired
