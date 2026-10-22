"""One real public sample with unmodified R3a/R3b plus passive safety timeline."""
import argparse
from datetime import datetime,timezone,timedelta
import importlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from experiment import load_local_env,fingerprint
from nova_agent.protocol import LoggedClient,Gateway
from nova_agent.telemetry import Trace
from nova_agent.safety_trace import SafetyTimeline,TimelineClient,install,restore
from nova_agent.rag_retrieval import VectorStore
from nova_agent.analysis import write_report
from examples.hybrid_care import consult,prepare


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--mode',choices=['R3a','R3b','R3a_safety','R3a_obligations','R3a_obligations_fixed','R3a_response_state','R3a_coverage_order','R3a_question_link','R3a_observation_state'],required=True);args=p.parse_args()
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Key missing; configure locally')
    if os.environ.get('NOVA_API_BASE','https://nova.snubhai.org').rstrip('/')!='https://nova.snubhai.org':raise SystemExit('Official origin required')
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S_%f')
    out=ROOT/'results'/f'{stamp}_safety_session_{args.mode}';out.mkdir(mode=0o700)
    manifest={'scope':'public development sample; no official score','mode':args.mode,'case':args.case,'fingerprint':fingerprint()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    trace=Trace(out/'trace.jsonl',secrets=[key]);raw=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    trace.emit('experiment_start',manifest=manifest)
    Gateway(raw,trace=trace).invoke('create_sample',args.case)
    timeline=SafetyTimeline(trace);client=TimelineClient(raw,timeline)
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    module=importlib.import_module('nova_agent.e2_rag_query' if args.mode=='R3b' else 'nova_agent.e2_rag_selection')
    old_rag=module.install(store);old_safety=None
    old_response=None;response_events=[]
    if args.mode in ('R3a_response_state','R3a_coverage_order','R3a_question_link','R3a_observation_state'):
        from nova_agent import response_state
        old_response=response_state.install(response_events)
    old_order=None
    if args.mode in ('R3a_coverage_order','R3a_question_link','R3a_observation_state'):
        from nova_agent import coverage_order
        old_order=coverage_order.install(response_events)
    old_unified=None;observation_ledgers=[]
    if args.mode=='R3a_observation_state':
        from nova_agent import e2_observation_state
        old_unified=e2_observation_state.install(response_events,observation_ledgers)
    old_link=None
    if args.mode=='R3a_question_link':
        from nova_agent import e2_question_link
        old_link=e2_question_link.install(response_events)
    if args.mode in ('R3a_safety','R3a_obligations','R3a_obligations_fixed'):
        from nova_agent import e2_safety_delivery
        old_safety=e2_safety_delivery.install(timeline)
        client=e2_safety_delivery.wrap(client,timeline)
    old_obligations=None
    old_questions=None
    if args.mode in ('R3a_obligations','R3a_obligations_fixed'):
        from nova_agent import e2_safety_obligations
        old_obligations=e2_safety_obligations.install(timeline,repair_invalid=args.mode=='R3a_obligations_fixed')
        if args.mode=='R3a_obligations_fixed':
            from nova_agent import answered_questions
            old_questions=answered_questions.install(timeline.obligations.events)
        # Skip S1's regex-based final record rewrite for the structured candidate.
        client=e2_safety_obligations.wrap(TimelineClient(raw,timeline),timeline)
    old_record=install(timeline)
    print('Experiment directory:',out,flush=True)
    try:
        outcome=consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
        trace.emit('experiment_complete',outcome=outcome)
    finally:
        restore(old_record)
        if old_unified is not None:
            e2_observation_state.restore(old_unified)
            (out/'observation_ledgers.json').write_text(json.dumps([l.snapshot() for l in observation_ledgers],ensure_ascii=False,indent=2),encoding='utf-8')
            (out/'observation_events.json').write_text(json.dumps([e for l in observation_ledgers for e in l.events],ensure_ascii=False,indent=2),encoding='utf-8')
        if old_link is not None:e2_question_link.restore(old_link)
        if old_order is not None:coverage_order.restore(old_order)
        if old_response is not None:
            response_state.restore(old_response)
            (out/'response_state.json').write_text(json.dumps(response_events,ensure_ascii=False,indent=2),encoding='utf-8')
        if old_questions is not None:answered_questions.restore(old_questions)
        if old_obligations is not None:
            e2_safety_obligations.restore(old_obligations)
        if old_safety is not None:
            (out/'safety_delivery.json').write_text(json.dumps(e2_safety_delivery.LAST_RUN,ensure_ascii=False,indent=2),encoding='utf-8')
            e2_safety_delivery.restore(old_safety)
        module.restore(old_rag);store.close()
        (out/'timeline.json').write_text(json.dumps(timeline.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['end_fingerprint']=fingerprint()
    manifest['fingerprint_unchanged']=manifest['end_fingerprint']==manifest['fingerprint']
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(write_report(out/'trace.jsonl'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
