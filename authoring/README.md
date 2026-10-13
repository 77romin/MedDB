# KB 원본 (사람이 고치는 곳)

`meddb/data/*.json` 은 이 폴더의 텍스트 파일에서 만들어진다. KB를 고칠 때는 JSON이 아니라 여기를 고친다.

| 파일 | 내용 | 한 줄 형식 |
|---|---|---|
| `base.txt` `[slots]` | 현병력 슬롯 | `id\|이름\|SOAP 칸\|질문(30자, 물음표 하나)\|조건(sex=F,age=12-55)` |
| `base.txt` `[exams]` | 진찰 | `id\|진찰표 표준명\|EXAM 문장(30자, 진찰 하나)` |
| `base.txt` `[findings]` | 소견 | `id\|이름\|kind\|계통\|질문 또는 진찰 id\|환자 표현;…\|조건·soap=` |
| `diseases.txt` | 질환 (`@id\|한글명\|영문명\|KCD\|urgency\|red flag Y/N\|빈도 1~3\|성별\|나이`) | 아래 `key:` `sup:` `against:` `ro:` `test:` `treat:` `dispo:` `edu:` `explain:` `unsafe:` `alias:` |
| `complaints.txt` | 주호소 (`#id\|이름`) | `alias:` `slots:` `ask:` `exams:` `diseases:` |

진찰 이름은 대회 진찰 결과표의 표준명(예: `갑상선 촉진`, `갑상선 안징후 검사`, `성장도표 백분위수 확인`)을 그대로 쓴다.
진찰 판정 모델이 요청을 표의 행에 맞추므로, 표준명을 쓰면 거절·"특이 소견 없음"이 줄어든다.

```bash
python tools/compile_kb.py authoring meddb/data     # 텍스트 → JSON
python -m unittest discover -s tests              # 검증(30자, KCD 코드, 참조 등) 포함
python tools/map_guidelines.py --catalog <catalog.csv>   # 새 주호소·질환을 넣었으면 지침 목록 연결도 갱신
python -m meddb clinical page docs/viewer.html     # 시각화 페이지 갱신
```
