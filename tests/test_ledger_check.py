import copy
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from support import make_app, run_script
import ledger_check

ORIGINAL = {"path": "/Applications/Synthetic.app", "bundle_id": "org.example.original",
            "name": "Synthetic", "version": "1.0", "build": "1"}
REPLICA_ID = "org.example.replica"
REPLICA_NAME = "Synthetic-replicate"
MENU = "MenuBar > MenuBarItem[合成] > MenuItem[运行合成]"
INVENTORY = [{"kind": "menu", "path": MENU, "feature": "F-001"}]
NIB = "Contents/Resources/Main.storyboardc"
CLUES = [{"source": "nib", "name": NIB, "feature": "F-001"}]
DUMP = "evidence/ax/original/main.txt"
# 除 MENU 外都应被覆盖统计排除：Apple 菜单、分隔线、窗口控制按钮、表格内生成的元素
DUMP_LINES = [
    "MenuBar",
    "MenuBar > MenuBarItem[Apple]",
    "MenuBar > MenuBarItem[Apple] > MenuItem[关于本机]",
    "MenuBar > MenuBarItem[合成]",
    f"{MENU}\tshortcut=⌘R",
    "MenuBar > MenuBarItem[合成] > MenuItem",
    "Window[合成]",
    "Window[合成] > Button\tsubrole=AXCloseButton",
    "Window[合成] > ScrollArea > Table > Row#1 > Cell > TextField\tvalue=合成",
]
STATES = [{"id": "ST-001", "name": "主窗口", "reach": "启动 A", "dumps": [DUMP]}]


