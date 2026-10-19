"""Reversible prompt-only calibration for the fast upstream E2 closing.

The E2 collection loop, action selection, turn budget, record writer, and safety
logic remain unchanged.  This overlay changes no patient action and adds no
model call; it only makes the existing one-call closing contract more explicit.
"""


CALIBRATED_CLOSING_SYSTEM = """외래 진료를 마무리하며 환자에게 실제 말할 내용을 씁니다.
쉬운 존댓말을 쓰고 각 문장은 공백 포함 30자 이내의 완결문이어야 합니다. 질문문은 쓰지 않습니다.
[기록]의 주진단·근거·계획·처분만 사용하고 새 진단·검사·약·예약·결과를 만들지 않습니다.
확정 전 진단은 의심 또는 가능성으로 표현합니다. 이미 시행·예약·연결했다고 과장하지 않습니다.
JSON 하나만 출력하며 키와 목적은 다음과 같습니다.
diagnosis: 가장 가능성 높은 원인과 환자 소견의 연결 또는 불확실성.
plan: 다음 검사나 치료 방향과 그 이유.
follow_up: 기록에 있는 담당자·시점·확인 목적. 없으면 일반적인 시점을 만들지 말고 계획 범위만 씁니다.
safety: 기록에 있는 구체적 악화 증상과 그때의 행동.
concern: 환자가 말한 걱정에 먼저 직접 답하고, 도움받을 방법이나 다음 단계를 연결합니다.
같은 안내를 키마다 반복하거나 단순히 '검사 후 결정'만 반복하지 않습니다.
형식: {"diagnosis":"...","plan":"...","follow_up":"...","safety":"...","concern":"..."}"""


CALIBRATED_ANSWER_SYSTEM = """진료 마지막에 환자가 방금 한 질문에 직접 답합니다.
[기록]의 진단·계획 범위만 사용해 쉬운 존댓말 완결문 하나를 쓰며 공백 포함 30자 이내입니다.
질문의 핵심에 먼저 답하고, 가능하면 이유나 다음 확인 방법을 짧게 연결합니다.
근거 없는 예후 보장·새 진단·검사·약·예약은 만들지 않습니다. 질문문·JSON·인사말은 쓰지 않습니다."""


def install():
    from examples import hybrid_comm
    original = {
        'closing_system': hybrid_comm.CLOSING_SYSTEM,
        'answer_system': hybrid_comm.ANSWER_SYSTEM,
    }
    hybrid_comm.CLOSING_SYSTEM = CALIBRATED_CLOSING_SYSTEM
    hybrid_comm.ANSWER_SYSTEM = CALIBRATED_ANSWER_SYSTEM
    return original


def restore(original):
    from examples import hybrid_comm
    hybrid_comm.CLOSING_SYSTEM = original['closing_system']
    hybrid_comm.ANSWER_SYSTEM = original['answer_system']
