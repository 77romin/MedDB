"""Completeness checks for the E2 evidence-ledger overlay."""

UNVERIFIED_MARKER = "교육 계획(실제 전달 여부 미확인):"


def audit(note, ledger):
    unresolved = [e.evidence_id for e in ledger.entries if not e.disposition]
    important_excluded = [e.evidence_id for e in ledger.entries
                          if e.disposition == "excluded_with_reason" and e.action == "EXAM"]
    education = note.get("P", {}).get("education", "")
    education_separated = (not education or UNVERIFIED_MARKER in education
                            or education.startswith("실제 전달 근거:")
                            or education.startswith("[e2-"))
    return {
        "captured": len(ledger.entries),
        "disposed": len(ledger.entries) - len(unresolved),
        "unresolved": unresolved,
        "important_excluded": important_excluded,
        "education_plan_separated": education_separated,
        "complete": not unresolved and not important_excluded and education_separated,
    }


def require_complete(report):
    if not report.get("complete"):
        raise ValueError("SOAP evidence audit incomplete")
