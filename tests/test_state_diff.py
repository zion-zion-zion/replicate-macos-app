import json
import plistlib
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from support import init_project, macos_only, make_app, run_script


def insert_rows(path, *names):
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE IF NOT EXISTS items (name TEXT)")
        connection.executemany("INSERT INTO items VALUES (?)", [(name,) for name in names])
    connection.close()


@macos_only
class StateDiffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        # 每次使用新的 bundle identifier，不会碰到真实的偏好设置域
        self.bundle_id = f"org.example.synthetic.{uuid.uuid4().hex}"
        self.app = make_app(base, bundle_id=self.bundle_id)
        self.project = base / "project"
        proc = init_project(self.project, self.app, "--skip-ax")
        self.assertEqual(proc.returncode, 0, proc.stderr)

        # HOME 指向临时目录，~/Library 下的扫描位置都在测试目录内
        self.env = {"HOME": str(base / "home")}
        self.support = base / "home" / "Library" / "Application Support" / self.bundle_id
        self.support.mkdir(parents=True)
        (self.support / "state.json").write_text("{}", encoding="utf-8")

        self.data = base / "data"
        self.data.mkdir()
        (self.data / "note.txt").write_text("one", encoding="utf-8")
        (self.data / "obsolete.txt").write_text("old", encoding="utf-8")
        (self.data / "settings.plist").write_bytes(plistlib.dumps({"count": 1}))
        insert_rows(self.data / "store.sqlite", "a")

    def state(self, *args):
        proc = run_script("state_diff.py", *args, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def snapshot(self, name, *extra):
        return self.state("snapshot", self.project, name, "--path", self.data, *extra)

    def test_snapshot_lists_preferences_and_locations(self):
        summary = self.snapshot("before")
        self.assertEqual(summary["snapshot"], "evidence/state/before.json")
        self.assertEqual(summary["app"], self.bundle_id)
        self.assertEqual(summary["preferences"], {self.bundle_id: 0, f"{self.bundle_id} (currentHost)": 0})
        self.assertEqual(summary["locations"][str(self.support)], 1)
        self.assertEqual(summary["locations"][str(self.data)], 4)

    def test_diff_reports_file_plist_and_sqlite_changes(self):
        self.snapshot("before")
        (self.data / "note.txt").write_text("two!", encoding="utf-8")
        (self.data / "added.txt").write_text("new", encoding="utf-8")
        (self.data / "obsolete.txt").unlink()
        (self.data / "settings.plist").write_bytes(plistlib.dumps({"count": 2}))
        insert_rows(self.data / "store.sqlite", "b")
        (self.support / "state.json").write_text('{"opened": true}', encoding="utf-8")
        self.snapshot("after")

        shown = self.state("diff", self.project, "before", "after")
        self.assertEqual(shown["file"], "evidence/state/before--after.json")
        result = json.loads((self.project / "replica" / shown["file"]).read_text(encoding="utf-8"))
        self.assertEqual(result["preferences"], {})

        data = result["locations"][str(self.data)]
        self.assertEqual(data["added"], [{"path": "added.txt", "type": "file"}])
        self.assertEqual(data["removed"], [{"path": "obsolete.txt", "type": "file"}])
        modified = {item["path"]: item for item in data["modified"]}
        self.assertEqual(modified["note.txt"]["size"], [3, 4])
        self.assertEqual(modified["settings.plist"]["plist"], {"changed": {"count": [1, 2]}})
        self.assertEqual(modified["store.sqlite"]["sqlite"], {"row_counts": {"changed": {"items": [1, 2]}}})

        support = result["locations"][str(self.support)]
        self.assertEqual([item["path"] for item in support["modified"]], ["state.json"])

    def test_snapshot_name_must_be_new(self):
        self.snapshot("before")
        proc = run_script("state_diff.py", "snapshot", self.project, "before", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("已存在", proc.stderr)

    def test_diff_rejects_snapshots_of_different_apps(self):
        other = make_app(self.project.parent / "other", bundle_id=f"{self.bundle_id}.replica")
        self.snapshot("original")
        self.snapshot("replica", "--app-path", other)
        proc = run_script("state_diff.py", "diff", self.project, "original", "replica", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("不同 App", proc.stderr)


if __name__ == "__main__":
    unittest.main()
