"""Build a small offline KB integration bundle, not a complete contest submission."""
import hashlib
import gzip
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB


def run():
    root=Path(__file__).resolve().parents[1]
    kb=KB();folder=root/'dist';folder.mkdir(exist_ok=True)
    target=folder/'nova-knowledge-bundle.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in (root/'meddb').glob('*.py'):archive.write(file,file.relative_to(root).as_posix())
        for file in (root/'meddb/data').glob('*'):
            if file.is_file():archive.write(file,file.relative_to(root).as_posix())
        for file in (root/'data/agent').glob('*.json'):
            if file.name!='evaluation-cases.json':archive.write(file,file.relative_to(root).as_posix())
        raw=kb.path.read_bytes()
        if kb.path.suffix=='.gz':raw=gzip.decompress(raw)
        if hashlib.sha256(raw).hexdigest()!=kb.sha256:
            raise ValueError('Source snapshot changed during packaging')
        archive.writestr(f'data/releases/{kb.version}.json.gz',gzip.compress(raw,mtime=0))
        for name in ('examples/agent_knowledge.py','examples/knowledge_session.py','docs/agent-integration.md','docs/agent-contract.md','docs/THIRD_PARTY_NOTICES.md','docs/licenses/DisMech-BSD-3-Clause.txt'):
            archive.write(root/name,name)
    with tempfile.TemporaryDirectory() as temporary:
        with zipfile.ZipFile(target) as archive:archive.extractall(temporary)
        checked=subprocess.check_output([sys.executable,'-c',"import json; from meddb import KB; from examples.agent_knowledge import knowledge_tools; from examples.knowledge_session import KnowledgeSession; k=KB(); r=knowledge_tools(k,{'nova:vomiting':'present'},profile='pilot'); session=KnowledgeSession(k,profile='research'); event=session.record_result('say',1,'잠을 잘 못 자요'); session.confirm_observation('hpo:HP:0100785','present',[event]); contract=session.support()['contract_version']; print(json.dumps({'sha256':k.sha256,'candidates':len(r['candidates']),'recommendations':len(r['next_actions']),'contract':contract}))"],cwd=temporary,text=True)
        validation=json.loads(checked)
        if validation['sha256']!=kb.sha256 or not validation['candidates']:
            raise ValueError('Extracted bundle verification failed')
    manifest={'bundle':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'data_version':kb.version,'data_sha256':kb.sha256,'complete_contest_submission':False,'extracted_bundle_validation':validation}
    (folder/'nova-knowledge-bundle.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':run()
