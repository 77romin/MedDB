"""Frozen-revision knowledge replay; no Doctor model, API keys, or diagnosis accuracy."""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE_REVISION='9711bb8'
IMPROVED_REVISION='d766fd4'


def freeze_revision(revision,folder):
    revision=subprocess.check_output(['git','rev-parse','--verify',revision+'^{commit}'],cwd=ROOT,text=True).strip()
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',revision],cwd=ROOT,text=True).splitlines()
    selected=[n for n in names if (n.startswith('meddb/') and n.endswith('.py')) or (n.startswith('data/agent/') and n.endswith('.json') and n!='data/agent/evaluation-cases.json') or n=='data/releases/meddb-2026.10.13.1.json.gz']
    if not selected:raise ValueError('Revision lacks knowledge files')
    raw=subprocess.check_output(['git','archive','--format=zip',revision,*selected],cwd=ROOT)
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);files=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            target=(folder/info.filename).resolve()
            if not target.is_relative_to(folder):raise ValueError('Unsafe snapshot path')
            if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            data=archive.read(info);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            files.append({'path':info.filename,'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'revision':revision,'files':files,'sample_answers_included':False}
    (folder/'snapshot-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def load_snapshot(folder):
    folder=Path(folder).resolve();manifest=json.loads((folder/'snapshot-manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path=(folder/entry['path']).resolve()
        if not path.is_relative_to(folder) or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Snapshot changed')
    name='frozen_meddb_'+manifest['revision']
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,folder/'meddb/__init__.py',submodule_search_locations=[str(folder/'meddb')])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name].KB()


def requests_from_public_samples():
    root=ROOT/'data/external/samples/nova-samples-2026';results=[]
    for case,age,sex in [('C01',62,'female'),('C03',6,'male'),('C10',32,'female')]:
        path=root/case/'case.json';raw=path.read_bytes();sample=json.loads(raw)
        events=[{'id':'initial','kind':'initial','turn':0,'content':sample['start_information']['opening']}]
        obs=[];patient={'age':age,'sex':sex};bindings={'age':['initial'],'sex':['initial']}
        if case=='C01':obs=[{'finding_id':'hpo:HP:0100785','state':'present','evidence_ids':['initial']}]
        if case=='C03':
            result=next(e['result'] for e in sample['exam_results'] if e['exam'].startswith('성장도표'))
            events.append({'id':'exam-1','kind':'exam','turn':1,'content':result})
            obs=[{'finding_id':'hpo:HP:0004322','state':'present','evidence_ids':['exam-1']}]
            patient['puberty_assessment']='not_age_appropriate';bindings['puberty_assessment']=['initial']
        if case=='C10':
            for i,(prefix,finding) in enumerate([('갑상선 촉진','hpo:HP:0000853'),('갑상선 안징후','hpo:HP:0000520')],1):
                content=next(e['result'] for e in sample['exam_results'] if e['exam'].startswith(prefix))
                events.append({'id':f'exam-{i}','kind':'exam','turn':i,'content':content})
                obs.append({'finding_id':finding,'state':'present','evidence_ids':[f'exam-{i}']})
            obs.append({'finding_id':'nova:weight-loss','state':'present','evidence_ids':['initial']})
        results.append({'case_id':case,'source_sha256':hashlib.sha256(raw).hexdigest(),'request':{'observations':obs,'events':events,'patient':patient,'patient_evidence':bindings,'profile':'research','phase':'preliminary','limit':5}})
    return results


def support(kb,request,arm):
    if arm=='no_kb':return None
    if arm=='improved_kb':return kb.assist(**request)
    states={o['finding_id']:o['state'] for o in request['observations']}
    patient={k:v for k,v in request.get('patient',{}).items() if k in {'age','sex'}}
    result=kb.suggest(states,profile=request['profile'],patient=patient,limit=5)
    return {'data_version':kb.version,'data_sha256':kb.sha256,'score_method':result['ranking']['score_method'],'candidates':[{'id':c['disease']['id'],'rank':c['rank'],'evidence_score':c['score'],'evidence':c['evidence'][:4]} for c in result['ranking']['candidates'][:5]],'next_actions':result['recommendations'],'history_pathways':{'pathways':[]},'context_ignored':[],'warnings':result['ranking']['warnings']+['Legacy snapshot does not support the new evidence/history/context contract.']}


def run(output=None):
    folder=ROOT/'.run/knowledge-comparison'
    manifests={arm:freeze_revision(ref,folder/arm) for arm,ref in [('previous_kb',BASE_REVISION),('improved_kb',IMPROVED_REVISION)]}
    old=load_snapshot(folder/'previous_kb');new=load_snapshot(folder/'improved_kb')
    cases=requests_from_public_samples();rows=[]
    for case in cases:
        # Verify shared annotations with the strict contract before comparing any arm.
        new.assist(**case['request'])
        for arm,kb in [('no_kb',None),('previous_kb',old),('improved_kb',new)]:
            start=time.perf_counter();result=support(kb,case['request'],arm);elapsed=time.perf_counter()-start
            text=json.dumps(result,ensure_ascii=False)
            rows.append({'case_id':case['case_id'],'arm':arm,'knowledge_enabled':result is not None,'latency_seconds':round(elapsed,6) if result is not None else None,'response_bytes':len(text.encode()) if result is not None else 0,'candidate_ids':[c['id'] for c in result['candidates']] if result else [],'pathway_requirements':sum(len(p['pending']) for p in result['history_pathways']['pathways']) if result else 0,'source_sha256':case['source_sha256']})
    report={'mode':'offline_reference_fact_replay','revisions':{arm:m['revision'] for arm,m in manifests.items()},'cases':len(cases),'runs':rows,'patient_interaction_performed':False,'model_calls':0,'diagnostic_accuracy':None,'doctor_turns':None,'model_cost':None,'interpretation':'Public source facts were provided directly, including selected exam-table entries. No autonomous patient interaction or clinical accuracy test. Knowledge latency and output size only.'}
    target=Path(output) if output else ROOT/'docs/offline-knowledge-comparison.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 오프라인 KB 비교','','공개 자료의 확인된 사실을 직접 제공한 참고 사실 재생입니다. 실제 진료·진단 정확도·모델 비용·진료 턴 수를 측정하지 않았습니다.','', '| 증례 | 조건 | 요구사항 제안 | 응답 bytes | KB 조회 초 |','|---|---|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['case_id']} | {r['arm']} | {r['pathway_requirements']} | {r['response_bytes']} | {r['latency_seconds']} |")
    (ROOT/'docs/offline-knowledge-comparison.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'runs':len(rows),'model_calls':0,'accuracy':None,'revisions':report['revisions']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');run(parser.parse_args().output)
