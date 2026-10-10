import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from support import run_script
import ledger_check

INVENTORY = [{"kind": "menu", "path": "MenuBar > MenuBarItem[合成]", "feature": "F-001"}]


def evidence(kind="gui"):
    return {"kind": kind, "path": "evidence/observation.txt", "note": "合成证据"}


def feature(**changes):
    item = {"id": "F-001", "name": "合成功能", "preconditions": [], "expected": ["合成结果"],
            "status": "passed", "blocker": None, "evidence": [evidence("ax")]}
    item.update(changes)
    return item


def side(**changes):
    item = {"result": "合成输出", "evidence": [evidence()]}
    item.update(changes)
    return item


def scenario(**changes):
    item = {"id": "S-001", "features": ["F-001"], "kind": "gui", "fixtures": [],
            "steps": ["合成步骤"], "checks": ["合成检查"], "original": side(), "replica": side(),
            "differences": [], "status": "passed", "blocker": None}
    item.update(changes)
    return item


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "replica"
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "evidence" / "observation.txt").write_text("合成证据\n", encoding="utf-8")

    def write(self, features, scenarios, inventory=INVENTORY, absent=None):
        if absent is None:
            covered = {item["kind"] for item in inventory if "feature" in item}
            absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS if kind not in covered}
        ledger = {"schema_version": 4, "inventory": inventory, "features": features,
                  "absent_entry_kinds": absent}
        (self.root / "feature-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (self.root / "scenarios.json").write_text(
            json.dumps({"schema_version": 4, "scenarios": scenarios}), encoding="utf-8")

    def check(self, features, scenarios, final=True, **kwargs):
        self.write(features, scenarios, **kwargs)
        checker, summary = ledger_check.check(self.root, final)
        return checker.errors, summary

    def assertError(self, errors, fragment):
        self.assertTrue(any(fragment in error for error in errors),
                        f"没有包含「{fragment}」的错误：{errors}")


class EvidenceTests(LedgerTestCase):
    def feature_errors(self, kind, status):
        checker = ledger_check.Checker(self.root)
        checker.feature(feature(status=status, evidence=[evidence(kind)]), 1)
        return checker.errors

    def test_runtime_evidence_from_any_tool_is_accepted(self):
        self.assertEqual(self.feature_errors("runtime", "observed"), [])

    def test_static_evidence_supports_a_hypothesis(self):
        self.assertEqual(self.feature_errors("static", "hypothesis"), [])

    def test_static_evidence_alone_cannot_mark_observed(self):
        self.assertError(self.feature_errors("static", "observed"), "在运行的原版上取得的证据")

    def test_path_evidence_requires_an_existing_file(self):
        for kind in ("ax", "state", "bundle", "static", "runtime"):
            for path in (None, "evidence/missing.txt"):
                with self.subTest(kind=kind, path=path):
                    item = {"kind": kind, "note": "合成证据"}
                    if path is not None:
                        item["path"] = path
                    checker = ledger_check.Checker(self.root)
                    checker.evidence("F-001", [item])
                    self.assertTrue(checker.errors)

    def test_doc_evidence_requires_url_or_path(self):
        checker = ledger_check.Checker(self.root)
        checker.evidence("F-001", [{"kind": "doc", "note": "官网说明"}])
        self.assertError(checker.errors, "doc 证据需要 url 或 path")
        checker = ledger_check.Checker(self.root)
        checker.evidence("F-001", [{"kind": "doc", "note": "官网说明", "url": "https://example.com"}])
        self.assertEqual(checker.errors, [])


