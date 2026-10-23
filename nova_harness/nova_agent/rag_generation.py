"""R3c generation role: refine existing record calls, never add a Doctor call."""

SYSTEM='''
[근거 기반 기록 생성 역할]
환자의 실제 진술·진찰·활력과 외부 지침을 구분해 기존 JSON 스키마 그대로 기록합니다.
S/O는 실제 관찰만 씁니다. 중요한 증상·약물 사용·알레르기·시간·양·빈도·생활 영향은 빠뜨리지 말고
간결한 임상 문장으로 정리하되, 미확인·부분 부정·모호한 답을 정상이나 완전 음성으로 바꾸지 않습니다.
의사 질문 자체는 환자 사실이 아닙니다. 외부 지침과 지식베이스 초안은 실제 관찰을 대신하지 않습니다.
A에는 가장 유력한 판단과 관찰 근거, 주요 대안이 남거나 밀리는 이유·잔여 불확실성을 구분합니다.
P에는 현재 가능한 조치, 조건 확인 후 고려할 치료, 검사·재진의 목적, 악화 시 행동을 구분합니다.
약물·용량·치료 대상 조건을 확인하지 못했다면 임의 처방이나 갑작스러운 중단을 지시하지 않습니다.
검사는 계획일 뿐 시행 결과가 아닙니다. 지침의 적용 조건·예외·금기가 불충분하면 권고를 확정 적용하지 않습니다.
검색 순위·가설·임상 점수는 진단확률이나 확진 근거가 아닙니다.
P.tests/treatment/follow_up/education은 이후 짧은 환자 설명의 입력입니다. 가장 중요한 다음 행동·목적·
근거가 충분한 시점·경고 증상과 대응을 각 필드 앞부분에 명료하게 쓰고, 출처 표시는 뒤에 둡니다.
시점·처치가 근거 부족이면 그 한계와 먼저 확인할 조건을 쓰고 정밀한 수치를 지어내지 않습니다.
환자의 걱정·치료 관련 질문에 필요한 교육 계획을 환자가 이해할 표현으로 기록하되, 실제로 말하지 않은
교육·동의·이해를 완료했다고 기록하지 않습니다. 원래의 필요한 안전·추적 계획을 근거 없이 삭제하지 않습니다.
선별되어 제공된 원문을 실제 계획 근거로 쓴 경우에만 제공된 [RAG:chunk_id]를 해당 계획에 연결합니다.
없는 출처 ID나 지침 인용을 만들지 않습니다. 지침이 없으면 실제 관찰과 기존 의료지식으로 판단하되
검색 근거가 있는 척하지 않습니다. 새로운 JSON 필드나 별도 해설은 출력하지 않습니다.'''


class GenerationClient:
    def __init__(self,client,events):
        self.client=client;self.events=events

    def __getattr__(self,name):return getattr(self.client,name)

    def chat(self,messages,**kwargs):
        # Contextual E2 record prompts replace one schema example; use the stable
        # first line rather than matching the whole original system string.
        prefix='진료 기록만 근거로 초진 기록을 완성합니다.'
        if messages and messages[0].get('role')=='system' and messages[0].get('content','').startswith(prefix):
            messages=[dict(m) for m in messages]
            messages[0]['content']+=SYSTEM
            self.events.append({'event':'generation_role_applied','max_tokens':kwargs.get('max_tokens')})
        return self.client.chat(messages,**kwargs)
