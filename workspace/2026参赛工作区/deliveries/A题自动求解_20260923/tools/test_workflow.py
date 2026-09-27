"""Regression checks for stale provenance and exact-byte freezing."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from workspace import check_claims, freeze, inputs, record, verify_freeze, verify_records, write_json
from check_submission import check_support


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "inputs/problem").mkdir(parents=True)
        (self.root / "inputs/raw").mkdir()
        write_json(self.root / "inputs/manifest.json", [])

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_inputs_are_not_received(self):
        self.assertEqual(inputs(self.root)["status"], "NOT_RECEIVED")

    def test_registration_rejects_changed_original(self):
        path = self.root / "inputs/raw/data.csv"
        path.write_text("x\n1\n")
        inputs(self.root, register=True)
        path.write_text("x\n2\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            inputs(self.root, register=True)

    def test_unregistered_input_is_detected(self):
        (self.root / "inputs/raw/new.csv").write_text("x\n1\n")
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            inputs(self.root)

    def test_external_manifest_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside project"):
            verify_records(self.root, [{"path": "../outside", "sha256": "x"}])

    def test_freeze_preserves_bytes_and_rejects_change(self):
        pdf = self.root / "test.pdf"
        data = b"%PDF-1.4\nsynthetic byte-check fixture\n%%EOF\n"
        pdf.write_bytes(data)
        dest = self.root / "frozen"
        info = freeze(pdf, dest, "A", "00000000")
        self.assertEqual(info["md5"], hashlib.md5(data).hexdigest())
        self.assertTrue(verify_freeze(dest)["bytes_verified"])
        frozen = dest / info["filename"]
        frozen.chmod(0o644)
        frozen.write_bytes(data + b" ")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            verify_freeze(dest)

    def test_existing_freeze_not_overwritten(self):
        pdf = self.root / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        dest = self.root / "frozen"
        freeze(pdf, dest, "B", "00000000")
        with self.assertRaises(FileExistsError):
            freeze(pdf, dest, "B", "00000000")

    def test_support_manifest_detects_missing_and_changed_file(self):
        folder = self.root / "support"
        (folder / "code").mkdir(parents=True)
        code = folder / "code/solve.py"
        code.write_text("# anonymous fixture\n")
        digest = record(folder, code)["sha256"]
        (folder / "MANIFEST.csv").write_text("path,role,question,paper_location,sha256\ncode/solve.py,code,Q1,section1," + digest + "\n")
        self.assertEqual(check_support(self.root)["status"], "MANIFEST_VERIFIED")
        code.write_text("# changed\n")
        self.assertEqual(check_support(self.root)["status"], "ISSUES_FOUND")
        code.unlink()
        self.assertTrue(check_support(self.root)["issues"])

    def test_empty_support_is_not_prepared(self):
        (self.root / "support").mkdir()
        (self.root / "support/MANIFEST.csv").write_text("path,role,question,paper_location,sha256\n")
        self.assertEqual(check_support(self.root)["status"], "NOT_PREPARED")

    def test_claim_matches_cell_and_current_code(self):
        result, code, source = [self.root / p for p in ("result.csv", "solver.py", "input.csv")]
        result.write_text("metric,value\nobjective,34\n")
        code.write_text("# test fixture\n")
        source.write_text("x\n1\n")
        verification = self.root / "verification.json"
        write_json(verification, {"run_id": "test", "checks": [{"passed": True}], "files": [record(self.root, result), record(self.root, code)]})
        write_json(self.root / "results/test/run.json", {"run_id": "test", "inputs": [record(self.root, source)], "code": [record(self.root, code)], "outputs": [record(self.root, result)]})
        claim = dict(claim_id="C1", statement="fixture", value="34", tolerance="0", result_file="result.csv", result_row="1", result_column="value", code_file="solver.py", run_id="test", paper_location="section 1", verification_file="verification.json")
        check_claims(self.root, [claim])
        claim["value"] = "35"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            check_claims(self.root, [claim])
        claim["value"] = "34"
        code.write_text("# changed code\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            check_claims(self.root, [claim])


if __name__ == "__main__":
    unittest.main(verbosity=2)