def write_dump(path, lines, bundle_id=ORIGINAL["bundle_id"], version="1.0", build="1"):
    header = {"bundle_id": bundle_id, "version": version, "build": build, "pid": 1,
              "app_path": None, "root": None, "taken_at": "2026-01-01T00:00:00Z"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# ax-dump " + json.dumps(header) + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def evidence(kind="gui", path="evidence/observation.txt"):
    return {"kind": kind, "path": path, "note": "合成证据"}


def feature(**changes):
    item = {"id": "F-001", "name": "合成功能", "preconditions": [], "expected": ["合成结果"],
            "status": "passed", "blocker": None, "evidence": [evidence("ax", DUMP)]}
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
        self.project = Path(temp.name)
        self.root = self.project / "replica"
        (self.root / "evidence").mkdir(parents=True)
        (self.root / "evidence" / "observation.txt").write_text("合成证据\n", encoding="utf-8")
        write_dump(self.root / DUMP, DUMP_LINES)
        bundle = {"entries": {}, "resources": {"nibs": [NIB]}, "stack": {}}
        (self.root / "evidence" / "bundle").mkdir()
        (self.root / "evidence" / "bundle" / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        make_app(self.project, bundle_id=REPLICA_ID, name=REPLICA_NAME)
        artifact = self.project / f"{REPLICA_NAME}-1.0.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.write(self.project / f"{REPLICA_NAME}.app" / "Contents" / "Info.plist",
                          f"{REPLICA_NAME}.app/Contents/Info.plist")
        self.manifest = {
            "schema_version": 2,
            "reference": {"name": REPLICA_NAME, "bundle_id": REPLICA_ID,
                          "artifact_path": f"{REPLICA_NAME}.app", "build_command": "make",
                          "launch_command": "open", "reset_command": "make reset"},
            "verification": {"fidelity": {"status": "passed", "evidence": ["evidence/observation.txt"]},
                             "independence": {"status": "pending", "evidence": []},
                             "reset": {"status": "passed", "evidence": ["evidence/observation.txt"]}},
            "freeze": {"reference_version": "1.0", "frozen_at": "2026-01-01T00:00:00Z",
                       "source_revision": "abc123", "artifact": artifact.name,
                       "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
        }

    def write(self, features, scenarios, inventory=INVENTORY, absent=None, clues=CLUES,
              manifest=None, states=STATES, **extra):
        if absent is None:
            covered = {item["kind"] for item in inventory if "feature" in item}
            absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS if kind not in covered}
        ledger = {"schema_version": 6, "app": ORIGINAL, "inventory": inventory, "clues": clues,
                  "states": states, "features": features, "absent_entry_kinds": absent, **extra}
        (self.root / "feature-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (self.root / "scenarios.json").write_text(
            json.dumps({"schema_version": 6, "scenarios": scenarios}), encoding="utf-8")
        (self.root / "reference-manifest.json").write_text(
            json.dumps(self.manifest if manifest is None else manifest), encoding="utf-8")

    def check(self, features=None, scenarios=None, final=True, **kwargs):
        self.write([feature()] if features is None else features,
                   [scenario()] if scenarios is None else scenarios, **kwargs)
        checker, summary = ledger_check.check(self.root, final)
        return checker.errors, summary

    def assertError(self, errors, fragment):
        self.assertTrue(any(fragment in error for error in errors),
                        f"没有包含「{fragment}」的错误：{errors}")

    def assertNoError(self, errors, fragment):
        self.assertFalse(any(fragment in error for error in errors),
                         f"不应出现包含「{fragment}」的错误：{errors}")


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
        for kind in ledger_check.PATH_EVIDENCE:
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


class OriginTests(LedgerTestCase):
    def test_feature_evidence_from_replica_dump_is_rejected(self):
        write_dump(self.root / "evidence/ax/replica/main.txt", DUMP_LINES, bundle_id=REPLICA_ID)
        errors, _ = self.check([feature(evidence=[evidence("ax", "evidence/ax/replica/main.txt")])])
        self.assertError(errors, f"F-001: 证据来自 {REPLICA_ID}，这里需要原版 A")

    def test_ax_evidence_requires_dump_header(self):
        errors, _ = self.check([feature(evidence=[evidence("ax")])])
        self.assertError(errors, "第一行以 # ax-dump 开头")

    def test_state_evidence_origin(self):
        state = self.root / "evidence" / "state"
        state.mkdir()
        for name, app in (("a.json", {"bundle_id": ORIGINAL["bundle_id"]}), ("b.json", {"bundle_id": REPLICA_ID}),
                          ("diff.json", "org.example.other")):
            (state / name).write_text(json.dumps({"app": app}), encoding="utf-8")
        (state / "notes.txt").write_text("手写说明\n", encoding="utf-8")
        cases = [
            ("A 一侧用了 B 的快照", {"original": side(evidence=[evidence(), evidence("state", "evidence/state/b.json")])},
             f"S-001.original: 证据来自 {REPLICA_ID}"),
            ("B 一侧用了 A 的快照", {"replica": side(evidence=[evidence("state", "evidence/state/a.json")])},
             "S-001.replica: 证据来自原版 A"),
            ("B 一侧来自其他 App", {"replica": side(evidence=[evidence("state", "evidence/state/diff.json")])},
             f"复刻版 B 的 bundle identifier 是 {REPLICA_ID}"),
            ("state 证据不是快照", {"replica": side(evidence=[evidence("state", "evidence/state/notes.txt")])},
             "state 证据需要 state_diff.py"),
        ]
        for name, changes, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(scenarios=[scenario(**changes)])
                self.assertError(errors, fragment)


class RecordTests(LedgerTestCase):
    def test_valid_records_pass_final(self):
        errors, summary = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(summary["features"]["status"], {"passed": 1})
        self.assertEqual(summary["entry_kinds"]["covered"], ["menu"])
        self.assertEqual(summary["entry_kinds"]["unchecked"], [])
        self.assertEqual(summary["clues"], {"required": 1, "mapped": 1, "skipped": 0, "unmapped": []})
        self.assertEqual(summary["reference"]["name"], REPLICA_NAME)
        self.assertTrue(summary["reference"]["frozen"])

    def test_empty_records(self):
        errors, _ = self.check([], [], final=False, inventory=[], clues=[])
        self.assertEqual(errors, [])
        errors, _ = self.check([], [], final=True, inventory=[], clues=[])
        self.assertError(errors, "非空的功能清单")
        self.assertError(errors, "非空的验证场景")

    def test_scenario_rules(self):
        cases = [
            ("失败场景缺少差异", {"status": "failed"}, "失败的场景需要写明 differences"),
            ("通过场景仍有差异", {"differences": ["页边距不同"]}, "不能有未解决的 differences"),
            ("通过场景缺少原版结果", {"original": side(result=None)}, "需要记录 original.result"),
            ("gui 通过场景缺少证据文件", {"replica": side(evidence=[])}, "S-001.replica: 需要至少一个存在的证据文件"),
            ("automated 通过场景缺少 B 的证据文件", {"kind": "automated", "replica": side(evidence=[])},
             "S-001.replica: 需要至少一个存在的证据文件"),
            ("A 的结果只有静态线索", {"original": side(evidence=[evidence("static")])}, "静态线索不能作为 A 的结果"),
            ("fixture 不存在", {"fixtures": ["evidence/fixtures/missing.db"]}, "fixture 不存在"),
            ("script 场景缺少脚本", {"kind": "script", "script": "scenarios/missing.sh"}, "需要存在的脚本文件"),
            ("阻塞场景缺少 blocker", {"status": "blocked"}, "blocked 时 blocker 需要"),
            ("非阻塞场景填写 blocker", {"blocker": {"kind": "server", "detail": "原厂服务"}}, "状态不是 blocked"),
            ("关联不存在的功能", {"features": ["F-001", "F-999"]}, "关联了不存在的功能 F-999"),
            ("缺少步骤", {"steps": []}, "steps 需要至少一步"),
        ]
        for name, changes, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(scenarios=[scenario(**changes)])
                self.assertError(errors, fragment)

    def test_automated_scenario_needs_no_original_file(self):
        original = side(evidence=[{"kind": "user", "note": "用户提供的 A 的输出"}])
        errors, _ = self.check(scenarios=[scenario(kind="automated", original=original)])
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
        errors, _ = self.check(inventory=[])
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
                errors, _ = self.check(inventory=inventory)
                self.assertError(errors, fragment)

    def test_absent_kind_cannot_be_covered(self):
        absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS}
        errors, _ = self.check(absent=absent)
        self.assertError(errors, "absent_entry_kinds.menu: 已有入口指向功能")

    def test_skip_only_kind_stays_unchecked(self):
        inventory = [*INVENTORY, {"kind": "service", "path": "服务菜单", "skip": "系统提供的服务子菜单"}]
        absent = {kind: "合成记录：不适用" for kind in ledger_check.ENTRY_KINDS
                  if kind not in ("menu", "service")}
        errors, summary = self.check(inventory=inventory, absent=absent)
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
        ledger["schema_version"] = 5
        (self.root / "feature-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        checker, _ = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "feature-ledger.json: schema_version 应为 6")

        (self.root / "scenarios.json").unlink()
        checker, _ = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "缺少")

    def test_cli_exit_status(self):
        self.write([feature()], [scenario()])
        proc = run_script("ledger_check.py", self.project, "--final")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["errors"], [])
        self.write([feature(status="hypothesis")], [scenario()])
        proc = run_script("ledger_check.py", self.project, "--final")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(json.loads(proc.stdout)["errors"])


class ScriptRunTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.script = self.root / "scenarios" / "S-001.sh"
        self.script.parent.mkdir()
        self.script.write_text("#!/bin/sh\n", encoding="utf-8")
        self.item = scenario(kind="script", script="scenarios/S-001.sh")

    def write_run(self, name, side_name, **changes):
        run = {"scenario": "S-001", "side": side_name, "bundle_id": ORIGINAL["bundle_id"], "app_sha256": None,
               "script": "scenarios/S-001.sh", "exit_code": 0,
               "script_sha256": hashlib.sha256(self.script.read_bytes()).hexdigest()}
        if side_name == "replica":
            run.update(bundle_id=REPLICA_ID,
                       app_sha256=ledger_check.tree_sha256(self.project / f"{REPLICA_NAME}.app"),
                       compare={"original_run": "evidence/runs/a/run.json", "identical": ["out.txt"],
                                "different": [], "only_original": [], "only_replica": []})
        run.update(changes)
        path = self.root / "evidence" / "runs" / name / "run.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(run), encoding="utf-8")
        return str(path.relative_to(self.root))

    def with_runs(self, original, replica, **changes):
        return scenario(kind="script", script="scenarios/S-001.sh",
                        original=side(evidence=[evidence(), evidence("run", original)]),
                        replica=side(evidence=[evidence("run", replica)]), **changes)

    def test_script_must_be_executable(self):
        errors, _ = self.check(scenarios=[self.item])
        self.assertError(errors, "脚本不可执行")

    def test_passed_script_scenario_needs_runs_on_both_sides(self):
        os.chmod(self.script, 0o755)
        errors, _ = self.check(scenarios=[self.item])
        self.assertError(errors, "S-001.original: 通过的 script 场景需要当前脚本在 original 一侧成功运行")
        self.assertError(errors, "S-001.replica: 通过的 script 场景需要当前脚本在 replica 一侧成功运行")
        item = self.with_runs(self.write_run("a", "original"), self.write_run("b", "replica"))
        errors, _ = self.check(scenarios=[item])
        self.assertEqual(errors, [])

    def test_final_requires_replica_run_on_current_build(self):
        os.chmod(self.script, 0o755)
        item = self.with_runs(self.write_run("a", "original"), self.write_run("b", "replica", app_sha256="0" * 64))
        errors, _ = self.check(scenarios=[item], final=False)
        self.assertEqual(errors, [])
        errors, _ = self.check(scenarios=[item])
        self.assertError(errors, "S-001.replica: 通过的 script 场景需要当前脚本在 replica 一侧成功运行")
        self.assertError(errors, "当前的 reference.artifact_path 构建")
        self.assertNoError(errors, "S-001.original")

    def test_replica_run_needs_compare(self):
        os.chmod(self.script, 0o755)
        item = self.with_runs(self.write_run("a", "original"), self.write_run("b", "replica", compare=None))
        errors, _ = self.check(scenarios=[item], final=False)
        self.assertError(errors, "S-001.replica: 通过的 script 场景需要当前脚本在 replica 一侧成功运行")
        self.assertError(errors, "B 一侧的 run 需要带 compare")

    def test_compare_differences_need_normalization(self):
        os.chmod(self.script, 0o755)
        compare = {"original_run": "evidence/runs/a/run.json", "identical": [], "different": ["export.pdf"],
                   "only_original": [], "only_replica": ["debug.log"]}
        original = self.write_run("a", "original")
        replica = self.write_run("b", "replica", compare=compare)
        errors, _ = self.check(scenarios=[self.with_runs(original, replica)])
        self.assertError(errors, "S-001: compare 中 export.pdf 两侧内容不同")
        self.assertError(errors, "S-001: compare 中 debug.log 只在 B 一侧出现")
        rules = {"export.pdf": "比较页数和文字内容，忽略创建时间", "debug.log": "B 的调试日志，不属于 A 的行为"}
        errors, _ = self.check(scenarios=[self.with_runs(original, replica, normalization=rules)])
        self.assertEqual(errors, [])
        errors, _ = self.check(scenarios=[self.with_runs(original, replica, normalization=["export.pdf"])])
        self.assertError(errors, "S-001: normalization 需要是「输出文件: 比较规则」的对象")

    def test_run_records_must_match(self):
        os.chmod(self.script, 0o755)
        cases = [
            ("脚本已修改", {"script_sha256": "0" * 64}, "original 一侧成功运行"),
            ("运行失败", {"exit_code": 1}, "original 一侧成功运行"),
            ("属于其他场景", {"scenario": "S-002"}, "run 证据属于场景 S-002"),
            ("来自 B 的运行", {"side": "replica", "bundle_id": REPLICA_ID}, "run 证据来自 replica 一侧"),
        ]
        for index, (name, changes, fragment) in enumerate(cases):
            with self.subTest(name):
                item = self.with_runs(self.write_run(f"a{index}", "original", **changes),
                                      self.write_run(f"b{index}", "replica"))
                errors, _ = self.check(scenarios=[item])
                self.assertError(errors, fragment)


