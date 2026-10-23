import unittest

from nova_sdk import empty_record
from nova_agent.e2_evidence_ledger import EvidenceLedger
from nova_agent.e2_soap_audit import audit
from nova_agent.e2_soap_router import reconcile
from nova_agent.e2_tracking_client import TrackingClient


class FakeClient:
    def __init__(self):
        self.turn = 0
        self.submitted = None

    def say(self, content, **kwargs):
        self.turn += 1
        return {"turn": self.turn, "content": f"답변 {self.turn}: {content}"}

    def exam(self, content, **kwargs):
        self.turn += 1
        return {"turn": self.turn, "result": f"진찰 {self.turn}: 정상 아님"}

    def diagnose(self, *, note, diagnosis, **kwargs):
        self.submitted = note
        return {"status": "OK"}


class E2EvidenceLedgerTests(unittest.TestCase):
    def test_first_turn_survives_forty_five_turns(self):
        base = FakeClient()
        ledger = EvidenceLedger()
        client = TrackingClient(base, ledger)
        for index in range(44):
            client.say(f"증상 {index+1}은 어떤가요?")
        client.exam("복부 촉진")
        client.diagnose(note=empty_record(), diagnosis="진단")
        self.assertIn("답변 1: 증상 1은 어떤가요?", base.submitted["S"]["hpi"])
        self.assertIn("진찰 45: 정상 아님", base.submitted["O"]["exam"])
        self.assertEqual(len(ledger.entries), 45)
        self.assertEqual(audit(base.submitted, ledger)["unresolved"], [])

    def test_annotation_routes_medication_to_pmh(self):
        ledger = EvidenceLedger()
        entry = ledger.record("SAY", "드시고 있는 약은?", {"turn": 2, "content": "암로디핀을 먹어요."})
        ledger.annotate(2, "드시고 있는 약은?", "meds", "pmh")
        note = reconcile(empty_record(), ledger)
        self.assertIn("암로디핀", note["S"]["pmh"])
        self.assertEqual(entry.disposition, "included")

    def test_duplicate_and_conflict_are_explicit(self):
        ledger = EvidenceLedger()
        first = ledger.record("SAY", "열이 있나요?", {"turn": 1, "content": "없어요."})
        duplicate = ledger.record("SAY", "열이 있나요?", {"turn": 2, "content": "없어요."})
        conflict = ledger.record("SAY", "열이 있나요?", {"turn": 3, "content": "지금은 있어요."})
        for entry in ledger.entries:
            entry.target = "fever"
        note = reconcile(empty_record(), ledger)
        self.assertEqual(duplicate.disposition, "duplicate")
        self.assertEqual(first.disposition, "conflict")
        self.assertEqual(conflict.disposition, "conflict")
        self.assertIn("없어요", note["S"]["hpi"])
        self.assertIn("지금은 있어요", note["S"]["hpi"])

    def test_acknowledgement_is_disposed_without_entering_history(self):
        ledger = EvidenceLedger()
        entry = ledger.record("SAY", "이해하셨나요?", {"turn": 1, "content": "네, 알겠습니다."})
        note = reconcile(empty_record(), ledger)
        self.assertEqual(entry.disposition, "nonclinical")
        self.assertNotIn("알겠습니다", note["S"]["hpi"])

    def test_teach_back_is_kept_in_education_not_hpi(self):
        ledger = EvidenceLedger()
        entry = ledger.record("SAY", "집에서 어떻게 하실지 말씀해 주시겠어요?",
                              {"turn": 45, "content": "약은 확인받고 감량을 상의할게요."})
        note = reconcile(empty_record(), ledger)
        self.assertEqual(entry.disposition, "included")
        self.assertIn("이해 확인 응답", note["P"]["education"])
        self.assertNotIn("감량", note["S"]["hpi"])

    def test_patient_question_is_kept_as_communication(self):
        ledger = EvidenceLedger()
        ledger.record("SAY", "더 궁금하신 점 있으세요?",
                      {"turn": 43, "content": "수면제 말고 다른 방법도 있나요?"})
        note = reconcile(empty_record(), ledger)
        self.assertIn("환자 질문", note["P"]["education"])
        self.assertNotIn("수면제 말고", note["S"]["hpi"])

    def test_question_after_explanation_is_not_discarded(self):
        ledger = EvidenceLedger()
        entry = ledger.record("SAY", "검사로 원인을 확인할게요.",
                              {"turn": 37, "content": "검사로 확인할 수 있나요?"})
        note = reconcile(empty_record(), ledger)
        self.assertEqual(entry.reason, "P.education 의사소통 근거")
        self.assertIn("환자 질문", note["P"]["education"])

    def test_safety_commitment_is_education_evidence_not_history(self):
        ledger = EvidenceLedger()
        ledger.record("SAY", "경련이나 호흡 이상 땐 응급실로 가세요.",
                      {"turn": 41, "content": "네, 그럴 땐 응급실로 갈게요."})
        note = reconcile(empty_record(), ledger)
        self.assertIn("안전계획 확인", note["P"]["education"])
        self.assertNotIn("응급실로 갈게요", note["S"]["hpi"])

    def test_planned_and_delivered_education_are_separated(self):
        ledger = EvidenceLedger()
        note = empty_record()
        note["P"]["education"] = ("술을 피하도록 교육함. | "
                                  "환자에게 설명함: 약을 임의로 끊지 마세요.")
        repaired = reconcile(note, ledger)
        self.assertIn("교육 계획(실제 전달 여부 미확인)", repaired["P"]["education"])
        self.assertIn("실제 전달 근거", repaired["P"]["education"])
        self.assertTrue(audit(repaired, ledger)["education_plan_separated"])


if __name__ == "__main__":
    unittest.main()
