"""Reversible E2 overlay that ranks the next action by clinical decision value."""

TREATMENT_SAFETY = {
    "meds", "allergy", "pregnancy", "breastfeeding", "med_name",
    "med_schedule", "med_duration", "med_strength", "med_last_taken",
    "med_total_24h", "med_sources", "other_sedatives",
}
MEDICATION_QUESTIONS = (
    ("med_strength", "그 약 한 알은 몇 mg인가요?"),
    ("med_last_taken", "그 약을 마지막으로 언제 몇 알 드셨나요?"),
    ("med_total_24h", "지난 24시간에 모두 몇 알 드셨나요?"),
    ("med_sources", "수면제는 몇 군데에서 처방받으시나요?"),
    ("other_sedatives", "다른 수면유도제나 진정제도 드시나요?"),
)


def _value(action, kb):
    target = action.get("target", "")
    why = action.get("why", "")
    if target in kb.conflicts:
        return 120
    if why.startswith("위험 원인 확인"):
        return 110

    ranked = kb.ranked(k=4)
    top_key = set(ranked[0].get("unknown_key", [])) if ranked else set()
    other_key = {fid for row in ranked[1:3] for fid in row.get("unknown_key", [])}
    if target in top_key:
        return 100
    if target in other_key:
        return 80
    if target in TREATMENT_SAFETY:
        return 95
    if action.get("type") == "EXAM":
        return 70
    if why in {"주호소 핵심 소견", "현병력", "수면 평가", "성장 경과와 다른 원인"}:
        return 60
    if why in {"생활 영향", "체중 변화와 치료 조건"}:
        return 55
    if why == "기본 병력·처치 안전":
        return 45
    if why == "과거력·사회력":
        return 20
    return 30


def install():
    import meddb.coverage as coverage

    original = coverage.CareCoverage

    class ValueCoverage(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.extra.update({target: (question, "pmh") for target, question in MEDICATION_QUESTIONS})

        def needed(self, kb):
            actions = super().needed(kb)
            if getattr(self, "complaint", None) == "insomnia" and "hypnotic_use" in kb.present:
                for index, (target, question) in enumerate(MEDICATION_QUESTIONS):
                    if target in self.records or self.attempts.get(target, 0) >= 2:
                        continue
                    actions.append({
                        "type": "SAY", "target": target, "text": question, "resolves": [],
                        "priority": 1 + index / 100,
                        "why": "확인된 수면제의 노출량·처방·병용 안전 확인",
                    })
            unique = []
            seen = set()
            for action in actions:
                key = (action.get("type"), action.get("target") or action.get("text"))
                if key in seen:
                    continue
                if action.get("target") == "meds" and "med_name" in self.records:
                    continue
                if action.get("target") == "med_name" and "meds" in self.records:
                    continue
                seen.add(key)
                item = dict(action)
                item["decision_value"] = _value(item, kb)
                unique.append(item)
            return sorted(unique, key=lambda item: (-item["decision_value"], item.get("priority", 99)))

    coverage.CareCoverage = ValueCoverage
    return original


def restore(original):
    import meddb.coverage as coverage
    coverage.CareCoverage = original
