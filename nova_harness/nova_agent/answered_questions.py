"""Exact-question guard using actual successful coverage observations only."""
import re
import unicodedata


def question_key(text):
    text=unicodedata.normalize('NFC',text)
    text=re.sub(r'^많이 힘드셨겠어요\.\s*','',text)
    return re.sub(r'\s+','',text)


def answered(answer):
    return bool(answer.strip()) and not re.search(r'무슨\s*(뜻|말)|다시\s*(말|질문)|못\s*들|잘\s*모르|모르겠|대답.*어려',answer)


def install(events):
    from meddb.coverage import CareCoverage
    observe,needed,allow=CareCoverage.observe,CareCoverage.needed,CareCoverage.allow_action
    def remember(self,target,question,answer,turn):
        observe(self,target,question,answer,turn)
        if (target or '?' in question) and answered(answer):
            if not hasattr(self,'_answered_exact'):self._answered_exact={}
            self._answered_exact[question_key(question)]={'answer':answer,'turn':turn}
    def duplicate(self,kb,text,target):
        # Conflicts justify a distinct clarification, not replaying an answered
        # identical question. Keep the original observation unresolved.
        return question_key(text) in getattr(self,'_answered_exact',{})
    def candidates(self,kb):
        result=[]
        for item in needed(self,kb):
            if item['type']=='SAY' and duplicate(self,kb,item['text'],item.get('target')):
                events.append({'event':'answered_question_filtered','stage':'required'})
            else:result.append(item)
        return result
    def allowed(self,kb,kind,text,target):
        if kind=='SAY' and duplicate(self,kb,text,target):
            events.append({'event':'answered_question_filtered','stage':'generated'})
            return False
        return allow(self,kb,kind,text,target)
    CareCoverage.observe,CareCoverage.needed,CareCoverage.allow_action=remember,candidates,allowed
    return observe,needed,allow


def restore(original):
    from meddb.coverage import CareCoverage
    CareCoverage.observe,CareCoverage.needed,CareCoverage.allow_action=original
