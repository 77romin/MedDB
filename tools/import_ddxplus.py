#!/usr/bin/env python3
"""DDXPlus 지식 파일에서 질환–소견 연결을 뽑아 meddb/data/ext_ddxplus.json을 만든다 (표준 라이브러리만).

    python tools/import_ddxplus.py --conditions release_conditions.json --evidences release_evidences.json

DDXPlus (Fansi Tchango et al., NeurIPS 2022 Datasets and Benchmarks), CC BY 4.0.
가져오는 것은 "어떤 질환에 어떤 문진 항목이 연결되어 있는가"뿐이고, 문장은 가져오지 않는다.
대응표(tools/ddxplus_map.json)에 없는 항목과 질환은 건너뛴다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "meddb" / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", required=True)
    ap.add_argument("--evidences", required=True)
    args = ap.parse_args()
    conditions = json.loads(Path(args.conditions).read_text(encoding="utf-8"))
    evidences = json.loads(Path(args.evidences).read_text(encoding="utf-8"))
    mapping = json.loads((ROOT / "tools" / "ddxplus_map.json").read_text(encoding="utf-8"))
    ev_map, cond_map = mapping["evidence"], mapping["condition"]
    findings = {f["id"] for f in json.loads((DATA / "findings.json").read_text(encoding="utf-8"))}
    diseases = {d["id"]: d for d in json.loads((DATA / "diseases.json").read_text(encoding="utf-8"))}
    for ev, fid in ev_map.items():
        if ev not in evidences:
            raise SystemExit(f"대응표의 {ev}가 DDXPlus에 없음")
        if fid not in findings:
            raise SystemExit(f"대응표의 소견 '{fid}'가 KB에 없음")

    links: dict[str, list[str]] = {}
    new = conflict = 0
    for name, cond in conditions.items():
        did = cond_map.get(name)
        if did is None:
            continue
        if did not in diseases:
            raise SystemExit(f"대응표의 질환 '{did}'가 KB에 없음")
        d = diseases[did]
        mapped = sorted({ev_map[e] for e in list(cond["symptoms"]) + list(cond["antecedents"]) if e in ev_map})
        links[did] = mapped
        for fid in mapped:
            if fid in d.get("against", []):
                conflict += 1
                print(f"충돌(팀 판단 유지): {did} — {fid} 는 KB에서 반대 소견")
            elif fid not in d["key"] and fid not in d.get("support", []):
                new += 1
    out = {
        "meta": {
            "source": "DDXPlus Dataset (English) — release_conditions.json, release_evidences.json",
            "citation": "Fansi Tchango A, et al. DDXPlus: A New Dataset For Automatic Medical Diagnosis. NeurIPS 2022 Datasets and Benchmarks.",
            "license": "CC BY 4.0",
            "url": "https://figshare.com/articles/dataset/DDXPlus_Dataset_English_/22687585",
            "changes": "질환–문진 항목 연결만 추출해 KB 소견 id로 옮김 (tools/ddxplus_map.json). 문장·환자 데이터는 포함하지 않음.",
            "conditions_total": len(conditions), "conditions_mapped": len(links),
            "evidences_total": len(evidences), "evidences_mapped": len(ev_map),
        },
        "links": dict(sorted(links.items())),
    }
    body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in out["links"].items())
    text = '{\n  "meta": ' + json.dumps(out["meta"], ensure_ascii=False, indent=4).replace("\n", "\n  ") + ',\n  "links": {\n' + body + "\n  }\n}\n"
    (DATA / "ext_ddxplus.json").write_text(text, encoding="utf-8")
    print(f"질환 {len(links)}/{len(conditions)}개, 문진 항목 {len(ev_map)}/{len(evidences)}개 대응. "
          f"KB에 없던 연결 {new}건, 충돌 {conflict}건")


if __name__ == "__main__":
    main()
