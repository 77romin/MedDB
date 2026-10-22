"""Private saved-note replay; publish counts only, never patient text."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nova_agent.safety_obligations import ObligationLedger

def main():
    count=0
    for path in sorted((ROOT/'results').glob('20261022_*_safety_session_*/timeline.json')):
        data=json.loads(path.read_text())
        if not data.get('final'):
            continue
        ledger=ObligationLedger()
        for i,record in enumerate(data['records']):
            ledger.update(record['note'],record['observation_hash'],record_count=i+1)
        note=data['final']['note']
        ledger.update(note,record_count=len(data['records'])+1)
        frozen=json.dumps(note,sort_keys=True,ensure_ascii=False)
        out=ledger.render(note,data['successful_speech'])
        assert json.dumps(note,sort_keys=True,ensure_ascii=False)==frozen
        assert all(out.get(k)==note.get(k) for k in ('S','O','A'))
        for field,value in note.get('P',{}).items():
            if isinstance(value,str):
                assert value.split('환자에게 설명함:',1)[0].strip() in out['P'][field]
        actual=out['P']['education'].split('실제 전달 기록(API 성공 응답 기준; 이해 여부 미확인):',1)[1]
        for speech in data['successful_speech']:
            if speech['record_count']>0 and '?' not in speech['content']:
                assert speech['content'] in actual
        assert not ledger.audit(data['successful_speech'])['coverage_verified']
        count+=1
    assert count>0
    result={'saved_sessions':count,'input_unchanged':True,'SOA_unchanged':True,
            'source_plan_preserved_as_unverified_quote':True,'actual_speech_rendered':True,
            'clinical_coverage_proven':False,'scope':'saved-record replay, not fresh API or official score'}
    (ROOT/'reports/obligations_replay_042.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
