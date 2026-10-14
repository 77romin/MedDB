"""Clinical coverage from the complaint and observed facts, never a sample ID or answer."""


class CareCoverage:
    def __init__(self, db, complaint, age, sex):
        self.db, self.complaint, self.age, self.sex = db, complaint, age, sex
        self.records = {}
        self.attempts = {}
        self.extra = {
            'impact': ('일상생활에서 어떤 점이 힘드세요?', 'hpi'),
            'med_name': ('복용하는 약 이름을 알려 주세요.', 'pmh'),
            'med_schedule': ('그 약을 하루에 얼마나 드세요?', 'pmh'),
            'med_duration': ('그 약을 얼마나 오래 드셨나요?', 'pmh'),
            'sleep_latency': ('누우면 잠들기까지 얼마나 걸리나요?', 'hpi'),
            'sleep_hours': ('하루에 실제로 몇 시간 주무세요?', 'hpi'),
            'sleep_frequency': ('한 주에 며칠 잠을 못 주무세요?', 'hpi'),
            'caffeine': ('커피나 에너지음료는 얼마나 드세요?', 'sh'),
            'birth_weight': ('아이가 태어날 때 몸무게는 얼마였나요?', 'hpi'),
            'birth_term': ('아이가 몇 주에 태어났나요?', 'hpi'),
            'nutrition': ('아이는 평소 식사를 잘 하나요?', 'hpi'),
            'chronic_gi': ('아이에게 오래 지속된 설사가 있나요?', 'hpi'),
            'parent_father': ('아버지 키는 얼마인가요?', 'fh'),
            'parent_mother': ('어머니 키는 얼마인가요?', 'fh'),
            'pregnancy': ('현재 임신 가능성이 있나요?', 'hpi'),
            'breastfeeding': ('현재 수유 중이신가요?', 'hpi'),
            'eye_change': ('눈이 불편하거나 시력이 변했나요?', 'hpi'),
            'supplements': ('건강보조제나 한약을 드시나요?', 'pmh'),
        }

    def observe(self, target, question, answer, turn):
        if target:
            self.records[target] = {'question': question, 'answer': answer, 'turn': turn}
            if target == 'chronic_illness':
                # This is the same long-term illness question as the generic pmh slot.
                self.records['pmh'] = self.records[target]

    def allow_action(self, kb, kind, text, target):
        if kind == 'EXAM' and target == 'ex_tanner' and self.complaint == 'short_stature' and (self.age is None or self.age < 10):
            return False
        if target and target in self.records:
            return False
        if kind == 'EXAM' and target in kb.exams_done:
            return False
        return True

    def needed(self, kb):
        db = self.db
        items = db.items[self.complaint] if self.complaint else {'slot': ['onset', 'course'], 'finding': [], 'exam': []}
        out = []
        for fid in sorted(kb.conflicts):
            repeat = db._action(fid, 'discriminate', '상충 진술 재확인')
            if repeat and self.attempts.get(repeat['target'], 0) < 2:
                out.append(dict(repeat, priority=-1))
        def add(target, priority, why):
            if target in self.records or target in kb.asked or target in kb.present or target in kb.absent:
                return
            if self.attempts.get(target, 0) >= 2:
                return
            if target in self.extra:
                action = {'type': 'SAY', 'text': self.extra[target][0], 'target': target, 'resolves': []}
            else:
                row = db.slots.get(target) or db.findings.get(target) or {}
                if not db._fits(row, self.age, self.sex):
                    return
                if target in db.exams and target in kb.exams_done:
                    return
                action = db._action(target, 'core', why)
            if action:
                actual = action['target']
                if actual in self.records or actual in kb.exams_done or self.attempts.get(actual, 0) >= 2:
                    return
                action = dict(action, priority=priority, why=why)
                if self.complaint == 'short_stature' and self.age is not None and self.age < 18:
                    pediatric = {'pmh':'아이가 앓는 지병이 있나요?', 'meds':'아이가 먹고 있는 약이 있나요?',
                                 'allergy':'아이에게 약이나 음식 알레르기가 있나요?'}
                    action['text'] = pediatric.get(target, action['text'])
                if not any(a['type']==action['type'] and a['text']==action['text'] for a in out):
                    out.append(action)
        flags = db.red_flags_pending(self.complaint, kb.present, kb.absent, kb.exams_done, self.age, self.sex) if self.complaint else []
        for flag in flags:
            for fid in flag['unchecked']:
                add(fid, 0, '위험 원인 확인: ' + flag['ko'])
        for sid in items['slot']:
            # Parent heights are separate questions so a short answer cannot resolve both.
            if sid != 'parent_height': add(sid, 1, '현병력')
        add('impact', 1, '생활 영향')
        for fid in items['finding']:
            add(fid, 2, '주호소 핵심 소견')
        for item in ('pmh', 'meds', 'allergy', 'family'):
            add(item, 3, '기본 병력·처치 안전')
        if self.complaint == 'insomnia':
            for fid in ('sleep_latency', 'sleep_hours', 'sleep_frequency', 'caffeine', 'heavy_alcohol'):
                add(fid, 2, '수면 평가')
            if 'hypnotic_use' in kb.present:
                for fid in ('med_name', 'med_schedule', 'med_duration'):
                    add(fid, 1, '실제 수면제 복용 확인')
        if self.complaint == 'short_stature':
            for fid in ('parent_father', 'parent_mother', 'birth_weight', 'birth_term', 'nutrition', 'chronic_gi'):
                add(fid, 2, '성장 경과와 다른 원인')
        if self.complaint == 'weight_loss':
            for fid in ('course', 'eye_change', 'supplements'):
                add(fid, 2, '체중 변화와 치료 조건')
            if self.sex == 'F' and self.age is not None and 12 <= self.age <= 55:
                for fid in ('pregnancy', 'breastfeeding'):
                    add(fid, 3, '검사·치료 전 조건 확인')
        for eid in items['exam']:
            # Puberty staging is not a routine test for a young child's short stature.
            if eid == 'ex_tanner' and (self.age is None or self.age < 10): continue
            add(eid, 4, '주호소 신체진찰')
        for kind, fid in db.background:
            add(fid, 5, '과거력·사회력')
        return sorted(out, key=lambda a: a['priority'])

    def append_record(self, note):
        for target, row in self.records.items():
            if target in self.extra:
                field = self.extra[target][1]
                line = f"{row['question']} → 환자 답: {row['answer']} (턴 {row['turn']})"
                note['S'][field] = (note['S'][field].rstrip() + '\n' + line).strip()

    def trace(self):
        return {'successful_response_count': len(self.records), 'responses': self.records, 'attempts': self.attempts}
