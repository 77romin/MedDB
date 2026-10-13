"""Assess knowledge coverage against public-reference checklists, without diagnosis scoring."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB

ROOT=Path(__file__).resolve().parents[1]


def build_report(kb, config, pathways=None):
    pathways=pathways or {'entries':[]}
    requirements={p['id']:{r['id'] for r in p['requirements']} for p in pathways['entries']}
    result=[]
    for case in config['cases']:
        items=[]
        for item in case['items']:
            row=dict(item)
            if 'finding_id' in item:
                rows=[a for a in kb.assertions(True) if a['subject']==case['disease_id'] and a['predicate']=='has_phenotype' and a['object']==item['finding_id']]
                row.update(status='draft_relation' if rows else 'no_direct_relation',evidence_ids=[a['id'] for a in rows])
            else:
                row['status']='draft_pathway' if item['id'] in requirements.get(item['pathway'],set()) else 'missing_pathway'
            items.append(row)
        result.append({'case_id':case['case_id'],'disease_id':case['disease_id'],'patient_context':case['patient_context'],'source':case['source'],'items':items})
    return {'scope':config['scope'],'version':kb.version,'sha256':kb.sha256,'cases':result,'interpretation':'Structural coverage only; a draft relation/pathway is not clinically verified. Missing direct relation may be intentional.'}


def run():
    config=json.loads((ROOT/'data/evaluation/public-checklists.json').read_text(encoding='utf-8'))
    path=ROOT/'data/agent/clinical-pathways.json'
    pathways=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    report=build_report(KB(),config,pathways)
    lines=['# 공개 증례 지식 점검표','','평가 전용 자료입니다. 공개 정답·대본을 에이전트 실행 지식으로 가져오지 않습니다. 상태는 구조적 연결 여부이며 임상 검수 결과가 아닙니다.','']
    for case in report['cases']:
        lines += [f"## {case['case_id']}",'',f"맥락: {case['patient_context']}",f"원문: data/external/samples/nova-samples-2026/{case['source']}",'','| 영역 | 확인할 지식 | 현재 상태 | 원문 위치 |','|---|---|---|---|']
        for item in case['items']:lines.append(f"| {item['area']} | {item['label']} | {item['status']} | {item['locator']} |")
        lines.append('')
    (ROOT/'docs/public-case-checklists.md').write_text('\n'.join(lines),encoding='utf-8')
    (ROOT/'docs/public-case-checklists.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(report['cases']),'items':sum(len(c['items']) for c in report['cases']),'missing_pathways':sum(i['status']=='missing_pathway' for c in report['cases'] for i in c['items'])}))


if __name__=='__main__':run()
