"""One-factor E2 experiment: make the existing final answer direct."""

DIRECT_ANSWER_SUFFIX = "\n환자 질문의 핵심에 먼저 직접 답하세요."


def install():
    from examples import hybrid_comm
    original = hybrid_comm.ANSWER_SYSTEM
    hybrid_comm.ANSWER_SYSTEM = original + DIRECT_ANSWER_SUFFIX
    return original


def restore(original):
    from examples import hybrid_comm
    hybrid_comm.ANSWER_SYSTEM = original