class AXCoverageTests(LedgerTestCase):
    def add_lines(self, *lines, path=DUMP):
        write_dump(self.root / path, [*DUMP_LINES, *lines])

    def test_only_operable_elements_count(self):
        errors, summary = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(summary["ax"], {"dumps": [DUMP], "interactive": 1, "covered": 1, "uncovered": 0,
                                         "uncovered_entries": [], "wildcards": {}})

    def test_unregistered_element_blocks_final(self):
        self.add_lines("Window[合成] > Toolbar > Button[刷新]")
        errors, summary = self.check(final=False)
        self.assertEqual(errors, [])
        self.assertEqual(summary["ax"]["uncovered_entries"],
                         [{"kind": "toolbar", "path": "Window[合成] > Toolbar > Button[刷新]"}])
        errors, _ = self.check()
        self.assertError(errors, "1 个可操作元素没有登记到 inventory")

    def test_skip_entry_covers_its_submenu(self):
        services = "MenuBar > MenuBarItem[合成] > MenuItem[服务]"
        self.add_lines(services, f"{services} > MenuItem[系统服务]")
        inventory = [*INVENTORY, {"kind": "menu", "path": services, "skip": "系统提供的服务子菜单"}]
        errors, summary = self.check(inventory=inventory)
        self.assertEqual(errors, [])
        self.assertEqual(summary["ax"]["uncovered"], 0)

    def test_wildcard_label_matches_dynamic_segments(self):
        self.assertTrue(ledger_check.segment_matches("Window[*]", "Window[a.txt]#2"))
        self.assertFalse(ledger_check.segment_matches("Window[*]", "Window#2"))
        self.assertFalse(ledger_check.segment_matches("Window[*]", "WindowGroup[a.txt]"))
        bold = "Toolbar > Button[粗体]"
        self.add_lines(f"Window[a.txt] > {bold}", f"Window[a.txt]#2 > {bold}", f"Window[b.txt] > {bold}",
                       f"Window > {bold}")
        pattern = f"Window[*] > {bold}"
        inventory = [*INVENTORY, {"kind": "toolbar", "path": pattern, "feature": "F-001"}]
        errors, summary = self.check(inventory=inventory, final=False)
        self.assertEqual(errors, [])
        self.assertEqual(summary["ax"]["wildcards"], {pattern: 3})
        self.assertEqual(summary["ax"]["uncovered_entries"], [{"kind": "toolbar", "path": f"Window > {bold}"}])

    def test_wildcard_skip_covers_children(self):
        recent = "MenuBar > MenuBarItem[合成] > MenuItem[最近打开]"
        self.add_lines(recent, f"{recent} > MenuItem[a.txt]", f"{recent} > MenuItem[a.txt] > MenuItem[详情]")
        inventory = [*INVENTORY, {"kind": "menu", "path": recent, "feature": "F-001"},
                     {"kind": "menu", "path": f"{recent} > MenuItem[*]", "skip": "最近文件列表，由打开功能覆盖"}]
        errors, summary = self.check(inventory=inventory)
        self.assertEqual(errors, [])
        self.assertEqual(summary["ax"]["uncovered"], 0)

    def test_wildcard_must_match_a_dump(self):
        pattern = "Window[*] > Button[不存在]"
        inventory = [*INVENTORY, {"kind": "window", "path": pattern, "feature": "F-001"}]
        errors, _ = self.check(inventory=inventory)
        self.assertError(errors, f"inventory[1]: AX 路径不在原版 A 的任何 AX 导出中 {pattern}")

    def test_inventory_paths_come_from_original_dumps(self):
        typo = "MenuBar > MenuBarItem[合成] > MenuItem[运行 合成]"
        write_dump(self.root / "evidence/ax/replica/main.txt", [typo], bundle_id=REPLICA_ID)
        inventory = [*INVENTORY, {"kind": "menu", "path": typo, "feature": "F-001"}]
        errors, _ = self.check(inventory=inventory)
        self.assertError(errors, f"inventory[1]: AX 路径不在原版 A 的任何 AX 导出中 {typo}")

    def test_dump_from_another_version_is_rejected(self):
        write_dump(self.root / "evidence/ax/original/old.txt", DUMP_LINES, version="0.9")
        errors, summary = self.check()
        self.assertError(errors, "evidence/ax/original/old.txt: AX 导出来自 A 的 0.9（1）")
        self.assertEqual(summary["ax"]["dumps"], [DUMP])

    def test_final_requires_dump_or_reason(self):
        (self.root / DUMP).unlink()
        features = [feature(evidence=[evidence()])]
        states = [{**STATES[0], "dumps": []}]
        errors, _ = self.check(features, states=states)
        self.assertError(errors, "交付前需要原版 A 的 AX 导出")
        self.assertError(errors, "ST-001: 交付前每个状态需要至少一份 A 的 AX 导出")
        errors, _ = self.check(features, states=states, ax_unavailable="A 使用自绘界面，AX 只能读到窗口")
        self.assertEqual(errors, [])
        errors, _ = self.check(features, states=states, ax_unavailable="")
        self.assertError(errors, "ax_unavailable: 需要写明")

    def test_cli_lists_uncovered_on_request(self):
        self.add_lines(*(f"Window[合成] > Button[按钮 {index:02}]" for index in range(25)))
        self.write([feature()], [scenario()])
        proc = run_script("ledger_check.py", self.project)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        ax = json.loads(proc.stdout)["ax"]
        self.assertEqual((ax["uncovered"], len(ax["uncovered_entries"])), (25, ledger_check.UNCOVERED_SAMPLE))
        proc = run_script("ledger_check.py", self.project, "--uncovered")
        self.assertEqual(len(json.loads(proc.stdout)["ax"]["uncovered_entries"]), 25)


