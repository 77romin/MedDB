"""Focused E2 experiment: reconcile sedatives and make safety advice observable."""

from nova_agent.e2_med_reconciliation import install as install_coverage, restore as restore_coverage


DIRECT_SUFFIX = "\n기록에 답이 있으면 질문에 먼저 직접 답하고 검사 후로 미루지 마세요."


def install():
    from examples import hybrid_comm

    original_coverage = install_coverage()
    original_closing = hybrid_comm._closing_sentences
    original_answer = hybrid_comm.ANSWER_SYSTEM

    def safety_closing(client, db, note, diagnosis, concern, comprehensive=False):
        sentences = original_closing(client, db, note, diagnosis, concern, comprehensive)
        if comprehensive and any(word in str(diagnosis) for word in ("수면제", "진정", "졸피뎀")):
            # These replace vague generated follow-up/safety slots. They are actual
            # patient speech, not claims added only to the submitted record.
            if len(sentences) >= 4:
                sentences[2] = "추가 수면제·술·직접 운전은 피하세요."
                sentences[3] = "깨우기 어렵거나 숨이 느리면 119에 연락하세요."
        return sentences

    hybrid_comm._closing_sentences = safety_closing
    hybrid_comm.ANSWER_SYSTEM = original_answer + DIRECT_SUFFIX
    return original_coverage, original_closing, original_answer


def restore(original):
    from examples import hybrid_comm

    original_coverage, original_closing, original_answer = original
    restore_coverage(original_coverage)
    hybrid_comm._closing_sentences = original_closing
    hybrid_comm.ANSWER_SYSTEM = original_answer
