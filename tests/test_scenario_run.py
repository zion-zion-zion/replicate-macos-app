import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from support import make_app, run_script
from scenario_run import tree_sha256
import ledger_check

ORIGINAL_ID = "org.example.original"
REPLICA_ID = "org.example.replica"
SCRIPT = """#!/bin/sh
printf '%s\\n' "$1" > "$3/bundle.txt"
printf 'same\\n' > "$3/same.txt"
[ "$REPLICA_SIDE" = original ] && printf 'a\\n' > "$3/only-a.txt"
echo "ran $1 $2"
pwd
"""


class ScenarioRunTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve() / "project"
        self.root = self.project / "replica"
        (self.root / "scenarios").mkdir(parents=True)
        self.original = make_app(Path(temp.name) / "a", bundle_id=ORIGINAL_ID)
        self.replica = make_app(self.project, bundle_id=REPLICA_ID, name="Synthetic-replicate")
        self.write_records()
        self.write_script(SCRIPT)

    def write_records(self, version="1.0", replica_id=REPLICA_ID, kind="script"):
        ledger = {"app": {"path": str(self.original), "bundle_id": ORIGINAL_ID, "version": version, "build": "1"}}
        manifest = {"reference": {"bundle_id": replica_id, "artifact_path": "Synthetic-replicate.app"}}
        scenarios = {"scenarios": [{"id": "S-001", "kind": kind, "script": "scenarios/S-001.sh"}]}
        for name, data in (("feature-ledger.json", ledger), ("reference-manifest.json", manifest),
                           ("scenarios.json", scenarios)):
            (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def write_script(self, text):
        self.script = self.root / "scenarios" / "S-001.sh"
        self.script.write_text(text, encoding="utf-8")
        os.chmod(self.script, 0o755)

    def run_scenario(self, *args):
        proc = run_script("scenario_run.py", self.project, "S-001", *args)
        return proc, json.loads(proc.stdout) if proc.stdout else None

    def test_runs_both_sides_and_compares_outputs(self):
        proc, report = self.run_scenario()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(report["compare"], {"original_run": report["runs"]["original"]["evidence"]["path"],
                                             "identical": ["same.txt"], "different": ["bundle.txt"],
                                             "only_original": ["only-a.txt"], "only_replica": []})
        for side, bundle_id, app in (("original", ORIGINAL_ID, self.original),
                                     ("replica", REPLICA_ID, self.replica)):
            with self.subTest(side):
                entry = report["runs"][side]
                self.assertEqual(entry["exit_code"], 0)
                self.assertEqual(entry["evidence"]["kind"], "run")
                run_path = self.root / entry["evidence"]["path"]
                self.assertTrue(entry["evidence"]["path"].startswith(f"evidence/runs/S-001/{side}-"))
                run = json.loads(run_path.read_text(encoding="utf-8"))
                self.assertEqual((run["scenario"], run["side"], run["bundle_id"], run["app_path"]),
                                 ("S-001", side, bundle_id, str(app)))
                self.assertEqual(run["script_sha256"], hashlib.sha256(self.script.read_bytes()).hexdigest())
                self.assertEqual(run["argv"][1:3], [bundle_id, str(app)])
                self.assertFalse(run["timed_out"])
                stdout = (run_path.parent / "stdout.txt").read_text(encoding="utf-8").splitlines()
                self.assertEqual(stdout[0], f"ran {bundle_id} {app}")
                self.assertEqual(Path(stdout[1]).resolve(), self.root)
                self.assertEqual((run_path.parent / "bundle.txt").read_text(encoding="utf-8"), f"{bundle_id}\n")
                value = {"evidence": [{**entry["evidence"], "note": "运行记录"}]}
                checker = ledger_check.Checker(self.root, ORIGINAL_ID, REPLICA_ID)
                checker.replica_tree = tree_sha256(self.replica)
                checker.evidence(f"S-001.{side}", value["evidence"], True, side, "S-001")
                checker.runs(f"S-001.{side}", value, side, run["script_sha256"])
                self.assertEqual(checker.errors, [])
        original_run = json.loads((self.root / report["runs"]["original"]["evidence"]["path"]).read_text(encoding="utf-8"))
        replica_run = json.loads((self.root / report["runs"]["replica"]["evidence"]["path"]).read_text(encoding="utf-8"))
        self.assertIsNone(original_run["app_sha256"])
        self.assertEqual(replica_run["app_sha256"], tree_sha256(self.replica))
        self.assertEqual(replica_run["compare"], report["compare"])

    def read_run(self, report, side):
        return json.loads((self.root / report["runs"][side]["evidence"]["path"]).read_text(encoding="utf-8"))

    def test_replica_only_run_compares_with_latest_original(self):
        _, first = self.run_scenario()
        proc, report = self.run_scenario("--side", "replica")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(list(report["runs"]), ["replica"])
        self.assertEqual(report["compare"]["original_run"], first["runs"]["original"]["evidence"]["path"])
        self.assertEqual(report["compare"]["only_original"], ["only-a.txt"])
        self.assertEqual(self.read_run(report, "replica")["compare"], report["compare"])

    def test_replica_only_run_skips_stale_original(self):
        self.run_scenario()
        self.write_script(SCRIPT + "echo changed\n")
        proc, report = self.run_scenario("--side", "replica")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("compare", report)
        self.assertNotIn("compare", self.read_run(report, "replica"))

    def test_failed_original_is_not_recorded_as_comparison(self):
        self.write_script('#!/bin/sh\n[ "$REPLICA_SIDE" = original ] && exit 3\nexit 0\n')
        proc, report = self.run_scenario()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("compare", report)
        self.assertNotIn("compare", self.read_run(report, "replica"))

    def test_tree_hash_tracks_app_content(self):
        (self.replica / "Contents" / "Resources").mkdir()
        (self.replica / "Contents" / "Resources" / "data.txt").write_text("一\n", encoding="utf-8")
        os.symlink("Resources/data.txt", self.replica / "Contents" / "link.txt")
        before = tree_sha256(self.replica)
        copy = self.project / "copy" / self.replica.name
        shutil.copytree(self.replica, copy, symlinks=True)
        self.assertEqual(tree_sha256(copy), before)
        (copy / "Contents" / "Resources" / "data.txt").write_text("二\n", encoding="utf-8")
        self.assertNotEqual(tree_sha256(copy), before)

    def test_failed_side_exits_nonzero(self):
        self.write_script('#!/bin/sh\n[ "$REPLICA_SIDE" = replica ] && exit 3\nexit 0\n')
        proc, report = self.run_scenario()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual((report["runs"]["original"]["exit_code"], report["runs"]["replica"]["exit_code"]), (0, 3))

    def test_timeout_is_recorded(self):
        self.write_script("#!/bin/sh\necho started\nexec sleep 5\n")
        proc, report = self.run_scenario("--side", "original", "--timeout", "0.5")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(list(report["runs"]), ["original"])
        self.assertNotIn("compare", report)
        entry = report["runs"]["original"]
        self.assertEqual((entry["exit_code"], entry["timed_out"]), (None, True))

    def test_rejects_invalid_targets(self):
        cases = [
            ("B 的 bundle id 不一致", {"replica_id": "org.example.other"}, "CFBundleIdentifier 是 org.example.replica"),
            ("B 还未填写", {"replica_id": None}, "先在 reference-manifest.json 填写"),
            ("A 的版本已变化", {"version": "0.9"}, "原版 A 已变为 1.0（1）"),
            ("不是 script 场景", {"kind": "gui"}, "只执行 script 场景"),
        ]
        for name, changes, fragment in cases:
            with self.subTest(name):
                self.write_records(**changes)
                proc = run_script("scenario_run.py", self.project, "S-001")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn(fragment, proc.stderr)
                self.assertFalse((self.root / "evidence").exists())


if __name__ == "__main__":
    unittest.main()
