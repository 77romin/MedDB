"""Replay selected observed SAYs through the final guard; no new choices/patient calls."""
import json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from meddb.coverage import CareCoverage
from nova_agent import answered_questions as Q

def main():
    summary=json.loads((Path(sys.argv[1])/'summary.json').read_text());results=[]
    for item in summary['runs']:
        data=json.loads((Path(item['directory'])/'timeline.json').read_text());events=[]
        original=Q.install(events);coverage=CareCoverage(None,None,None,None)
        kb=SimpleNamespace(conflicts={'unresolved'},exams_done=set());blocked=0
        try:
            for s in data['successful_speech']:
                if s['record_count']>0:continue
                if not coverage.allow_action(kb,'SAY',s['content'],None):blocked+=1;continue
                coverage.observe(None,s['content'],s.get('reply',{}).get('content',''),s['index'])
        finally:Q.restore(original)
        results.append({'case':item['case_label'],'blocked_observed_candidates':blocked})
    result={'scope':'saved selected SAY replay only, not new action selection or a live session','runs':results}
    (ROOT/'reports/question_guard_replay_044.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
