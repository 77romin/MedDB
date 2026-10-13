"""공개 샘플 증례를 개발 키로 실제 대회 서버에서 돌린다 (시작 패키지의 sample.py와 같은 방식).

    python examples/sample_meddb.py --list
    python examples/sample_meddb.py --case <공개 샘플 UUID>             # 온톨로지 에이전트
    python examples/sample_meddb.py --case <공개 샘플 UUID> --baseline  # 시작 패키지 기본 에이전트

환경변수 NOVA_API_BASE, NOVA_DEV_KEY 가 필요하다. 크레딧이 차감된다(채점은 하지 않음).
시작 패키지 폴더(run.py, nova_sdk.py가 있는 곳)에서 실행한다.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nova_sdk import Client  # noqa: E402

import run as baseline  # noqa: E402
from examples.consult_skeleton import consult, prepare  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--case")
    group.add_argument("--list", action="store_true")
    ap.add_argument("--baseline", action="store_true", help="시작 패키지 기본 에이전트로 실행")
    args = ap.parse_args()
    client = Client(token=os.environ["NOVA_DEV_KEY"], sample=True)
    if args.list:
        for case in client._request("GET", "/v1/sample/cases")["cases"]:
            print(case["case_id"], case["initial"]["opening"][:70])
        return
    client.create_sample(args.case)
    if args.baseline:
        result = baseline.consult(client, baseline.prepare())
    else:
        result = consult(client, prepare(), fallback=baseline.consult)
    print("제출 응답:", result)
    try:  # 개발 키 샘플 세션은 지난 행동 기록(events)을 돌려준다
        session = client.session()
    except Exception as exc:  # noqa: BLE001
        print("세션 기록을 가져오지 못함:", exc)
        return
    out = ROOT / "local" / "out"
    out.mkdir(parents=True, exist_ok=True)
    name = f"sample_{args.case[:8]}_{'baseline' if args.baseline else 'meddb'}.json"
    (out / name).write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
    for event in session.get("events", []):
        print(json.dumps(event, ensure_ascii=False)[:300])
    print("저장:", out / name)


if __name__ == "__main__":
    main()
