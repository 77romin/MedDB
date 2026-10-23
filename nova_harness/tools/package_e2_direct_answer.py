"""Package upstream E2 with only the final patient-answer prompt changed."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(destination=None):
    reference = ROOT / "dist/submission_meddb_E2_reference.zip"
    out = Path(destination) if destination else ROOT / "dist/submission_E2_direct_answer.zip"
    with zipfile.ZipFile(reference) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    run = files["run.py"].decode("utf-8")
    old = "    return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')"
    if run.count(old) != 1:
        raise ValueError("unexpected upstream E2 run contract")
    new = """    from nova_agent.e2_direct_answer import install, restore
    original = install()
    try:
        return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)"""
    files["run.py"] = run.replace(old, new).encode("utf-8")
    files["nova_agent/__init__.py"] = b""
    files["nova_agent/e2_direct_answer.py"] = (ROOT / "nova_agent/e2_direct_answer.py").read_bytes()
    forbidden = (".env", "results/", "tests/", "tools/", "local/", "data/evaluation/", "docs/nova_competition/")
    if any(name.startswith(forbidden) or name.endswith(".pptx") or "evaluation-cases" in name for name in files):
        raise ValueError("unsafe submission member")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(out) as archive:
        if archive.testzip() is not None:
            raise ValueError("corrupt ZIP")
        names = archive.namelist()
    with tempfile.TemporaryDirectory(prefix="nova-e2-direct-answer-") as directory:
        with zipfile.ZipFile(out) as archive:
            archive.extractall(directory)
        subprocess.run([sys.executable, "-c", "import run; db=run.prepare(); print(db.meta['kb_version'])"], cwd=directory, check=True)
    result = {
        "path": str(out), "bytes": out.stat().st_size, "files": len(names),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "base_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "scope": "upstream E2 plus one final-answer instruction",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    build()
