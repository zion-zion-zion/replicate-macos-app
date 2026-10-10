import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import init_project, macos_only, make_app

RECORDS = [".gitignore", "feature-ledger.json", "scenarios.json",
           "reference-manifest.json", "progress.md"]


def swiftc_available():
    return sys.platform == "darwin" and subprocess.run(
        ["xcrun", "--find", "swiftc"], capture_output=True).returncode == 0


@macos_only
class InitializationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / "reference project"
        self.root = self.project / "replica"
        self.app = make_app(self.base)

    def initialize(self, *flags, env=None):
        proc = init_project(self.project, self.app, *flags, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def read(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def change_info(self, **values):
        path = self.app / "Contents" / "Info.plist"
        info = plistlib.loads(path.read_bytes())
        info.update(values)
        path.write_bytes(plistlib.dumps(info))

    def test_new_project_records(self):
        result = self.initialize("--skip-ax")
        self.assertEqual(sorted(Path(p).name for p in result["created"]), sorted(RECORDS))
        self.assertEqual(result["ax"]["status"], "skipped")
        self.assertFalse((self.root / "bin" / "ax").exists())
        self.assertTrue((self.root / "evidence").is_dir())
        self.assertTrue((self.root / "scenarios").is_dir())

        ledger = self.read("feature-ledger.json")
        self.assertEqual(ledger["schema_version"], 4)
        self.assertEqual(ledger["app"]["bundle_id"], "org.example.synthetic")
        self.assertTrue(ledger["macos"]["version"])
        self.assertEqual(self.read("scenarios.json"), {"schema_version": 4, "scenarios": []})

        manifest = self.read("reference-manifest.json")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["role"], "reference_app_construction")
        self.assertEqual(manifest["original"]["bundle_id"], "org.example.synthetic")
        self.assertEqual(manifest["reference"]["name"], "Synthetic-replicate")
        for name in ("fidelity", "independence", "reset"):
            self.assertEqual(manifest["verification"][name]["status"], "pending")
        self.assertEqual(manifest["verification"]["known_differences"], [])
        self.assertIsNone(manifest["freeze"]["artifact_sha256"])

        progress = (self.root / "progress.md").read_text(encoding="utf-8")
        self.assertTrue(progress.startswith("# 复刻进度"))
        self.assertIn("org.example.synthetic", progress)
        self.assertIn("复刻版 B：Synthetic-replicate", progress)

    def test_replica_name_prefers_display_name(self):
        self.change_info(CFBundleDisplayName="Synthetic Pro")
        self.initialize("--skip-ax")
        self.assertEqual(self.read("reference-manifest.json")["reference"]["name"],
                         "Synthetic Pro-replicate")

    def test_old_project_only_gains_missing_manifest(self):
        self.initialize("--skip-ax")
        (self.root / "reference-manifest.json").unlink()
        (self.root / "progress.md").write_text("已有调查记录\n", encoding="utf-8")
        before = self.snapshot()
        result = self.initialize("--skip-ax")
        self.assertEqual([Path(p).name for p in result["created"]], ["reference-manifest.json"])
        for name, content in before.items():
            self.assertEqual((self.project / name).read_bytes(), content)

    def test_rerun_preserves_all_existing_records(self):
        self.initialize("--skip-ax")
        path = self.root / "reference-manifest.json"
        manifest = self.read("reference-manifest.json")
        manifest["construction"]["methods"] = [{"name": "自写分析器"}]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        before = self.snapshot()
        result = self.initialize("--skip-ax")
        self.assertEqual(result["created"], [])
        self.assertEqual(self.snapshot(), before)

    def test_identity_mismatch_stops_without_changes(self):
        for key, value in (("CFBundleIdentifier", "org.example.other"), ("CFBundleVersion", "2")):
            with self.subTest(key=key):
                self.initialize("--skip-ax")
                before = self.snapshot()
                original = plistlib.loads((self.app / "Contents" / "Info.plist").read_bytes())
                self.change_info(**{key: value})
                proc = init_project(self.project, self.app, "--skip-ax")
                self.assertEqual(proc.returncode, 2)
                self.assertIn("不一致", proc.stderr)
                self.assertEqual(self.snapshot(), before)
                self.change_info(**{key: original[key]})

    def test_invalid_bundle_does_not_create_project(self):
        proc = init_project(self.project, self.base / "missing.app", "--skip-ax")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("不是有效的 App bundle", proc.stderr)
        self.assertFalse(self.project.exists())

    def test_missing_toolchain_keeps_records(self):
        # PATH 只保留 sw_vers，xcrun 找不到
        tools = self.base / "tools"
        tools.mkdir()
        os.symlink("/usr/bin/sw_vers", tools / "sw_vers")
        result = self.initialize(env={"PATH": str(tools)})
        self.assertEqual(result["ax"]["status"], "unavailable")
        self.assertIn("xcrun", result["ax"]["error"])
        self.assertEqual(len(result["created"]), len(RECORDS))

    def test_compile_failure_is_reported(self):
        result = self.initialize(env={"DEVELOPER_DIR": str(self.base / "missing-developer-dir")})
        self.assertEqual(result["ax"]["status"], "unavailable")
        self.assertIn("swiftc", result["ax"]["error"])
        self.assertEqual(len(result["created"]), len(RECORDS))

    @unittest.skipUnless(swiftc_available(), "需要 Xcode Command Line Tools 中的 swiftc")
    def test_builds_then_reuses_ax(self):
        result = self.initialize()
        self.assertEqual(result["ax"]["status"], "built")
        binary = self.root / "bin" / "ax"
        self.assertTrue(os.access(binary, os.X_OK))
        usage = subprocess.run([str(binary)], text=True, capture_output=True)
        self.assertEqual(usage.returncode, 1)
        self.assertIn("ax dump BUNDLE_ID", usage.stderr)
        self.assertEqual(self.initialize()["ax"]["status"], "reused")


if __name__ == "__main__":
    unittest.main()