class StateTests(LedgerTestCase):
    def test_final_requires_states(self):
        errors, summary = self.check(states=[], final=False)
        self.assertEqual(errors, [])
        self.assertEqual(summary["states"], {"total": 0, "with_dump": 0})
        errors, _ = self.check(states=[])
        self.assertError(errors, "交付前需要在 states 列出 A 的各个界面状态")

    def test_state_without_dump_blocks_final_only(self):
        states = [*STATES, {"id": "ST-002", "name": "设置 > 通用", "reach": "合成 > 设置…", "dumps": []}]
        errors, summary = self.check(states=states, final=False)
        self.assertEqual(errors, [])
        self.assertEqual(summary["states"], {"total": 2, "with_dump": 1})
        errors, _ = self.check(states=states)
        self.assertError(errors, "ST-002: 交付前每个状态需要至少一份 A 的 AX 导出")

    def test_state_rules(self):
        write_dump(self.root / "evidence/ax/replica/main.txt", DUMP_LINES, bundle_id=REPLICA_ID)
        write_dump(self.root / "evidence/ax/original/old.txt", DUMP_LINES, version="0.9")
        base = STATES[0]
        cases = [
            ("id 格式错误", {"id": "state-1"}, "id 格式应为 ST-001"),
            ("缺少到达方式", {"reach": " "}, "状态需要 name 和 reach"),
            ("dumps 不是数组", {"dumps": DUMP}, "dumps 必须是 AX 导出的路径数组"),
            ("dumps 不是 AX 导出", {"dumps": ["evidence/observation.txt"]}, "dumps 需要 ax dump 的逐行输出"),
            ("dumps 来自 B", {"dumps": ["evidence/ax/replica/main.txt"]}, "不是功能清单记录的原版 A 的 AX 导出"),
            ("dumps 来自 A 的其他版本", {"dumps": ["evidence/ax/original/old.txt"]}, "不是功能清单记录的原版 A 的 AX 导出"),
        ]
        for name, changes, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(states=[{**base, **changes}], final=False)
                self.assertError(errors, fragment)
        errors, _ = self.check(states=[base, copy.deepcopy(base)], final=False)
        self.assertError(errors, "states: ID 重复 ST-001")


