"""Reproduce the compact clinical import from an explicitly pinned user-owned repo."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PINNED_COMMIT = '63743a8b8a2e278b426d18fc040e880740318ae3'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', default=str(ROOT/'vendor/meddb'))
    args = p.parse_args()
    repo = Path(args.repo)
    commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if commit != PINNED_COMMIT:
        p.error('upstream changed; review before deliberately updating the pinned import')
    folder = repo/'meddb/data'
    names = ['common','slots','exams','findings','diseases','complaints']
    raw = {name:json.loads((folder/(name+'.json')).read_text(encoding='utf-8')) for name in names}
    out = {'source_repository':'https://github.com/SSAFY16-S11-NOVA2026/MedDB','commit':commit,
           'review':raw['common']['meta']['review'], 'slots':raw['slots'],'exams':raw['exams'],
           'findings':raw['findings'],'complaints':raw['complaints'],
           'diseases':[{k:d.get(k) for k in ['id','ko','en','sex','age','key','support','against','red_flag']}
                       for d in raw['diseases']], 'background':raw['common']['background']}
    target = ROOT/'nova_agent/clinical_graph.json'
    data = (json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
    sources = {str((folder/(name+'.json')).relative_to(repo)):hashlib.sha256((folder/(name+'.json')).read_bytes()).hexdigest() for name in names}
    # Check against the checked-in source hashes: commit alone does not detect dirty upstream data.
    manifest_path = ROOT/'third_party/meddb/import_manifest.json'
    if manifest_path.exists():
        pinned = json.loads(manifest_path.read_text(encoding='utf-8'))
        if pinned['source_files'] != sources:
            p.error('source files differ from pinned hashes')
    target.write_bytes(data)
    notices = ROOT/'third_party/meddb'; notices.mkdir(parents=True,exist_ok=True)
    for name in ['SOURCES.md','THIRD_PARTY_NOTICES.md']:
        (notices/name).write_bytes((repo/'docs'/name).read_bytes())
    manifest = {'repository':out['source_repository'],'commit':commit,'source_files':sources,
                'output_sha256':hashlib.sha256(data).hexdigest(),
                'counts':{k:len(out[k]) for k in ['slots','exams','findings','complaints','diseases']},
                'scope':'team-authored clinical structure only; no upstream evaluation material or treatment plans'}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest['counts']))


if __name__ == '__main__': main()
