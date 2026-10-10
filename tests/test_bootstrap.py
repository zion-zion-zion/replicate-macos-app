import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  将 scripts 加入 sys.path
import bootstrap


def plan(*actions, status="planned"):
    return {"status": status, "plannedActions": [{"kind": kind, "id": action_id} for kind, action_id in actions]}


def registration(version, state="drifted", command=None):
    command = command if command is not None else ["npx", "-y", f"rea-agents@{version}", "mcp"]
    return {"codex_registration": state, "registered_command": command,
            "registered_package_version": version}


class VersionTests(unittest.TestCase):
    def test_supported_node(self):
        cases = {"v22.19.0": True, "v22.18.9": False, "v23.5.0": False, "v24.10.0": False,
                 "v24.11.0": True, "v26.0.0": True, "v27.1.0": True, "v26.0.0-nightly": False,
                 "": False, None: False}
        for version, expected in cases.items():
            with self.subTest(version=version):
                self.assertIs(bootstrap.supported_node(version), expected)

    def test_version_core(self):
        self.assertEqual(bootstrap.version_core("6.1.0"), (6, 1, 0))
        self.assertEqual(bootstrap.version_core("6.2.0-beta.1"), (6, 2, 0))
        self.assertIsNone(bootstrap.version_core("latest"))
        self.assertIsNone(bootstrap.version_core(None))


class ReaPlanTests(unittest.TestCase):
    CODEX = ("configure_client", "configure_client:codex")
    SKILL = ("install_skill", "install_skill:rea")
    HOPPER = ("install_hopper", "install_hopper")

    def test_scoped_plan_is_accepted(self):
        bootstrap.verify_rea_plan(plan(self.CODEX, self.SKILL), with_hopper=False)
        bootstrap.verify_rea_plan(plan(self.CODEX, self.SKILL, self.HOPPER), with_hopper=True)

    def test_out_of_scope_plan_is_rejected(self):
        cases = {
            "其他客户端": (plan(("configure_client", "configure_client:claude")), False),
            "未选择 Hopper": (plan(self.CODEX, self.HOPPER), False),
            "未知操作": (plan(self.CODEX, ("remove_client", "remove_client:codex")), False),
            "未生成计划": (plan(self.CODEX, status="needs_human"), False),
        }
        for name, (value, with_hopper) in cases.items():
            with self.subTest(name):
                with self.assertRaises(RuntimeError):
                    bootstrap.verify_rea_plan(value, with_hopper)


class RegistrationTests(unittest.TestCase):
    def test_setup_allowed(self):
        for name, value in {"已一致": registration("6.2.0", state="aligned"),
                            "未注册": registration(None, state="missing", command=[]),
                            "相同版本": registration(bootstrap.REA_VERSION),
                            "旧版本": registration("6.0.0")}.items():
            with self.subTest(name):
                bootstrap.guard_rea_registration(value)

    def test_existing_registration_is_kept(self):
        for name, value in {"更新版本": registration("6.2.0"),
                            "latest": registration("latest"),
                            "本地路径": registration(None, command=["node", "/opt/rea/rea.mjs", "mcp"])}.items():
            with self.subTest(name):
                with self.assertRaises(RuntimeError):
                    bootstrap.guard_rea_registration(value)


class PluginTests(unittest.TestCase):
    def test_ready_plugin_is_reused(self):
        status = {"installed": True, "enabled": True, "plugin_ids": ["computer-use@openai-bundled"]}
        self.assertEqual(bootstrap.install_plugin("codex", "computer-use", status),
                         {"status": "ready", "plugin_id": "computer-use@openai-bundled"})

    def test_plugin_needing_user_action(self):
        cases = {
            "已安装未启用": ({"installed": True, "enabled": False, "plugin_ids": ["computer-use@a"]}, "未启用"),
            "没有来源": ({"installed": False, "enabled": False, "plugin_ids": []}, "marketplace"),
            "多个来源": ({"installed": False, "enabled": False,
                      "plugin_ids": ["computer-use@a", "computer-use@b"]}, "多个来源"),
        }
        for name, (status, fragment) in cases.items():
            with self.subTest(name):
                with self.assertRaisesRegex(RuntimeError, fragment):
                    bootstrap.install_plugin("codex", "computer-use", status)


class WriteJsonTests(unittest.TestCase):
    def test_replaces_file_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "installation.json"
            path.write_text("旧内容", encoding="utf-8")
            bootstrap.write_json(path, {"status": "checked", "名称": "合成"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                             {"status": "checked", "名称": "合成"})
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual([item.name for item in Path(temp).iterdir()], ["installation.json"])


if __name__ == "__main__":
    unittest.main()
