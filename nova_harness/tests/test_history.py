import unittest
from nova_agent.state import PatientState
from nova_agent.records import make_record
from nova_agent.history import history_routes


class HistoryTests(unittest.TestCase):
    def test_unmapped_family_answer_reaches_family_field_without_changed_words(self):
        s=PatientState({}, {})
        s.add_response('SAY','가족 중 같은 질환이 있나요?',{'content':'어머니가 갑상샘저하증이세요.'})
        n,_=make_record(s,{'diagnosis':'평가 중','history_routes':{'fh':['e1']}})
        self.assertIn('어머니가 갑상샘저하증이세요.',n['S']['fh'])
        self.assertNotIn('어머니',n['S']['hpi'])

    def test_invalid_or_ambiguous_routes_do_not_drop_evidence(self):
        s=PatientState({}, {})
        s.add_response('SAY','오늘 복용은요?',{'content':'오늘은 안 먹었지만 평소에는 가끔 먹어요.'})
        s.add_response('EXAM','관찰합니다.',{'result':'반환 결과'})
        routes={'fh':['e1'],'hpi':['e1'],'pmh':['e1','e2','e99',[]]}
        self.assertEqual(history_routes(s,{'history_routes':routes}),{})
        n,_=make_record(s,{'diagnosis':'평가 중','history_routes':routes})
        self.assertIn(s.evidence[0].response,n['S']['hpi'])
        self.assertIn('반환 결과',n['O']['exam'])
        self.assertEqual(n['S']['fh'],'')

    def test_mixed_negation_never_becomes_a_bare_absent_label(self):
        s=PatientState({}, {'mood':{'field':'ros'}})
        s.add_response('SAY','기분은 어떤가요?',{'content':'우울하진 않은데 의욕은 없어요.'})
        s.facts=[{'concept_id':'mood','evidence_id':'e1','assertion':'absent','subject':'patient'}]
        n,_=make_record(s,{'diagnosis':'평가 중'})
        self.assertIn('우울하진 않은데 의욕은 없어요.',n['S']['ros'])
        self.assertNotIn('absent',n['S']['ros'])
        self.assertEqual(s.facts[0]['assertion'],'absent')  # audit source is retained

    def test_same_response_is_not_repeated_for_multiple_extracted_facts(self):
        s=PatientState({}, {'one':{'field':'pmh'},'two':{'field':'pmh'}})
        s.add_response('SAY','복용량은요?',{'content':'밤 3알, 새벽 1알이에요.'})
        s.facts=[{'concept_id':c,'evidence_id':'e1','subject':'patient'} for c in ['one','two']]
        n,_=make_record(s,{'diagnosis':'평가 중'})
        self.assertEqual(n['S']['pmh'].count('밤 3알, 새벽 1알이에요.'),1)

    def test_chief_complaint_requires_exact_initial_quote(self):
        s=PatientState({'opening':'54세 남성. 손목이 아파서 왔습니다.'}, {})
        n,_=make_record(s,{'diagnosis':'평가 중','chief_complaint_quote':'손목이 아파서 왔습니다.'})
        self.assertEqual(n['S']['cc'],'손목이 아파서 왔습니다.')
        self.assertIn('54세',n['S']['hpi'])
        n,_=make_record(s,{'diagnosis':'평가 중','chief_complaint_quote':'발목이 아픕니다.'})
        self.assertEqual(n['S']['cc'],s.initial['opening'])


if __name__=='__main__':unittest.main()
