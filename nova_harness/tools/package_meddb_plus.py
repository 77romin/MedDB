"""Package the inspected upstream E2 with a reversible, explicit local overlay."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    reference=ROOT/'dist/submission_meddb_E2_reference.zip'
    out=ROOT/'dist/submission_meddb_E2_plus_candidate.zip'
    with zipfile.ZipFile(reference) as z:
        files={n:z.read(n) for n in z.namelist()}
    text=files['run.py'].decode('utf-8')
    old="    return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')"
    if text.count(old)!=1:
        raise ValueError('unexpected upstream run.py contract')
    new="""    from nova_agent.meddb_overlay import install, restore
    original = install()
    try:
        return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)"""
    files['run.py']=text.replace(old,new).encode('utf-8')
    for p in [*sorted((ROOT/'nova_agent').glob('*.py')),*sorted((ROOT/'nova_agent').glob('*.json')),
              *sorted((ROOT/'third_party/meddb').glob('*'))]:
        if p.is_file():files[str(p.relative_to(ROOT))]=p.read_bytes()
    for name in files:
        if name.startswith(('.env','results/','tests/','tools/','local/','data/evaluation/')):
            raise ValueError('unsafe submission member')
    if len(files)>5000 or sum(map(len,files.values()))>500_000_000:
        raise ValueError('expanded package limit')
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    if out.stat().st_size>50_000_000:raise ValueError('ZIP size limit')
    manifest={'path':str(out),'bytes':out.stat().st_size,'files':len(files),
              'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
              'base_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),
              'scope':'candidate overlay; not the screenshot ZIP; not uploaded'}
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
