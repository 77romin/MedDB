"""Package the validated E2 turn-reallocation candidate from an explicit allowlist."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = (
    "nova_agent/__init__.py",
    "nova_agent/e2_med_reconciliation.py",
    "nova_agent/e2_turn_reallocation.py",
)


def build(destination=None):
    reference = ROOT / "dist/submission_meddb_E2_reference.zip"
    out = Path(destination) if destination else ROOT / "dist/submission_E2_turn_reallocation.zip"
    with zipfile.ZipFile(reference) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    run = files["run.py"].decode("utf-8")
    old = "    return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')"
    if run.count(old) != 1:
        raise ValueError("unexpected upstream E2 run contract")
    new = """    from nova_agent.e2_turn_reallocation import install, restore
    original = install()
    try:
        return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)"""
    files["run.py"] = run.replace(old, new).encode("utf-8")
    for name in OVERLAY:
        path = ROOT / name
        files[name] = path.read_bytes() if path.exists() else b""

    forbidden = (".env", "results/", "tests/", "tools/", "local/", "downloads/", "vendor/", "dist/", "docs/REPOSITORY_HANDOFF")
    if any(name.startswith(forbidden) or name.endswith(".pptx") or "evaluation-cases" in name for name in files):
        raise ValueError("unsafe submission member")
    if len(files) > 5000 or sum(map(len, files.values())) > 500_000_000:
        raise ValueError("expanded package limit")

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    if out.stat().st_size > 50_000_000:
        raise ValueError("ZIP size limit")
    with zipfile.ZipFile(out) as archive:
        if archive.testzip() is not None:
            raise ValueError("corrupt ZIP")
        names = archive.namelist()
    with tempfile.TemporaryDirectory(prefix="nova-e2-turn-reallocation-") as directory:
        with zipfile.ZipFile(out) as archive:
            archive.extractall(directory)
        subprocess.run(
            [sys.executable, "-c", "import run; db=run.prepare(); print(db.meta['kb_version'])"],
            cwd=directory, check=True,
        )
    result = {
        "path": str(out), "bytes": out.stat().st_size, "files": len(names),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "base_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "scope": "validated C01 E2 turn-reallocation candidate; not uploaded",
    }
    out.with_suffix(".manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    build()
