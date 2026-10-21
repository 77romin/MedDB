import unittest
from nova_agent.safety_delivery import complete_fields,complete_sentences,validate_addendum

class DeliveryTests(unittest.TestCase):
    def test_recovers_two_complete_warning_sentences_without_clipping(self):
        text='흉통·숨참·실신·고열 땐 응급실로 가세요. 의식 변화나 심해지는 두근거림도 바로 알려 주세요.'
        sentences=complete_sentences(text)
        self.assertEqual(len(sentences),2)
        self.assertEqual(' '.join(sentences),text)
        self.assertTrue(all(len(s)<=30 for s in sentences))
    def test_never_extracts_an_unterminated_safety_field(self):
        raw='{"diagnosis":"의심돼요.","plan":"검사할게요.","safety":"심한 두통·구토·시'
        self.assertEqual(complete_fields(raw),{'diagnosis':'의심돼요.','plan':'검사할게요.'})
    def test_preserves_negation_and_refuses_overlong_indivisible_warning(self):
        self.assertEqual(complete_sentences('약을 갑자기 끊지 마세요.'),['약을 갑자기 끊지 마세요.'])
        self.assertEqual(complete_sentences('매우 긴 문장이면서 조건과 부정과 대응이 이어져서 제한을 초과하는 단일 문장입니다.'),[])
    def test_rejects_new_dose_unknown_source_or_wrong_status(self):
        note={'P':{'education':'혼자 약을 끊지 않는다.'}}
        base={'status':'needs_clarification','missing':[{'source_field':'education','source_quote':'혼자 약을 끊지 않는다.','messages':['혼자 약을 끊지 마세요.']}]}
        self.assertEqual(validate_addendum(base,note),['혼자 약을 끊지 마세요.'])
        base['missing'][0]['messages']=['하루 5mg 드세요.']
        with self.assertRaises(ValueError):validate_addendum(base,note)
        base['missing'][0]['source_quote']='없는 근거'
        with self.assertRaises(ValueError):validate_addendum(base,note)
