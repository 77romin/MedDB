import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.package_e2_turn_reallocation import build

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "dist/submission_meddb_E2_reference.zip").exists(), "reference ZIP missing")
class PackageE2TurnReallocationTests(unittest.TestCase):
    def test_allowlisted_overlay_and_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "candidate.zip"
            build(out)
            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                run = archive.read("run.py").decode()
            self.assertIn("nova_agent/e2_turn_reallocation.py", names)
            self.assertIn("nova_agent/e2_med_reconciliation.py", names)
            self.assertIn("e2_turn_reallocation", run)
            self.assertFalse(any(name.startswith(("results/", "tests/", "tools/", "vendor/", ".env")) for name in names))
            self.assertNotIn("DECISIONS.md", names)
            self.assertNotIn("docs/REPOSITORY_HANDOFF.md", names)


if __name__ == "__main__":
    unittest.main()
