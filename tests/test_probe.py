import contextlib, io, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe

class ProbeSafetyTests(unittest.TestCase):
    def test_probe_requires_explicit_serial_without_calling_adb(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = probe.main([])
        self.assertEqual(2, rc)
        self.assertIn("explicit serial is required", err.getvalue())
