#!/usr/bin/env python3
"""제출 ZIP을 만든다.

    python tools/make_submission.py --starter <시작 패키지 run.py> [--agent hybrid|meddb] [--out ...]

--agent hybrid (기본): LLM이 진료를 이끌고 KB가 매 턴 힌트를 준다 (examples/hybrid_agent.py)
--agent meddb        : KB가 진료를 정하고, KB 밖 주호소는 시작 패키지 기본 에이전트로 넘긴다
구성: run.py, requirements.txt, nova_sdk.py, meddb/ (코드와 data), examples/. 테스트·도구·화면 파일은 넣지 않는다.
"""
from __future__ import annotations

import argparse
import re
import zipfile
import gzip
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))


def reference_files(root=ROOT):
    """Explicit runtime allowlist: no evaluation cases, answers, PPTs or guideline bodies."""
    from meddb import KB
    kb = KB()
    raw = gzip.decompress(kb.path.read_bytes()) if kb.path.suffix == '.gz' else kb.path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != kb.sha256:
        raise ValueError('Reference snapshot changed during packaging')
    files = {f'data/releases/{kb.version}.json.gz': gzip.compress(raw, mtime=0)}
    for name in ('actions', 'assist-schema', 'checklists', 'clinical-pathways', 'clinical-mappings',
                 'guideline-queries', 'phrases', 'profiles'):
        path = root / 'data/agent' / f'{name}.json'
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    for name in ('docs/THIRD_PARTY_NOTICES.md', 'docs/SOURCES.md', 'docs/licenses/DisMech-BSD-3-Clause.txt'):
        files[name] = (root / name).read_bytes()
    return files


def validate_members(names):
    forbidden = ('samples/', 'local/', 'tests/', 'authoring/', 'data/evaluation/', 'docs/nova_competition/')
    if any(n.startswith(forbidden) or n.endswith('.pptx') or 'evaluation-cases' in n for n in names):
        raise ValueError('Development or evaluation material in submission')

RUN_TAIL = '''

# ---------------------------------------------------------------------------
# 병명백백: 온톨로지(MedDB) 에이전트. 위의 기본 에이전트는 KB 밖 주호소일 때의 대비책으로 남겨 둔다.
from meddb import MedDB  # noqa: E402
from examples.{module} import consult as meddb_consult  # noqa: E402


def prepare():
    return MedDB.open()


def consult(client, db):
    return meddb_consult(client, db, fallback=baseline_consult{options})


if __name__ == '__main__':
    run_agent(prepare, consult)
'''


def build_run_py(starter_run: str, agent: str = "hybrid", knowledge_mode='clinical', reference_profile='reviewed') -> str:
    if knowledge_mode not in {'clinical', 'ontology', 'integrated'} or reference_profile not in {'reviewed', 'pilot', 'research'}:
        raise ValueError('Invalid knowledge configuration')
    text = starter_run.replace("def prepare():", "def baseline_prepare():", 1)
    text = text.replace("def consult(client, model):", "def baseline_consult(client, model):", 1)
    text = re.sub(r"\nif __name__ == '__main__':\n    run_agent\(prepare, consult\)\n?\Z", "\n", text)
    assert "def baseline_consult(" in text and "run_agent(prepare, consult)" not in text, "시작 패키지 run.py 형식이 다름"
    module = {"hybrid": "hybrid_agent", "meddb": "consult_skeleton"}[agent]
    options = f", knowledge_mode={knowledge_mode!r}, reference_profile={reference_profile!r}" if agent == 'hybrid' else ''
    return text.rstrip() + "\n" + RUN_TAIL.replace("{module}", module).replace('{options}', options)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--starter", required=True, help="시작 패키지의 run.py")
    ap.add_argument("--sdk", help="시작 패키지의 nova_sdk.py (생략하면 run.py와 같은 폴더)")
    ap.add_argument("--agent", choices=["hybrid", "meddb"], default="hybrid")
    ap.add_argument('--knowledge-mode', choices=['clinical', 'ontology', 'integrated'], default='clinical')
    ap.add_argument('--reference-profile', choices=['reviewed', 'pilot', 'research'], default='reviewed')
    ap.add_argument("--out")
    args = ap.parse_args()
    starter = Path(args.starter)
    sdk = Path(args.sdk) if args.sdk else starter.with_name("nova_sdk.py")
    out = Path(args.out or ROOT / "dist" / f"submission_{args.agent}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    files = {"run.py": build_run_py(starter.read_text(encoding="utf-8"), args.agent, args.knowledge_mode, args.reference_profile),
             "requirements.txt": "# 추가 의존성 없음 (표준 라이브러리만 사용)\n",
             "nova_sdk.py": sdk.read_text(encoding="utf-8"),
             "examples/__init__.py": "",
             "examples/consult_skeleton.py": (ROOT / "examples" / "consult_skeleton.py").read_text(encoding="utf-8"),
             "examples/hybrid_agent.py": (ROOT / "examples" / "hybrid_agent.py").read_text(encoding="utf-8")}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
        for path in sorted((ROOT / "meddb").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.name != "viewer.py":
                zf.write(path, path.relative_to(ROOT).as_posix())
        for name, content in reference_files().items():
            zf.writestr(name, content)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        unpacked = sum(i.file_size for i in zf.infolist())
    validate_members(names)
    if out.stat().st_size > 50_000_000:
        raise ValueError('Submission exceeds compressed size limit')
    with tempfile.TemporaryDirectory() as temporary:
        with zipfile.ZipFile(out) as zf:
            zf.extractall(temporary)
        validation = json.loads(subprocess.check_output([sys.executable, '-c',
            "import json,run; from meddb import KB; from meddb.bridge import KnowledgeBridge; d=run.prepare(); b=KnowledgeBridge(d,KB()); print(json.dumps({'clinical_version':d.meta['kb_version'],'reference_version':b.reference.version,'mapping_version':b.mapping_version}))"],
            cwd=temporary, text=True, encoding='utf-8'))
    manifest = {'zip': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                'knowledge_mode': args.knowledge_mode, 'reference_profile': args.reference_profile,
                'extracted_validation': validation, 'model_calls': 0}
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f"{out} - {out.stat().st_size:,}바이트 (한도 50,000,000), 해제 후 {unpacked:,}바이트, 항목 {len(names)}개")


if __name__ == "__main__":
    main()
