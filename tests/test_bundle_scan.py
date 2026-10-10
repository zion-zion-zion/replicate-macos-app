import json
import plistlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from support import init_project, macos_only, make_app, run_script

INFO = {
    "CFBundleDevelopmentRegion": "en",
    "CFBundleDocumentTypes": [{"CFBundleTypeName": "合成文档", "CFBundleTypeRole": "Editor",
                               "LSItemContentTypes": ["org.example.synthetic.document"],
                               "CFBundleTypeExtensions": ["syn"],
                               "NSDocumentClass": "SyntheticDocument"}],
    "CFBundleURLTypes": [{"CFBundleURLName": "org.example.synthetic",
                          "CFBundleURLSchemes": ["synthetic"]}],
    "NSServices": [{"NSMenuItem": {"default": "用合成 App 打开"}, "NSMessage": "openText",
                    "NSSendTypes": ["NSStringPboardType"]}],
    "NSCameraUsageDescription": "合成 App 需要使用摄像头",
}


@macos_only
class BundleScanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.app = make_app(base, extra=INFO)
        resources = self.app / "Contents" / "Resources"
        for region, text in (("en", '"greeting" = "Hello";\n"farewell" = "Bye";\n'),
                             ("fr", '"greeting" = "Bonjour";\n')):
            (resources / f"{region}.lproj").mkdir(parents=True)
            (resources / f"{region}.lproj" / "Localizable.strings").write_text(text, encoding="utf-8")
        (resources / "defaults.json").write_text('{"theme": "light"}\n', encoding="utf-8")
        with sqlite3.connect(resources / "seed.sqlite") as connection:
            connection.execute("CREATE TABLE items (name TEXT)")
            connection.executemany("INSERT INTO items VALUES (?)", [("a",), ("b",)])
        connection.close()
        extension = self.app / "Contents" / "PlugIns" / "Share.appex" / "Contents"
        extension.mkdir(parents=True)
        (extension / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "org.example.synthetic.share",
            "NSExtension": {"NSExtensionPointIdentifier": "com.apple.share-services"}}))

        self.project = base / "project"
        proc = init_project(self.project, self.app, "--skip-ax")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.output = self.project / "replica" / "evidence" / "bundle"

    def scan(self):
        proc = run_script("bundle_scan.py", self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def test_summary_counts_declared_entries(self):
        summary = self.scan()
        self.assertEqual(summary["files"], ["evidence/bundle/bundle.json", "evidence/bundle/strings.json"])
        self.assertTrue(summary["traits"]["declares_documents"])
        self.assertEqual(summary["traits"]["document_classes"], ["SyntheticDocument"])
        counts = summary["counts"]
        for key, value in (("document_types", 1), ("url_schemes", 1), ("services", 1),
                           ("extensions", 1), ("strings", 2), ("sqlite_databases", 1),
                           ("data_files", 1), ("nibs", 0), ("assets", 0)):
            self.assertEqual(counts[key], value, key)

    def test_report_details(self):
        self.scan()
        report = self.read("bundle.json")
        self.assertEqual(report["identity"]["bundle_id"], "org.example.synthetic")
        self.assertEqual(report["identity"]["development_region"], "en")
        entries = report["entries"]
        self.assertEqual(entries["document_types"][0]["extensions"], ["syn"])
        self.assertEqual(entries["url_schemes"], [{"name": "org.example.synthetic", "schemes": ["synthetic"]}])
        self.assertEqual(entries["services"][0]["menu_item"], "用合成 App 打开")
        self.assertEqual(entries["extensions"], [{"name": "Share.appex",
                                                  "bundle_id": "org.example.synthetic.share",
                                                  "extension_point": "com.apple.share-services"}])
        self.assertIn("NSCameraUsageDescription", report["usage_descriptions"])

        resources = report["resources"]
        self.assertEqual(resources["localizations"], ["en", "fr"])
        self.assertEqual(resources["string_region_directories"], ["en.lproj"])
        self.assertEqual(resources["sqlite_databases"]["Contents/Resources/seed.sqlite"]["row_counts"],
                         {"items": 2})
        self.assertEqual(resources["data_files"], ["Contents/Resources/defaults.json"])
        # 只保留开发语言的资源，fr.lproj 不计入
        self.assertEqual(resources["suffix_counts"], {".strings": 1, ".json": 1, ".sqlite": 1})

        strings = self.read("strings.json")
        self.assertEqual(strings["tables"], {"en.lproj/Localizable.strings":
                                             {"greeting": "Hello", "farewell": "Bye"}})

    def test_empty_strings_file_is_empty_table(self):
        (self.app / "Contents" / "Resources" / "en.lproj" / "Empty.strings").write_bytes(b"")
        self.scan()
        self.assertEqual(self.read("strings.json")["tables"]["en.lproj/Empty.strings"], {})

    def test_missing_app_stops(self):
        shutil.rmtree(self.app)
        proc = run_script("bundle_scan.py", self.project)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("功能清单记录的 App 不存在", proc.stderr)


if __name__ == "__main__":
    unittest.main()