class ClueTests(LedgerTestCase):
    def test_unmapped_clue_blocks_final(self):
        errors, summary = self.check(clues=[])
        self.assertError(errors, "clues: 1 条静态线索没有指向功能或写明 skip")
        self.assertEqual(summary["clues"]["unmapped"], [{"source": "nib", "name": NIB}])

    def test_clue_rules(self):
        cases = [
            ("bundle.json 中没有", [*CLUES, {"source": "nib", "name": "Contents/Resources/Other.nib", "skip": "无界面"}],
             "bundle.json 中没有 nib Contents/Resources/Other.nib"),
            ("skip 没写原因", [{"source": "nib", "name": NIB, "skip": " "}], "skip 需要写明原因"),
            ("来源不合法", [*CLUES, {"source": "binary", "name": "Synthetic"}], "需要合法的 source"),
            ("线索重复", [*CLUES, copy.deepcopy(CLUES[0])], "线索重复 nib"),
        ]
        for name, clues, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(clues=clues)
                self.assertError(errors, fragment)

    def test_final_requires_bundle_scan(self):
        (self.root / "evidence" / "bundle" / "bundle.json").unlink()
        errors, _ = self.check(final=False, clues=[])
        self.assertEqual(errors, [])
        errors, _ = self.check(clues=[])
        self.assertError(errors, "先运行 bundle_scan.py")

    def test_bundle_clue_sources(self):
        bundle = {
            "entries": {"xpc_services": [{"name": "Helper.xpc"}], "extensions": [{"name": "Share.appex"}],
                        "helpers": ["Login.app"], "other_plugins": ["Import.qlgenerator"],
                        "library": {"QuickLook": ["Preview.qlgenerator"]}, "app_intents": [{"id": "OpenIntent"}]},
            "resources": {"nibs": [NIB], "sqlite_databases": {"Contents/Resources/Sample.db": {}},
                          "core_data_models": ["Contents/Resources/Model.momd"]},
            "stack": {"embedded_frameworks": ["Sparkle.framework"]},
        }
        self.assertEqual(ledger_check.bundle_clues(bundle), [
            ("nib", NIB), ("framework", "Sparkle.framework"), ("xpc", "Helper.xpc"),
            ("extension", "Share.appex"), ("helper", "Login.app"), ("plugin", "Import.qlgenerator"),
            ("library", "QuickLook/Preview.qlgenerator"), ("app_intent", "OpenIntent"),
            ("database", "Contents/Resources/Sample.db"), ("data_model", "Contents/Resources/Model.momd"),
        ])


