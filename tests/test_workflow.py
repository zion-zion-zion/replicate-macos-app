import contextlib
import copy
import io
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import init_project
import ledger_check


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "reference project"
        self.app = self.base / "Original App.app"
        (self.app / "Contents").mkdir(parents=True)
        self.info = {
            "CFBundleIdentifier": "org.example.original",
            "CFBundleName": "Original App",
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
        }
        self.write_info()
        mock = patch.object(init_project, "macos_identity",
                            return_value={"version": "test", "build": "test-build"})
        mock.start()
        self.addCleanup(mock.stop)

    def write_info(self):
        (self.app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(self.info))

    def initialize(self, **kwargs):
        return init_project.initialize(self.project, self.app, **kwargs)

    def read(self, name):
        return json.loads((self.project / "replica" / name).read_text(encoding="utf-8"))

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_new_project_has_pending_reference_manifest(self):
        result = self.initialize(skip_ax=True)
        self.assertEqual(len(result["created"]), 5)
        self.assertEqual(self.read("feature-ledger.json")["schema_version"], 4)
        self.assertEqual(self.read("scenarios.json")["schema_version"], 4)
        manifest = self.read("reference-manifest.json")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["role"], "reference_app_construction")
        self.assertEqual(manifest["original"]["bundle_id"], "org.example.original")
        self.assertEqual(manifest["verification"]["independence"]["status"], "pending")
        self.assertIsNone(manifest["freeze"]["artifact_sha256"])

    def test_skip_ax_does_not_compile(self):
        with patch.object(init_project, "build_ax") as build:
            result = self.initialize(skip_ax=True)
        build.assert_not_called()
        self.assertEqual(result["ax"]["status"], "skipped")

    def test_default_still_uses_ax_when_available(self):
        with patch.object(init_project, "build_ax", return_value={"status": "built"}) as build:
            result = self.initialize()
        build.assert_called_once()
        self.assertEqual(result["ax"]["status"], "built")

    def test_missing_ax_toolchain_does_not_block_records(self):
        with patch.object(init_project, "build_ax", side_effect=FileNotFoundError("xcrun")):
            result = self.initialize()
        self.assertEqual(result["ax"]["status"], "unavailable")
        self.assertEqual(len(result["created"]), 5)
        self.assertTrue((self.project / "replica" / "progress.md").is_file())

    def test_ax_compilation_failure_is_reported(self):
        with patch.object(init_project, "build_ax",
                          side_effect=subprocess.CalledProcessError(1, ["swiftc"])):
            result = self.initialize()
        self.assertEqual(result["ax"]["status"], "unavailable")
        self.assertIn("swiftc", result["ax"]["error"])

    def test_old_project_only_gains_missing_manifest(self):
        self.initialize(skip_ax=True)
        root = self.project / "replica"
        (root / "reference-manifest.json").unlink()
        (root / "progress.md").write_text("Existing investigation\n", encoding="utf-8")
        before = self.snapshot()
        result = self.initialize(skip_ax=True)
        self.assertEqual([Path(p).name for p in result["created"]], ["reference-manifest.json"])
        for name, content in before.items():
            self.assertEqual((self.project / name).read_bytes(), content)

    def test_rerun_preserves_all_existing_records(self):
        self.initialize(skip_ax=True)
        path = self.project / "replica" / "reference-manifest.json"
        manifest = self.read("reference-manifest.json")
        manifest["construction"]["methods"] = [{"name": "custom analyzer"}]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        before = self.snapshot()
        result = self.initialize(skip_ax=True)
        self.assertEqual(result["created"], [])
        self.assertEqual(self.snapshot(), before)

    def test_target_identity_mismatch_does_not_change_records(self):
        self.initialize(skip_ax=True)
        before = self.snapshot()
        self.info["CFBundleIdentifier"] = "org.example.other"
        self.write_info()
        with self.assertRaises(ValueError):
            self.initialize(skip_ax=True)
        self.assertEqual(self.snapshot(), before)

    def test_original_version_mismatch_does_not_change_records(self):
        self.initialize(skip_ax=True)
        before = self.snapshot()
        self.info["CFBundleVersion"] = "2"
        self.write_info()
        with self.assertRaises(ValueError):
            self.initialize(skip_ax=True)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_bundle_does_not_create_project(self):
        with self.assertRaises(ValueError):
            init_project.initialize(self.project, self.base / "missing.app", skip_ax=True)
        self.assertFalse(self.project.exists())

    def test_cli_accepts_skip_ax_and_emits_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            init_project.main([str(self.project), "--app-path", str(self.app), "--skip-ax"])
        self.assertEqual(json.loads(output.getvalue())["ax"]["status"], "skipped")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "observation.txt").write_text("Synthetic test evidence\n", encoding="utf-8")

    def feature(self, kind="runtime", status="observed"):
        return {
            "id": "F-001", "name": "Synthetic operation", "preconditions": [],
            "expected": ["Expected output"], "status": status, "blocker": None,
            "evidence": [{"kind": kind, "path": "observation.txt",
                          "note": "Synthetic fixture from an arbitrary tool"}],
        }

    def test_arbitrary_runtime_tool_evidence_is_accepted(self):
        checker = ledger_check.Checker(self.root)
        checker.feature(self.feature(), 1)
        self.assertEqual(checker.errors, [])

    def test_static_evidence_supports_a_hypothesis(self):
        checker = ledger_check.Checker(self.root)
        checker.feature(self.feature("static", "hypothesis"), 1)
        self.assertEqual(checker.errors, [])

    def test_static_evidence_alone_cannot_mark_observed(self):
        checker = ledger_check.Checker(self.root)
        checker.feature(self.feature("static", "observed"), 1)
        self.assertTrue(checker.errors)

    def test_generic_evidence_requires_an_existing_file(self):
        for kind in ("static", "runtime"):
            for path in (None, "missing.txt"):
                with self.subTest(kind=kind, path=path):
                    item = {"kind": kind, "note": "Synthetic fixture"}
                    if path is not None:
                        item["path"] = path
                    checker = ledger_check.Checker(self.root)
                    checker.evidence("F-001", [item])
                    self.assertTrue(checker.errors)

    def write_records(self, features, scenarios, inventory=None):
        inventory = inventory or []
        used = {item["kind"] for item in inventory}
        ledger = {
            "schema_version": 4, "inventory": inventory, "features": features,
            "absent_entry_kinds": {
                kind: "Synthetic test fixture: not applicable"
                for kind in ledger_check.ENTRY_KINDS if kind not in used
            },
        }
        (self.root / "feature-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (self.root / "scenarios.json").write_text(
            json.dumps({"schema_version": 4, "scenarios": scenarios}), encoding="utf-8")

    def test_empty_records_cannot_pass_final_even_with_absent_categories(self):
        self.write_records([], [])
        checker, _ = ledger_check.check(self.root, final=True)
        self.assertEqual(len(checker.errors), 2)

    def test_empty_records_remain_valid_during_initialization(self):
        self.write_records([], [])
        checker, _ = ledger_check.check(self.root, final=False)
        self.assertEqual(checker.errors, [])

    def test_existing_schema_and_legacy_ax_evidence_still_pass(self):
        feature = self.feature("ax", "passed")
        side = {"result": "Synthetic output", "evidence": copy.deepcopy(feature["evidence"])}
        scenario = {
            "id": "S-001", "features": ["F-001"], "kind": "gui", "fixtures": [],
            "steps": ["Synthetic step"], "checks": ["Synthetic check"],
            "original": copy.deepcopy(side), "replica": copy.deepcopy(side),
            "differences": [], "status": "passed", "blocker": None,
        }
        self.write_records([feature], [scenario],
                           [{"kind": "menu", "path": "Synthetic menu", "feature": "F-001"}])
        checker, summary = ledger_check.check(self.root, final=True)
        self.assertEqual(checker.errors, [])
        self.assertEqual(summary["features"]["status"], {"passed": 1})


if __name__ == "__main__":
    unittest.main()