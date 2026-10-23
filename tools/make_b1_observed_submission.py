"""Build the B1-observed extension through the unmodified upstream B1 builder."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile
import make_submission as base
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--starter',required=True);p.add_argument('--sdk');p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        baseline=Path(tmp)/'b1.zip';saved=sys.argv
        sys.argv=['make_submission.py','--starter',a.starter,'--agent','b1','--out',str(baseline)]
        if a.sdk:sys.argv+=['--sdk',a.sdk]
        try:base.main()
        finally:sys.argv=saved
        with zipfile.ZipFile(baseline) as z:files={n:z.read(n) for n in z.namelist()}
    old=b'from examples.agent_b1 import consult as meddb_consult'
    if files['run.py'].count(old)!=1:raise ValueError('B1 dispatch contract changed')
    files['run.py']=files['run.py'].replace(old,b'from examples.agent_b1_observed import consult as meddb_consult')
    for name in ('examples/agent_b1_observed.py','examples/reader_b1_observed.py'):
        files[name]=(ROOT/name).read_bytes()
    base.validate_members(files)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):z.writestr(name,files[name])
    if out.stat().st_size>50_000_000:raise ValueError('ZIP size limit')
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    print(json.dumps({'zip':out.name,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'scope':'B1 observed extension; not uploaded'}))
if __name__=='__main__':main()
