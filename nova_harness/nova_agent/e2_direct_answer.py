"""One-factor E2 experiment: make the existing final answer direct."""

DIRECT_ANSWER_SUFFIX = "\n기록에 답이 있으면 질문에 먼저 직접 답하고 검사 후로 미루지 마세요."


def install():
    from examples import hybrid_comm
    original = hybrid_comm.ANSWER_SYSTEM
    hybrid_comm.ANSWER_SYSTEM = original + DIRECT_ANSWER_SUFFIX
    return original


def restore(original):
    from examples import hybrid_comm
    hybrid_comm.ANSWER_SYSTEM = original
