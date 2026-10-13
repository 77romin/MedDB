"""NOVA agent integration helper; not a complete Doctor Agent or submission run.py."""
from meddb import KB


def prepare_knowledge():
    return KB()


def knowledge_tools(kb, observations, patient=None, profile='research', guideline_query=None):
    """Call after the agent has confirmed observations from patient responses."""
    result=kb.suggest(observations,profile=profile,patient=patient,limit=5)
    output = {
        'version':result['version'],
        'data_sha256':result['sha256'],
        'policy':result['policy'],
        'score_method':result['ranking']['score_method'],
        'warnings':result['ranking']['warnings'],
        'candidates':[{
            'id':c['disease']['id'],'name':c['disease']['label_ko'],
            'rank':c['rank'],'evidence_score':c['score'],
            'support':c['matched'],'counter_evidence':c['conflicts'],
            'evidence':[{'assertion_id':a['id'],'source_id':a['source_id'],'locator':a['locator'],'context':a['context']} for a in c['evidence']]
        } for c in result['ranking']['candidates'][:5]],
        'next_actions':result['recommendations'],
        'checklists':result['checklists'],
        'interpretation':'Evidence is general medical knowledge, not facts observed in this patient. Scores are not probabilities.'
    }
    if guideline_query:
        output['guidelines']=kb.guidelines(guideline_query,limit=2)
    return output
