"""Synthetic contract tests; no live solver or official evaluation is invoked."""

import csv
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import zipfile

import package_a_author as packager


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False) + "\n"
    path.write_text(content, encoding="utf-8")


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class PackageAuthorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        source, run, baseline, official = [root / name for name in ("source", "run", "baseline", "official")]
        code = source / "scripts/run_experiment.py"
        write(code, "print('fixture')\n")
        matrix_code = source / "scripts/run_full_matrix.py"
        write(matrix_code, "print('fixture matrix')\n")
        write(source / "tests/test_solver.py", "def test_fixture(): pass\n")
        idea = source / "idea/final.md"
        write(idea, "fixture idea\n")
        config = source / "data/raw/A题/data/config.txt"
        write(config, "fixture config\n")
        evaluator = source / "vendor/official_evaluator/evaluate.py"
        write(evaluator, "# original evaluator fixture\n")
        official_evaluator = official / "inputs/raw/A题/附件/code/evaluate.py"
        write(official_evaluator, evaluator.read_text(encoding="utf-8"))
        original_config = official / "inputs/raw/A题/附件/data/config.txt"
        write(original_config, config.read_text(encoding="utf-8"))
        problem = official / "inputs/problem/A题/problem.docx"
        write(problem, "fixture problem\n")
        attachment = official / "inputs/raw/A题/attachment.zip"
        attachment.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(attachment, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data/config.txt", config.read_text(encoding="utf-8"))
            archive.writestr("code/evaluate.py", evaluator.read_text(encoding="utf-8"))
            for case in sorted(packager.CASES):
                archive.writestr(f"data/{case}.json", "{}")
                write(source / "data/raw/A题/data" / f"{case}.json", "{}")
        registered = []
        for path in (official_evaluator, original_config, problem, attachment):
            registered.append({"path": path.relative_to(official).as_posix(),
                               "bytes": path.stat().st_size, "sha256": packager.digest(path)})
        write(official / "inputs/manifest.json", registered)

        cases = sorted(packager.CASES)
        sha = packager.plan_digest({"node_to_subgraph": {"1": 0}, "core_schedules": [[0]]})
        child_root = run / "batch_01"
        candidate_rows = []
        report_rows = []
        combo_status = {}
        for case in cases:
            for cores in range(1, 6):
                for scene in "ABC":
                    label = f"{case}/{cores}core/{scene}"
                    combo_status[label] = "AI_VERIFIED"
                    base = child_root / "cases" / case / f"{cores}core" / scene
                    selected = base / "candidates/base"
                    plan = {"node_to_subgraph": {"1": 0}, "core_schedules": [[0]]}
                    makespan = int(case[-3:]) * 100 + cores
                    raw = {"makespan": makespan, "data_movement_bytes": {"added_copy_bytes": 12}}
                    write(base / "final_plan.json", plan)
                    write(base / "final_selection.json", {"candidate": "base", "plan_sha256": sha,
                                                         "makespan": makespan, "added_copy_bytes": 12})
                    write(selected / "plan.json", plan)
                    write(selected / "result.json", raw)
                    write(selected / "result_check.json", {"status": "AI_VERIFIED", "makespan": makespan,
                                                               "added_copy_bytes": 12})
                    candidate_rows.append({"case": case, "cores": cores, "scene": scene,
                                           "candidate": "base", "status": "AI_VERIFIED",
                                           "plan_sha256": sha, "makespan": makespan})
                    report_rows.append({"case": case, "cores": cores, "scene": scene,
                                        "status": "AI_VERIFIED", "final_plan_sha256": sha,
                                        "final_makespan": makespan, "final_added_copy_bytes": 12})
        source_hashes = {"scripts/run_experiment.py": packager.digest(code),
                         "scripts/run_full_matrix.py": packager.digest(matrix_code)}
        official_hashes = {"evaluate.py": packager.digest(evaluator)}
        write(run / "run_manifest.json", {"status": "COMPUTED", "cases": cases,
                                          "cores": [1, 2, 3, 4, 5], "scenes": ["A", "B", "C"],
                                          "config_sha256": packager.digest(config),
                                          "solver_source_sha256": source_hashes,
                                          "batches": [{"batch": 1, "cases": cases, "status": "COMPUTED", "returncode": 0}]})
        write(child_root / "run_manifest.json", {"status": "COMPUTED", "cases": cases,
                                                  "cores": [1, 2, 3, 4, 5], "scenes": ["A", "B", "C"],
                                                  "config": "data/raw/A题/data/config.txt",
                                                  "config_sha256": packager.digest(config),
                                                  "idea": "idea/final.md", "idea_sha256": packager.digest(idea),
                                                  "solver_source_sha256": source_hashes,
                                                  "official_code_sha256": official_hashes,
                                                  "combination_status": combo_status})
        write_rows(child_root / "metrics.csv", candidate_rows)
        write_rows(run / "metrics.csv", candidate_rows)
        report_csv = root / "report.csv"
        write_rows(report_csv, report_rows)

        baseline_rows = []
        for case in cases:
            makespan = int(case[-3:]) * 100
            write(baseline / "batch_01/cases" / case / "result.json", {"makespan": makespan})
            baseline_rows.append({"case": case, "status": "AI_VERIFIED", "makespan": makespan})
        write(baseline / "run_manifest.json", {"status": "COMPUTED", "official_code_sha256": official_hashes,
                                               "batches": [{"batch": 1, "cases": cases,
                                                            "status": "COMPUTED", "returncode": 0}]})
        write(baseline / "batch_01/run_manifest.json", {"status": "COMPUTED", "cases": cases,
                                                        "official_code_sha256": official_hashes})
        write_rows(baseline / "batch_01/metrics.csv", baseline_rows)
        write_rows(baseline / "metrics.csv", baseline_rows)
        cls.args = SimpleNamespace(source_root=source, run_root=run, baseline_root=baseline,
                                   official_workspace=official, evaluator_dir=evaluator.parent, report_csv=report_csv)
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_fixture_packages_and_verifies_archive(self):
        files, report = packager.audit(self.args)
        self.assertEqual((report["main_combinations"], report["baseline_cases"]), (1500, 100))
        result = packager.package(files, report, self.root / "author.zip")
        self.assertEqual(result["status"], "AUDIT_PASSED")
        with zipfile.ZipFile(self.root / "author.zip") as archive:
            self.assertIsNone(archive.testzip())
            manifest = json.loads(archive.read("MANIFEST.json"))
            self.assertEqual(len(manifest["files"]), len(files))

    def test_compact_candidate_retains_raw_hashes_and_discloses_omission(self):
        files, report = packager.audit(self.args)
        output = self.root / "compact.zip"
        result = packager.package(files, report, output, compact=True, full_archive=self.root / "author.zip")
        self.assertEqual(result["package_kind"], "COMPACT_SUBMISSION_CANDIDATE")
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            self.assertIn("RAW_RESULT_HASHES.csv", names)
            self.assertNotIn("run/batch_01/cases/case_001/1core/A/candidates/base/result.json", names)
            self.assertIn("run/batch_01/cases/case_001/1core/A/final_plan.json", names)
            self.assertEqual(len(archive.read("RAW_RESULT_HASHES.csv").splitlines()), 1601)
            self.assertIn("incomplete for full raw-result reproduction", archive.read("README.md").decode())

    def test_missing_selected_result_is_refused(self):
        path = self.args.run_root / "batch_01/cases/case_001/1core/A/candidates/base/result.json"
        saved = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaisesRegex(packager.AuditError, "missing or linked file"):
                packager.audit(self.args)
        finally:
            path.write_bytes(saved)

    def test_duplicate_report_combination_is_refused(self):
        path = self.args.report_csv
        saved = path.read_bytes()
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(saved.decode("utf-8").splitlines()[1] + "\n")
            with self.assertRaisesRegex(packager.AuditError, "expected 1500"):
                packager.audit(self.args)
        finally:
            path.write_bytes(saved)

    def test_changed_evaluator_is_refused(self):
        path = self.args.evaluator_dir / "evaluate.py"
        saved = path.read_bytes()
        try:
            path.write_text("# changed\n", encoding="utf-8")
            with self.assertRaisesRegex(packager.AuditError, "selected evaluator differs"):
                packager.audit(self.args)
        finally:
            path.write_bytes(saved)

    def test_changed_graph_is_refused(self):
        path = self.args.source_root / "data/raw/A题/data/case_001.json"
        saved = path.read_bytes()
        try:
            path.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaisesRegex(packager.AuditError, "solver input differs"):
                packager.audit(self.args)
        finally:
            path.write_bytes(saved)


if __name__ == "__main__":
    unittest.main()
