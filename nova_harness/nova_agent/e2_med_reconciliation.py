"""E2 coverage-only patch for observed sedative use; closing stays upstream."""


def install():
    import meddb.coverage as coverage
    original = coverage.CareCoverage

    class MedicationCoverage(original):
        QUESTIONS = (
            ("med_strength", "그 약 한 알은 몇 mg인가요?"),
            ("med_last_taken", "그 약을 마지막으로 언제 몇 알 드셨나요?"),
            ("med_total_24h", "지난 24시간에 모두 몇 알 드셨나요?"),
            ("med_sources", "수면제는 몇 군데에서 처방받으시나요?"),
            ("other_sedatives", "다른 수면유도제나 진정제도 드시나요?"),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.extra.update({key: (question, "pmh") for key, question in self.QUESTIONS})

        def needed(self, kb):
            actions = super().needed(kb)
            if self.complaint != "insomnia" or "hypnotic_use" not in kb.present:
                return actions
            added = []
            for index, (target, question) in enumerate(self.QUESTIONS):
                if target in self.records or self.attempts.get(target, 0) >= 2:
                    continue
                added.append({
                    "type": "SAY", "text": question, "target": target, "resolves": [],
                    "priority": 0.1 + index / 100,
                    "why": "확인된 수면제의 노출량·처방·병용 안전 확인",
                })
            return sorted(actions + added, key=lambda action: action["priority"])

    coverage.CareCoverage = MedicationCoverage
    return original


def restore(original):
    import meddb.coverage as coverage
    coverage.CareCoverage = original
