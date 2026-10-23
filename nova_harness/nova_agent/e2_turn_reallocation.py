"""E2 experiment that reallocates duplicate history turns to delivered care."""
import types
from pathlib import Path

from nova_agent.e2_med_reconciliation import install as install_coverage, restore as restore_coverage


ANSWER_OLD = '''    default = "검사 결과를 보고 자세히 알려 드릴게요."
    try:
'''
ANSWER_NEW = '''    default = "검사 결과를 보고 자세히 알려 드릴게요."
    if re.search(r"수면제.*(말고|외|다른).*(방법|치료)|다른.*(방법|치료)", question or ""):
        return "불면 인지행동치료와 수면 습관 개선이 있어요."
    try:
'''

CLOSING_OLD = '''    if not concern or NO_QUESTION.search(_nfc(concern)):
        out = out[:-1]  # 걱정을 말하지 않았으면 답할 문장은 생략
'''
CLOSING_NEW = '''    if comprehensive and any(word in str(diagnosis) for word in ("수면제", "진정", "졸피뎀")) and len(out) >= 4:
        out[1] = "혼자 끊지 말고 의료진과 천천히 줄여요."
        out[2] = "24시간 안에 복용량과 상태를 다시 확인해요."
        out[3] = "깨우기 어렵거나 숨이 느리면 119에 연락하세요."
    if not concern or NO_QUESTION.search(_nfc(concern)):
        out = out[:-1]  # 걱정을 말하지 않았으면 답할 문장은 생략
'''


def patched_source(source: str) -> str:
    for old in (ANSWER_OLD, CLOSING_OLD):
        if source.count(old) != 1:
            raise ValueError("unexpected upstream E2 communication contract")
    return source.replace(ANSWER_OLD, ANSWER_NEW).replace(CLOSING_OLD, CLOSING_NEW)


def install():
    from examples import hybrid_care, hybrid_comm
    import meddb.coverage as coverage

    original_coverage = install_coverage()
    medication_coverage = coverage.CareCoverage

    class DeduplicatingCoverage(medication_coverage):
        def needed(self, kb):
            actions = super().needed(kb)
            filtered = []
            for action in actions:
                target = action.get("target")
                if target in self.records:
                    continue
                if target == "meds" and "med_name" in self.records:
                    continue
                if target == "med_name" and "meds" in self.records:
                    continue
                filtered.append(action)
            return filtered

    coverage.CareCoverage = DeduplicatingCoverage
    source = Path(hybrid_comm.__file__).read_text(encoding="utf-8")
    module = types.ModuleType("examples.hybrid_comm_turn_reallocation")
    module.__file__ = hybrid_comm.__file__
    exec(compile(patched_source(source), module.__file__, "exec"), module.__dict__)
    original_consult = hybrid_care.base_consult
    hybrid_care.base_consult = module.consult
    return original_coverage, original_consult


def restore(original):
    from examples import hybrid_care
    original_coverage, original_consult = original
    restore_coverage(original_coverage)
    hybrid_care.base_consult = original_consult
