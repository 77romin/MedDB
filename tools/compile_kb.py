import json, sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])

def age(s):
    if not s: return None
    lo, hi = s.split("-")
    return [int(lo) if lo else None, int(hi) if hi else None]

def extra(s, row):
    for kv in filter(None, (s or "").split(",")):
        k, v = kv.split("=")
        row[k] = age(v) if k == "age" else v

def lst(s, sep=","): return [x.strip() for x in s.split(sep) if x.strip()]

slots, exams, findings = [], [], []
sec = None
for line in (src / "base.txt").read_text(encoding="utf-8").splitlines():
    if not line.strip(): continue
    if line.startswith("["): sec = line.strip("[]"); continue
    p = line.split("|")
    if sec == "slots":
        row = {"id": p[0], "ko": p[1], "soap": p[2], "ask": p[3]}
        extra(p[4] if len(p) > 4 else "", row); slots.append(row)
    elif sec == "exams":
        exams.append({"id": p[0], "ko": p[1], "action": p[2]})
    else:
        row = {"id": p[0], "ko": p[1], "kind": p[2], "sys": p[3]}
        if p[2] == "sign": row["exam"] = p[4]
        elif p[2] != "vital": row["ask"] = p[4]
        al = lst(p[5] if len(p) > 5 else "", ";")
        if al: row["alias"] = al
        extra(p[6] if len(p) > 6 else "", row); findings.append(row)

def blocks(path, mark):
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(mark):
            cur = {"_head": line[1:].split("|")}; yield cur
        elif line.strip():
            k, v = line.split(":", 1); cur[k.strip()] = v.strip()

diseases = []
for b in list(blocks(src / "diseases.txt", "@")):
    h = b["_head"]
    d = {"id": h[0], "ko": h[1], "en": h[2], "kcd": None if h[3] == "-" else h[3], "urgency": h[4],
         "red_flag": h[5] == "Y", "freq": int(h[6])}
    if h[7]: d["sex"] = h[7]
    if h[8]: d["age"] = age(h[8])
    if b.get("alias"): d["alias"] = lst(b["alias"], ";")
    d["key"] = lst(b["key"]); d["support"] = lst(b.get("sup", "")); d["against"] = lst(b.get("against", ""))
    d["rule_out"] = lst(b.get("ro", ""))
    d["dispo"] = b["dispo"]
    d["plan"] = {k: lst(b[k], ";") for k in ("test", "treat", "edu", "explain", "unsafe") if b.get(k)}
    diseases.append(d)

complaints = []
for b in list(blocks(src / "complaints.txt", "#")):
    h = b["_head"]
    complaints.append({"id": h[0], "ko": h[1], "alias": lst(b["alias"], ";"), "slots": lst(b["slots"]),
                       "ask": lst(b["ask"]), "exams": lst(b["exams"]), "diseases": lst(b["diseases"])})

J = lambda x: json.dumps(x, ensure_ascii=False)
def one_per_line(rows): return "[\n" + ",\n".join("  " + J(r) for r in rows) + "\n]\n"
def keyed(rows):
    parts = []
    for r in rows:
        body = ",\n".join(f"    {J(k)}: " + (("{\n" + ",\n".join(f"      {J(k2)}: {J(v2)}" for k2, v2 in v.items()) + "\n    }") if isinstance(v, dict) else J(v)) for k, v in r.items())
        parts.append("  {\n" + body + "\n  }")
    return "[\n" + ",\n".join(parts) + "\n]\n"

(out / "slots.json").write_text(one_per_line(slots), encoding="utf-8")
(out / "exams.json").write_text(one_per_line(exams), encoding="utf-8")
(out / "findings.json").write_text(one_per_line(findings), encoding="utf-8")
(out / "diseases.json").write_text(keyed(diseases), encoding="utf-8")
(out / "complaints.json").write_text(keyed(complaints), encoding="utf-8")
print(len(slots), len(exams), len(findings), len(diseases), len(complaints))
