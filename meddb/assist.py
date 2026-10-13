"""Versioned agent contract with caller-confirmed evidence provenance."""
from .workflow import profile_kb
from .pathways import recommend

CONTRACT_VERSION='nova-knowledge-contract-1'


def assist(kb, observations, events, patient=None, patient_evidence=None, history=None, profile='reviewed', phase='preliminary', limit=5):
    if phase not in {'preliminary','final'} or type(limit) is not int or not 1<=limit<=10:raise ValueError('Invalid phase/limit')
    if not isinstance(events,list) or len(events)>128:raise ValueError('Events must be a list of at most 128')
    indexed={}
    for event in events:
        if not isinstance(event,dict) or set(event)-{'id','kind','turn','content'}:raise ValueError('Invalid event fields')
        if not isinstance(event.get('id'),str) or not event['id'] or len(event['id'])>100 or event['id'] in indexed:raise ValueError('Invalid/duplicate event ID')
        if event.get('kind') not in {'initial','say','exam','test'} or not isinstance(event.get('content'),str) or not event['content'].strip() or len(event['content'])>2000:raise ValueError('Only provided initial or successful action results are evidence')
        turn=event.get('turn')
        if type(turn) is not int or not 0<=turn<=50 or (event['kind']=='initial')!=(turn==0):raise ValueError('Invalid event turn')
        if phase=='preliminary' and event['kind']=='test':raise ValueError('Preliminary phase does not provide test results')
        indexed[event['id']]=event

    def bindings(ids):
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in indexed for i in ids) or len(set(ids))!=len(ids):raise ValueError('Known facts need unique existing evidence IDs')

    if not isinstance(observations,list) or len(observations)>100:raise ValueError('Invalid observations')
    states={};provenance=[]
    for item in observations:
        if not isinstance(item,dict) or set(item)-{'finding_id','state','evidence_ids'}:raise ValueError('Invalid observation fields')
        finding=item.get('finding_id');state=item.get('state')
        if not isinstance(finding,str) or finding in states or state not in {'present','absent','unknown'}:raise ValueError('Duplicate or invalid observation')
        ids=item.get('evidence_ids',[])
        if state!='unknown' or ids:bindings(ids)
        states[finding]=state
        provenance.append({'finding_id':finding,'state':state,'evidence_ids':ids,'confirmation':'caller_confirmed' if state!='unknown' else 'unconfirmed'})
    patient={} if patient is None else patient
    patient_evidence={} if patient_evidence is None else patient_evidence
    if not isinstance(patient,dict) or not isinstance(patient_evidence,dict) or set(patient_evidence)-set(patient):raise ValueError('Invalid patient evidence')
    for field,value in patient.items():
        if value is not None and value!='unknown':bindings(patient_evidence.get(field))
    history={} if history is None else history
    if not isinstance(history,dict):raise ValueError('Invalid history')
    for item in history.values():
        if not isinstance(item,dict):raise ValueError('Invalid history record')
        if item.get('status') in {'confirmed','not_applicable'}:bindings([item.get('evidence_id')])
    view,policy=profile_kb(kb,profile)
    # suggest validates observation IDs, patient conditions and ranking arguments.
    result=view.suggest(states,profile,patient=patient,limit=limit)
    paths=recommend(view,states,history,policy['include_draft'])

    def evidence(rows):
        return [{'assertion_id':a['id'],'source_id':a['source_id'],'source_url':kb.sources[a['source_id']]['url'],'locator':a['locator'],'review_status':a['review_status'],'context_excerpt':a['context'][:300],'context_truncated':len(a['context'])>300} for a in rows[:4]]

    candidates=[]
    for c in result['ranking']['candidates'][:limit]:
        candidates.append({'id':c['disease']['id'],'label':c['disease']['label_ko'],'rank':c['rank'],'evidence_score':c['score'],'support':c['matched'],'counter_evidence':c['conflicts'],'uncertain':c['uncertain'],'evidence':evidence(c['evidence']),'omitted_evidence_count':max(0,len(c['evidence'])-4)})
    next_actions=[]
    for row in result['recommendations']:
        refs=[{'assertion_id':a['assertion_id'],'source_id':a['source_id'],'source_url':kb.sources[a['source_id']]['url'],'locator':a['locator'],'review_status':a['review_status'],'polarity':a['polarity'],'context_excerpt':a['context'][:300],'context_truncated':len(a['context'])>300} for a in row['evidence'][:4]]
        next_actions.append({'finding_id':row['finding'],'label':row['label'],'action':row['action'],'content':row['content'],'review_status':row['template_status'],'associated_candidates':row['associated_candidates'],'excluded_candidates':row['excluded_candidates'],'unrecorded_candidates':row['unrecorded_candidates'],'evidence':refs,'omitted_evidence_count':max(0,len(row['evidence'])-4)})
    return {'contract_version':CONTRACT_VERSION,'data_version':kb.version,'data_sha256':kb.sha256,'score_method':result['ranking']['score_method'],'policy':policy,'phase':phase,'observations':provenance,'patient':patient,'patient_evidence':patient_evidence,'context_ignored':result['ranking']['context_ignored'],'candidates':candidates,'next_actions':next_actions,'history_pathways':paths,'warnings':result['ranking']['warnings'],'interpretation':'Scores are not diagnostic probabilities. Medical reference knowledge is not observed patient evidence. Provenance validation checks references, not the truth of semantic mapping. Plans are not performed results.'}
