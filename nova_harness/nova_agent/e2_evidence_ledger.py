"""Append-only evidence ledger for the upstream E2 consultation."""
from dataclasses import asdict, dataclass
import re


@dataclass
class LedgerEntry:
    evidence_id: str
    turn: int
    action: str
    clinician_text: str
    observed_text: str
    target: str = ""
    soap_field: str = ""
    disposition: str = ""
    reason: str = ""


class EvidenceLedger:
    def __init__(self):
        self.entries = []
        self.errors = []

    def record(self, action, clinician_text, reply):
        key = "content" if action == "SAY" else "result"
        observed = reply.get(key, "") if isinstance(reply, dict) else ""
        turn = reply.get("turn") if isinstance(reply, dict) else None
        if not isinstance(turn, int) or not isinstance(observed, str):
            raise ValueError("successful clinical response lacks a turn or text")
        entry = LedgerEntry(
            evidence_id=f"e2-{len(self.entries)+1}", turn=turn, action=action,
            clinician_text=str(clinician_text), observed_text=observed,
        )
        self.entries.append(entry)
        return entry

    def record_error(self, action, clinician_text, code):
        self.errors.append({"action": action, "clinician_text": str(clinician_text), "code": str(code)})

    def annotate(self, turn, clinician_text, target, soap_field=""):
        candidates = [e for e in self.entries if e.turn == turn and e.action == "SAY"]
        if clinician_text:
            exact = [e for e in candidates if e.clinician_text == clinician_text]
            candidates = exact or candidates
        if candidates:
            candidates[-1].target = str(target or "")
            candidates[-1].soap_field = str(soap_field or "")

    def unresolved(self):
        return [e for e in self.entries if not e.disposition]

    def snapshot(self):
        return {"entries": [asdict(e) for e in self.entries], "errors": list(self.errors)}


ACKNOWLEDGEMENT = re.compile(
    r"^\s*(?:(?:네|예)(?:[,，]?\s*(?:알겠습니다|알겠어요|감사합니다|고맙습니다|그럴게요|그러겠습니다))?|알겠습니다|알겠어요|감사합니다|고맙습니다|그럴게요|그러겠습니다)[.!。\s]*$"
)


def is_nonclinical(entry):
    return entry.action == "SAY" and bool(ACKNOWLEDGEMENT.fullmatch(entry.observed_text or ""))
