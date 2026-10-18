"""Inspect bounded experiment plans; do not confuse unfinished, estimated and official scores."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.suite_report import CASES
from nova_agent.analysis import analyze


def collect_plans(plans):
    records=[]
    for plan in plans:
        jobs=json.loads(Path(plan).read_text())
        for job in jobs:
            source=Path(job['source'])
            matches=[p for p in (source/'results').glob('*/manifest.json')
                     if json.loads(p.read_text()).get('label')==job['label']]
            if len(matches)>1:
                raise ValueError('ambiguous run label '+job['label'])
            value={'label':job['label'],'case':CASES.get(job['case_id'],'unknown'),'status':'not_started',
                   'score':None,'official_score':None}
            if not matches:
                records.append(value);continue
            manifest=matches[0];d=manifest.parent;m=json.loads(manifest.read_text())
            data=analyze(d/'trace.jsonl');rows=[json.loads(x) for x in (d/'trace.jsonl').read_text().splitlines()]
            features = m.get('telemetry_features')
            goal_instrumented = ('decision_goals' in features if isinstance(features,list) else m.get('decision_review') is True)
            goal_instrumented |= any(r['event']=='decision_goals_updated' for r in rows)
            question_instrumented = ('patient_question_tracking' in features if isinstance(features,list) else
                                     m.get('agent','harness')=='harness' and m.get('agent_version') in {'0.8.1','0.8.2','0.8.3'})
            question_instrumented |= any(r['event']=='patient_question_pending' for r in rows)
            note=next((r['note'] for r in reversed(rows) if r['event']=='record_ready'),{})
            review=json.loads((d/'local_review.json').read_text()) if (d/'local_review.json').exists() else None
            value.update(directory=str(d),version=m.get('agent_version'),
                         source_sha256=hashlib.sha256(json.dumps(m['fingerprint'],sort_keys=True).encode()).hexdigest(),
                         status='completed' if data['completed'] else 'failed' if data['experiment_finished'] else 'running',
                         score=review['estimated_total'] if review else None,
                         areas={k:v['score'] for k,v in review['scores'].items()} if review else {},
                         review_prompt_sha256=review.get('review_prompt_sha256') if review else None,
                         review_reference_sha256=review.get('reference_sha256') if review else None,
                         input_tokens=data['prompt_tokens'],output_tokens=data['completion_tokens'],
                         doctor_attempts=data['doctor_attempted_request_ids'],errors=data['errors'],
                         truncations=data['truncated_completions'],collection_stop=data['collection_stop_reason'],
                         goal_updates=data['goal_updates_accepted'] if goal_instrumented else None,
                         goal_rejections=data['goal_updates_rejected'] if goal_instrumented else None,
                         questions_detected=data['patient_questions_detected'] if question_instrumented else None,
                         questions_without_sent_answer=data['patient_questions_without_sent_answer'] if question_instrumented else None,
                         closing_turns=sum(r['event']=='closing_say' for r in rows),
                         history_empty_fields=[k for k,v in note.get('S',{}).items() if not v.strip()],
                         note_bytes=len(json.dumps(note,ensure_ascii=False).encode()) if note else None,
                         collection_actions=dict(Counter(r['evidence']['action'] for r in rows if r['event']=='evidence_added')))
            records.append(value)
    return records


def render(records):
    lines=['# 단계별 개발 실험 모니터','',
           '점수는 세션 밖 개발 검토자의 비공식 추정이다. 공식 점수는 별도 제출 전까지 미측정이다.',
           '서로 다른 소스·옵션·단계는 평균으로 합치지 않는다. 단일 실행 차이는 일반화나 인과 효과를 입증하지 못한다.',
           '질문 감지·답변 ID 연결·목표 상태는 휴리스틱/모델 해석이며 임상적 충분성의 검증 결과가 아니다.',
           '계측이 없던 버전의 목표·질문 지표는 —로 표시한다. 기능이 없거나 미계측인 상태를 0건으로 해석하지 않는다.','',
           '| 조건 | 증례 | 상태 | 비공식 추정 | Doctor 요청 | 입력/출력 | 목표 갱신 | 감지 질문/답변 ID 미연결 | 기록 바이트 |',
           '| --- | --- | --- | ---: | ---: | --- | ---: | --- | ---: |']
    for r in records:
        display=lambda value: value if value is not None else '—'
        lines.append('| '+ ' | '.join(str(v) for v in [r['label'],r['case'],r['status'],r['score'] if r['score'] is not None else '미검토',
                     r.get('doctor_attempts','—'),f"{r.get('input_tokens','—')}/{r.get('output_tokens','—')}",
                     display(r.get('goal_updates')),f"{display(r.get('questions_detected'))}/{display(r.get('questions_without_sent_answer'))}",display(r.get('note_bytes'))])+' |')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plans',nargs='+');parser.add_argument('--output',required=True)
    args=parser.parse_args();records=collect_plans(args.plans)
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(render(records));dest.with_suffix('.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print(str(dest))


if __name__=='__main__':main()
