import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_isolated_submission_prepares_without_dev_files_or_credentials(self):
        spec = importlib.util.spec_from_file_location('package_submission', ROOT/'tools/package_submission.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with contextlib.redirect_stdout(io.StringIO()):
            archive = module.build()
        with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as directory:
            names = z.namelist()
            self.assertTrue({'run.py', 'nova_sdk.py', 'requirements.txt'}.issubset(names))
            self.assertFalse(any(x.startswith(('vendor/', 'results/', 'tests/', 'tools/', '.env')) for x in names))
            z.extractall(directory)
            env = {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'}
            completed = subprocess.run([sys.executable, '-B', '-c',
                'import json; from run import prepare; print(json.dumps(prepare()["status"]))'],
                cwd=directory, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout), 'structural_seed_not_clinically_validated')


if __name__ == '__main__': unittest.main()