class ManifestTests(LedgerTestCase):
    def changed(self, section, **changes):
        manifest = copy.deepcopy(self.manifest)
        manifest[section].update(changes)
        return manifest

    def test_manifest_rules(self):
        cases = [
            ("artifact_path 不是 .app", self.changed("reference", artifact_path=f"{REPLICA_NAME}-1.0.zip"),
             "artifact_path: 需要指向 B 的 .app"),
            ("bundle id 与 A 相同", self.changed("reference", bundle_id=ORIGINAL["bundle_id"]), "不能与原版 A 相同"),
            ("名称与 .app 不一致", self.changed("reference", name="Synthetic"),
             f".app 文件名 是 {REPLICA_NAME}，需要使用 B 的名称 Synthetic"),
            ("缺少构建命令", self.changed("reference", build_command=None), "build_command: 交付前需要填写"),
            ("未冻结", self.changed("freeze", artifact=None), "freeze.artifact: 交付前需要冻结版本"),
            ("制品哈希不一致", self.changed("freeze", artifact_sha256="0" * 64), "与制品的实际 SHA-256 不一致"),
            ("passed 缺少证据", self.changed("verification", reset={"status": "passed", "evidence": []}),
             "verification.reset: passed 需要证据"),
            ("状态不合法", self.changed("verification", reset={"status": "done", "evidence": []}),
             "verification.reset: status 取值"),
            ("fidelity 未通过", self.changed("verification", fidelity={"status": "pending", "evidence": []}),
             "verification.fidelity: 交付前需要 passed"),
            ("reset 未通过", self.changed("verification", reset={"status": "failed", "evidence": []}),
             "verification.reset: 交付前需要 passed"),
            ("schema 版本过旧", {**self.manifest, "schema_version": 1}, "reference-manifest.json: schema_version 应为 2"),
        ]
        for name, manifest, fragment in cases:
            with self.subTest(name):
                errors, _ = self.check(manifest=manifest)
                self.assertError(errors, fragment)

    def test_display_name_must_match(self):
        make_app(self.project, bundle_id=REPLICA_ID, name=REPLICA_NAME,
                 extra={"CFBundleDisplayName": ORIGINAL["name"]})
        errors, _ = self.check()
        self.assertError(errors, f"CFBundleDisplayName 是 {ORIGINAL['name']}")

    def test_bundle_identifier_must_match(self):
        make_app(self.project, bundle_id="org.example.other", name=REPLICA_NAME)
        errors, _ = self.check()
        self.assertError(errors, f".app 的 CFBundleIdentifier 是 org.example.other，记录的是 {REPLICA_ID}")

    def test_final_requires_manifest(self):
        self.write([feature()], [scenario()])
        (self.root / "reference-manifest.json").unlink()
        checker, summary = ledger_check.check(self.root, False)
        self.assertEqual(checker.errors, [])
        self.assertIsNone(summary["reference"])
        checker, _ = ledger_check.check(self.root, True)
        self.assertError(checker.errors, "缺少")

    def test_unfrozen_manifest_passes_during_development(self):
        manifest = self.changed("freeze", artifact=None, artifact_sha256=None)
        manifest["reference"]["artifact_path"] = None
        errors, summary = self.check(final=False, manifest=manifest)
        self.assertEqual(errors, [])
        self.assertFalse(summary["reference"]["frozen"])


if __name__ == "__main__":
    unittest.main()
