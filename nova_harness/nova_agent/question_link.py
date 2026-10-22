"""Conservative question identity: preserve predicate, time, negation and subject.

This is finite grammar normalization, not semantic medical inference. Unknown,
compound, historically scoped or non-unique paraphrases abstain. Original exact
canonical matches are retained by the caller before this fallback is attempted.
"""
from collections import defaultdict
import hashlib
import re
import unicodedata

ENDINGS=(('있나요','있으세요','있습니까','있으신가요'),
         ('없나요','없으세요','없습니까','없으신가요'),
         ('되나요','됩니까','되시나요'),
         ('드세요','드시나요','드십니까'),
         ('하나요','하시나요','하십니까'))
COMPOUND=re.compile(r'[·/,;]|그리고|또는|거나|\s및\s|하고\s.*(?:나요|세요|니까)')
HISTORICAL=re.compile(r'(?:된|한|온|간|있던|없던)\s*적|예전|과거|이전에|어릴|어렸')


def signature(text):
    text=unicodedata.normalize('NFC',str(text)).strip()
    return re.sub(r'\s+','',text.rstrip('?？.!。！'))


def variants(question):
    base=signature(question)
    values={base}
    for group in ENDINGS:
        for ending in group:
            if base.endswith(ending):
                stem=base[:-len(ending)]
                values.update(stem+other for other in group)
    # Explicit present-duration paraphrases. Never erase duration or "ever".
    if base.endswith('계속되나요'):
        values.add(base[:-len('계속되나요')]+'계속되고있나요')
    return values


class QuestionIndex:
    def __init__(self,db,extra,age,sex):
        self.by_variant=defaultdict(set)
        self.exact=defaultdict(set)
        self.eligible=set()
        for target,row in {**db.slots,**db.findings}.items():
            question=row.get('ask')
            if not question or not db._fits(row,age,sex):continue
            self.add(target,question)
        for target,(question,_) in extra.items():
            self.add(target,question)

    def add(self,target,question):
        self.eligible.add(target)
        self.exact[signature(question)].add(target)
        for value in variants(question):self.by_variant[value].add(target)

    def resolve(self,text):
        normalized=unicodedata.normalize('NFC',str(text)).strip()
        if normalized.count('?')+normalized.count('？')!=1 or not normalized.endswith(('?','？')):
            return None,'not_single_question'
        if COMPOUND.search(normalized):return None,'compound'
        if HISTORICAL.search(normalized):return None,'historical_scope'
        matches=self.by_variant.get(signature(normalized),set())
        if len(matches)!=1:return None,'ambiguous' if matches else 'unmapped'
        target=next(iter(matches))
        # Even a variant of A cannot override an exact canonical question for B.
        exact=self.exact.get(signature(normalized),set())
        if exact and exact!={target}:return None,'ambiguous'
        return target,'canonical' if exact else 'bounded_variant'


def propose(care,text,events):
    if not hasattr(care,'_question_index'):
        # Extra complaint-specific questions are already sent canonically by the
        # required queue. Do not broaden their age/complaint eligibility here.
        care._question_index=QuestionIndex(care.db,{},care.age,care.sex)
    target,reason=care._question_index.resolve(text)
    digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
    events.append({'event':'question_link_proposed' if target else 'question_link_abstained',
                   'target':target,'reason':reason,'question_sha256':digest})
    if target:
        care._pending_question_links[(target,signature(text))]={'reason':reason,'question_sha256':digest}
    return target