class RecordTests(LedgerTestCase):
    def test_valid_records_pass_final(self):
        errors, summary = self.check([feature()], [scenario()])
        self.assertEqual(errors, [])
        self.assertEqual(summary["features"]["status"], {"passed": 1})
        self.assertEqual(summary["entry_kinds"]["covered"], ["menu"])
        self.assertEqual(summary["entry_kinds"]["unchecked"], [])

    def test_empty_records(self):
        errors, _ = self.check([], [], final=False, inventory=[])
        self.assertEqual(errors, [])
        errors, _ = self.check([], [], final=True, inventory=[])
        self.assertError(errors, "非空的功能清单")
        self.assertError(errors, "非空的验证场景")

    def test_scenario_rules(self):
        cases = [
            ("失败场景缺少差异", {"status": "failed"}, "失败的场景需要写明 differences"),
            ("通过场景仍有差异", {"differences": ["页边距不同"]}, "不能有未解决的 differences"),
            ("通过场景缺少原版结果", {"original": side(result=None)}, "需要记录 original.result"),
            ("gui 通过场景缺少证据文件", {"replica": side(evidence=[])}, "S-001.replica: 需要至少一个存在的证据文件"),
            ("script 场景缺少脚本", {"kind": "script", "script": "scenarios/missing.sh"}, "需要存在的脚本文件"),
            ("阻塞场景缺少 blocker", {"status": "blocked"}, "blocked 时 blocker 需要"),
            ("非阻塞场景填写 blocker", {"blocker": {"kind": "server", "detail": "原厂服务"}}, "状态不是 blocked"),
            ("关联不存在的功能", {"features": ["F-001", "F-999"]}, "关联了不存在的功能 F-999"),
            ("缺少步骤", {"steps": []}, "steps 需要至少一步"),
        ]
        for name, changes, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check([feature()], [scenario(**changes)])
                self.assertError(errors, fragment)

    def test_script_scenario_requires_executable(self):
        script = self.root / "scenarios" / "S-001.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        item = scenario(kind="script", script="scenarios/S-001.sh")
        errors, _ = self.check([feature()], [item])
        self.assertError(errors, "脚本不可执行")
        os.chmod(script, 0o755)
        errors, _ = self.check([feature()], [item])
        self.assertEqual(errors, [])

    def test_feature_rules(self):
        cases = [
            ("passed 缺少通过的场景", [feature()], [scenario(status="pending")], "passed 需要至少一个通过的关联场景"),
            ("passed 仍有失败场景", [feature()],
             [scenario(), scenario(id="S-002", status="failed", differences=["输出不同"])], "仍有失败的关联场景"),
            ("blocked 缺少 blocker", [feature(status="blocked")], [scenario()], "blocked 时 blocker 需要"),
            ("交付前仍是 hypothesis", [feature(status="hypothesis")], [scenario()], "交付前需要 passed 或 blocked"),
            ("observed 缺少 expected", [feature(status="observed", expected=[])], [scenario()], "需要写明 expected"),
            ("功能 ID 重复", [feature(), feature()], [scenario()], "ID 重复 F-001"),
            ("功能 ID 格式错误", [feature(id="feature-1")], [scenario(features=["feature-1"])], "id 格式应为 F-001"),
        ]
        for name, features, scenarios, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(features, scenarios)
                self.assertError(errors, fragment)

    def test_feature_needs_an_inventory_entry(self):
        errors, _ = self.check([feature()], [scenario()], inventory=[])
        self.assertError(errors, "inventory 中没有指向该功能的入口")

    def test_inventory_rules(self):
        menu = INVENTORY[0]
        cases = [
            ("同时填写 feature 和 skip", [{**menu, "skip": "系统提供"}], "feature 与 skip 需要二选一"),
            ("两者都没填", [menu, {"kind": "toolbar", "path": "工具栏按钮"}], "feature 与 skip 需要二选一"),
            ("指向不存在的功能", [menu, {"kind": "toolbar", "path": "工具栏按钮", "feature": "F-999"}], "指向不存在的功能 F-999"),
            ("入口重复", [menu, copy.deepcopy(menu)], "入口重复 menu"),
            ("类别不合法", [menu, {"kind": "gesture", "path": "三指轻点", "skip": "系统提供"}], "需要合法的 kind 和 path"),
        ]
        for name, inventory, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check([feature()], [scenario()], inventory=inventory)
                self.assertError(errors, fragment)

    def test_absent_kind_cannot_be_covered(self):
        absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS}
        errors, _ = self.check([feature()], [scenario()], absent=absent)
        self.assertError(errors, "absent_entry_kinds.menu: 已有入口指向功能")

    def test_skip_only_kind_stays_unchecked(self):
        inventory = [*INVENTORY, {"kind": "service", "path": "服务菜单", "skip": "系统提供的服务子菜单"}]
        absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS
                  if kind not in ("menu", "service")}
        errors, summary = self.check([feature()], [scenario()], inventory=inventory, absent=absent)
        self.assertEqual(summary["entry_kinds"]["unchecked"], ["service"])
        self.assertError(errors, "入口类别 service")

    def test_file_level_rules(self):
        self.write([feature()], [scenario()])
        (self.root / "scenarios.json").write_text("[]", encoding="utf-8")
        checker, summary = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "scenarios.json: 顶层必须是 JSON 对象")
        self.assertEqual(summary, {})

        self.write([feature()], [scenario()])
        ledger = json.loads((self.root / "feature-ledger.json").read_text(encoding="utf-8"))
        ledger["schema_version"] = 3
        (self.root / "feature-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        checker, _ = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "feature-ledger.json: schema_version 应为 4")

        (self.root / "scenarios.json").unlink()
        checker, _ = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "缺少")

    def test_cli_exit_status(self):
        project = self.root.parent
        self.write([feature()], [scenario()])
        proc = run_script("ledger_check.py", project, "--final")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["errors"], [])
        self.write([feature(status="hypothesis")], [scenario()])
        proc = run_script("ledger_check.py", project, "--final")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(json.loads(proc.stdout)["errors"])


if __name__ == "__main__":
    unittest.main()
