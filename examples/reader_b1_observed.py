"""B1-compatible observation boundary, without extra model calls.

Raw question/answer pairs remain in B1's transcript. Only an unambiguous single
current-patient question may inherit a bare yes/no. This is conservative lexical
interpretation, not a clinical completeness or semantic accuracy guarantee.
"""
import re
import unicodedata
from examples import reader_g as G

FAMILY = re.compile(r"가족|어머니|아버지|부모|형제|자매|할머니|할아버지|남편|아내")
PAST = re.compile(r"예전에|과거에는|어릴 때|어렸을 때|지금은|이제는")
QUALIFIED = re.compile(r"거의.*없|자주.*(?:아니|않)|하지만|그런데|다만|때만|경우에만")
YES = re.compile(r"(?:네|예|응|맞아요|있어요|있습니다)(?:[, .!]*(?:있어요|있습니다|맞아요))?[ .!]*")
NO = re.compile(r"(?:아니요|아뇨|없어요|없습니다)(?:[, .!]*(?:없어요|없습니다))?[ .!]*")


def install(db):
    G.install(db)


def observe(kb, db, question, answer, turn):
    q = unicodedata.normalize('NFC', question or '')
    a = unicodedata.normalize('NFC', answer or '').strip()
    if not hasattr(kb, 'b1_observations'):
        kb.b1_observations = []
    row = {'question': q, 'answer': a, 'turn': turn, 'links': [], 'status': 'raw_only'}
    kb.b1_observations.append(row)
    asked = db.match_findings(q)
    qids = list(dict.fromkeys(asked['present'] + asked['absent']))
    canonical = [fid for fid, item in db.findings.items()
                 if item.get('ask') and G.A.norm(item['ask']) == G.A.norm(q)]
    if len(canonical) == 1:
        qids = canonical
    explicit = db.match_findings(a)
    # Do not turn a family/past/qualified statement into current binary findings.
    # Clinical history slots continue to be available verbatim to the writer.
    scoped = FAMILY.search(q + ' ' + a) or PAST.search(q + ' ' + a) or QUALIFIED.search(a)
    if scoped or G.UNSURE.search(a) or '하나씩' in a:
        row['status'] = 'scoped_or_uncertain'
        return
    mentioned = explicit['present'] + explicit['absent'] + explicit['unknown']
    if mentioned:
        for verdict, name in (('+', 'present'), ('-', 'absent'), ('?', 'unknown')):
            for fid in explicit[name]:
                kb.mark(fid, verdict, turn, q + ' → ' + a, 'b1_observed_explicit')
                row['links'].append({'id': fid, 'verdict': verdict})
        row['status'] = 'explicit'
        return
    verdict = '+' if YES.fullmatch(a) else '-' if NO.fullmatch(a) else None
    if verdict and len(qids) == 1:
        fid = qids[0]
        kb.mark(fid, verdict, turn, q + ' → ' + a, 'b1_observed_qa')
        row['links'].append({'id': fid, 'verdict': verdict})
        row['status'] = 'single_question_link'
    elif verdict:
        row['status'] = 'ambiguous_question'
