#!/usr/bin/env python3
"""제출 ZIP을 만든다.

    python tools/make_submission.py --starter <시작 패키지 run.py> [--out dist/submission.zip]

구성: run.py(온톨로지 에이전트 + 시작 패키지 기본 에이전트를 대비책으로), requirements.txt, nova_sdk.py,
meddb/ (코드와 data), examples/consult_skeleton.py. 테스트·도구·화면 파일은 넣지 않는다.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUN_TAIL = '''

# ---------------------------------------------------------------------------
# 병명백백: 온톨로지(MedDB) 에이전트. 위의 기본 에이전트는 KB 밖 주호소일 때의 대비책으로 남겨 둔다.
from meddb import MedDB  # noqa: E402
from examples.consult_skeleton import consult as meddb_consult  # noqa: E402


def prepare():
    return MedDB.open()


def consult(client, db):
    return meddb_consult(client, db, fallback=baseline_consult)


if __name__ == '__main__':
    run_agent(prepare, consult)
'''


def build_run_py(starter_run: str) -> str:
    text = starter_run.replace("def prepare():", "def baseline_prepare():", 1)
    text = text.replace("def consult(client, model):", "def baseline_consult(client, model):", 1)
    text = re.sub(r"\nif __name__ == '__main__':\n    run_agent\(prepare, consult\)\n?\Z", "\n", text)
    assert "def baseline_consult(" in text and "run_agent(prepare, consult)" not in text, "시작 패키지 run.py 형식이 다름"
    return text.rstrip() + "\n" + RUN_TAIL


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--starter", required=True, help="시작 패키지의 run.py")
    ap.add_argument("--sdk", help="시작 패키지의 nova_sdk.py (생략하면 run.py와 같은 폴더)")
    ap.add_argument("--out", default=str(ROOT / "dist" / "submission.zip"))
    args = ap.parse_args()
    starter = Path(args.starter)
    sdk = Path(args.sdk) if args.sdk else starter.with_name("nova_sdk.py")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = {"run.py": build_run_py(starter.read_text(encoding="utf-8")),
             "requirements.txt": "# 추가 의존성 없음 (표준 라이브러리만 사용)\n",
             "nova_sdk.py": sdk.read_text(encoding="utf-8"),
             "examples/__init__.py": "",
             "examples/consult_skeleton.py": (ROOT / "examples" / "consult_skeleton.py").read_text(encoding="utf-8")}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
        for path in sorted((ROOT / "meddb").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.name != "viewer.py":
                zf.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        unpacked = sum(i.file_size for i in zf.infolist())
    print(f"{out} — {out.stat().st_size:,}바이트 (한도 50,000,000), 해제 후 {unpacked:,}바이트, 항목 {len(names)}개")


if __name__ == "__main__":
    main()
