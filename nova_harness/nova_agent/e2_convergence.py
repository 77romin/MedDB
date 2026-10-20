"""Deterministic shadow instrumentation for evidence-driven differential convergence.

The engine never treats MedDB scores or shares as calibrated probabilities.  In
shadow mode it observes the same candidates and actions as upstream E2 and does
not alter either one.
"""
from copy import deepcopy


BASE_SAFETY_TARGETS = frozenset({"meds", "allergy"})
ROLE_SIGNAL = {"key": 2.0, "support": 1.0, "against": -2.0}
MIN_SCORE_MARGIN = 2.0  # Evidence-score gap for shadow gating; never reported as probability.


def _candidate_view(db, row):
    roles = db.roles.get(row["id"], {})
    matched = list(row.get("matched", ()))
    return {
        "id": row["id"],
        "name": row.get("ko", row["id"]),
        "score": float(row.get("score", 0.0)),
        "relative_share": float(row.get("share", 0.0)),
        "matched_key": [fid for fid in matched if roles.get(fid) == "key"],
        "matched_support": [fid for fid in matched if roles.get(fid) == "support"],
        "against": list(row.get("against", ())),
        "unknown_key": list(row.get("unknown_key", ())),
        "red_flag": bool(row.get("red_flag")),
    }


def _pending_red_flags(db, kb):
    if not getattr(kb, "complaint", None):
        return []
    rows = db.red_flags_pending(
        kb.complaint, kb.present, kb.absent, kb.exams_done, kb.age, kb.sex
    )
    return [
        {"id": row["id"], "name": row.get("ko", row["id"]), "unchecked": list(row["unchecked"])}
        for row in rows
    ]


def action_utility(db, candidates, action, known, conflicts):
    """Rank one existing E2 action for audit only; the value is not probability."""
    target = action.get("target")
    if not target:
        return {"total": -1000.0, "separation": 0.0, "risk": 0.0, "decision": 0.0,
                "gap": 0.0, "repeat_cost": 0.0}
    signals = [ROLE_SIGNAL.get(db.roles.get(row["id"], {}).get(target), 0.0) for row in candidates]
    separation = 0.0
    for i, left in enumerate(signals):
        for right in signals[i + 1:]:
            separation += abs(left - right) / (i + 1)
    unknown_owners = sum(target in row.get("unknown_key", ()) for row in candidates)
    risk = 4.0 if action.get("stage") == "red_flag" or str(action.get("why", "")).startswith("위험") else 0.0
    decision = 2.0 if target in BASE_SAFETY_TARGETS or target in {"pregnancy", "breastfeeding"} else 0.0
    gap = min(3.0, float(unknown_owners))
    repeat_cost = 100.0 if target in known and target not in conflicts else 0.0
    total = separation + risk + decision + gap - repeat_cost
    return {"total": round(total, 3), "separation": round(separation, 3),
            "risk": risk, "decision": decision, "gap": gap, "repeat_cost": repeat_cost}


class ConvergenceEngine:
    """Collect candidate trajectories without changing clinical behavior."""

    def __init__(self, db, complaint):
        self.db = db
        self.complaint = complaint
        self.trajectory = []

    def observe(self, kb, actions, records=None):
        ranked = kb.ranked(k=5)
        candidates = [_candidate_view(self.db, row) for row in ranked]
        known = set(kb.present) | set(kb.absent) | set(kb.exams_done)
        conflicts = set(kb.conflicts)
        utilities = []
        for index, action in enumerate(actions):
            item = deepcopy(action)
            item["original_index"] = index
            item["utility"] = action_utility(self.db, candidates, action, known, conflicts)
            utilities.append(item)
        recommended = max(utilities, key=lambda row: (row["utility"]["total"], -row["original_index"]), default=None)
        margin = round(candidates[0]["score"] - candidates[1]["score"], 3) if len(candidates) > 1 else None
        previous = self.trajectory[-1] if self.trajectory else None
        stable_top = bool(previous and candidates and previous["candidates"]
                          and previous["candidates"][0]["id"] == candidates[0]["id"])
        stable_margin = bool(previous and margin is not None and previous["margin"] is not None
                             and margin >= previous["margin"] - 0.25)
        pending_red_flags = _pending_red_flags(self.db, kb)
        recorded = set((records or {}).keys())
        required_safety = set(BASE_SAFETY_TARGETS)
        if getattr(kb, "sex", None) == "F" and 12 <= (getattr(kb, "age", None) or -1) <= 55:
            required_safety.update({"pregnancy", "breastfeeding"})
        safety_missing = sorted(required_safety - recorded)
        top = candidates[0] if candidates else None
        unresolved_top = list(top["unknown_key"]) if top else []
        margin_sufficient = bool(margin is None or margin >= MIN_SCORE_MARGIN)
        ready_now = bool(
            top and top["matched_key"] and not unresolved_top and not pending_red_flags
            and not conflicts and not safety_missing and stable_top and stable_margin and margin_sufficient
        )
        converged = ready_now
        snapshot = {
            "step": len(self.trajectory),
            "candidates": candidates,
            "margin": margin,
            "margin_is_probability": False,
            "top_stable": stable_top,
            "margin_non_decreasing": stable_margin,
            "margin_sufficient": margin_sufficient,
            "pending_red_flags": pending_red_flags,
            "conflicts": sorted(conflicts),
            "unknown_top_key": unresolved_top,
            "safety_missing": safety_missing,
            "recommended_existing_action": recommended,
            "converged": converged,
            "ready_without_streak": ready_now,
            "convergence_reasons": {
                "top_has_matched_key": bool(top and top["matched_key"]),
                "top_key_complete": not unresolved_top,
                "red_flags_resolved": not pending_red_flags,
                "conflicts_resolved": not conflicts,
                "safety_context_complete": not safety_missing,
                "top_stable": stable_top,
                "margin_stable": stable_margin,
                "margin_sufficient": margin_sufficient,
                "ready_on_two_snapshots": stable_top,
            },
        }
        self.trajectory.append(snapshot)
        return deepcopy(snapshot)

    def snapshot(self):
        return deepcopy(self.trajectory)
