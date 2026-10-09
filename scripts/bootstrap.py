import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REA_VERSION = "6.1.0"
NETWORK_TIMEOUT = 600
HOPPER_TIMEOUT = 1800
PLUGINS = {"build_macos_apps": "build-macos-apps", "computer_use": "computer-use"}


def execute(argv, timeout):
    # 使用参数数组；不把路径或 JSON 当作 shell 代码。
    env = dict(os.environ, NO_COLOR="1")
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, env=env)


def failure(argv, proc):
    return RuntimeError(f"{argv[0]} 退出码 {proc.returncode}: "
                        f"{(proc.stderr or proc.stdout).strip()[-1600:]}")


def run(argv, timeout=60):
    proc = execute(argv, timeout)
    if proc.returncode:
        raise failure(argv, proc)
    return proc.stdout.strip()


def probe(argv):
    try:
        return run(argv, timeout=15)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return None


def supported_node(version):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version or "")
    if not match:
        return False
    major, minor, patch = map(int, match.groups())
    return ((major == 22 and (minor, patch) >= (19, 0))
            or (major == 24 and (minor, patch) >= (11, 0)) or major >= 26)


def version_core(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?", version or "")
    return tuple(map(int, match.groups())) if match else None


def state_dir():
    value = os.environ.get("REPLICA_STATE_DIR")
    return Path(value).expanduser().resolve() if value else Path.home() / ".local/share/replicate-macos-app"


def codex_cli():
    path = shutil.which("codex") or os.environ.get("CODEX_CLI_PATH")
    return path if path and Path(path).is_file() else None


def plugin_status(codex):
    listing = json.loads(run([codex, "plugin", "list", "--json", "--available"], timeout=NETWORK_TIMEOUT))
    report = {}
    for key, name in PLUGINS.items():
        entries = [item for group in ("installed", "available") for item in listing.get(group, [])
                   if item.get("name") == name]
        installed = [item for item in entries if item.get("installed")]
        report[key] = {"installed": bool(installed),
                       "enabled": any(item.get("enabled") for item in installed),
                       "plugin_ids": sorted({item["pluginId"] for item in installed or entries})}
    return report


def rea_json(*args, timeout=NETWORK_TIMEOUT):
    argv = ["npm", "exec", "--yes", f"--package=rea-agents@{REA_VERSION}",
            "--", "rea", *args, "--format", "json"]
    proc = execute(argv, timeout)
    # doctor 不健康、setup 需要人工处理时 REA 退出码为 1，stdout 仍是完整 JSON；由调用方按字段判断。
    try:
        value = json.loads(proc.stdout)
    except ValueError:
        raise failure(argv, proc) from None
    if not isinstance(value, dict):
        raise RuntimeError("REA 返回了非对象 JSON；停止写入并检查已安装版本。")
    return value


def inspect_rea():
    doctor = rea_json("doctor", "--client", "codex", "--skill")
    identity = doctor["identity"]
    codex = next((item for item in identity["registrations"] if item["client"] == "codex"),
                 {"state": "missing", "command": []})
    package_version = next((arg.split("@", 1)[1] for arg in codex["command"]
                            if arg.startswith("rea-agents@")), None)
    return {"doctor_healthy": doctor["healthy"],
            "codex_registration": codex["state"],
            "registered_command": codex["command"],
            "registered_package_version": package_version,
            "skill": identity["skill"]["state"],
            "skill_version": identity["skill"]["installed_version"]}


def check():
    mac = sys.platform == "darwin"
    version = probe(["node", "--version"]) if shutil.which("node") else None
    npm, npx = shutil.which("npm"), shutil.which("npx")
    node_ready = supported_node(version) and bool(npm and npx)
    codex = codex_cli()
    record = state_dir() / "installation.json"
    installed = {}
    if record.is_file():
        try:
            installed = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            installed = {"record_error": "安装记录不可读；重新核对实际依赖。"}
    return {
        "macos": mac, "python": sys.version.split()[0],
        "node_version": version, "node_supported": supported_node(version),
        "npm": npm, "npx": npx,
        "swift": probe(["xcrun", "--find", "swift"]) if mac else None,
        "codex_cli": codex,
        "plugins": plugin_status(codex) if codex else "unchecked: 找不到 codex CLI",
        "rea": inspect_rea() if mac and node_ready else "unchecked: 需要受支持的 Node.js 与 npm/npx",
        "live_session": "unknown: 安装状态不代表当前会话已加载 Computer Use、REA 和插件 Skills",
        "installation_record": installed,
    }


def install_plugin(codex, name, status):
    if status["installed"]:
        if not status["enabled"]:
            raise RuntimeError(f"{name} 已安装但未启用；请在 Codex 的 Plugins 中启用。")
        return {"status": "ready", "plugin_id": status["plugin_ids"][0]}
    candidates = status["plugin_ids"]
    if not candidates:
        raise RuntimeError(f"已配置的 marketplace 中没有 {name}；请在 Codex 桌面版的 Plugins 中安装。")
    if len(candidates) > 1:
        raise RuntimeError(f"{name} 有多个来源 {candidates}；请让用户选择后运行 "
                           f"codex plugin add {name}@<marketplace>。")
    result = json.loads(run([codex, "plugin", "add", candidates[0], "--json"], timeout=NETWORK_TIMEOUT))
    return {"status": "installed", "plugin_id": candidates[0], "result": result}


def verify_rea_plan(plan, with_hopper):
    if plan.get("status") != "planned" or not isinstance(plan.get("plannedActions"), list):
        raise RuntimeError("REA 未返回有效限定安装计划: "
                           + str(plan.get("remediation") or plan.get("status")))
    allowed = {"configure_client", "install_skill"}
    if with_hopper:
        allowed.add("install_hopper")
    for action in plan["plannedActions"]:
        if action.get("kind") not in allowed:
            raise RuntimeError("REA 计划包含请求范围之外的操作；未应用。")
        if action.get("kind") == "configure_client" and action.get("id") != "configure_client:codex":
            raise RuntimeError("REA 计划尝试配置非 Codex 客户端；未应用。")


def guard_rea_registration(rea):
    if rea["codex_registration"] == "aligned" or not rea["registered_command"]:
        return
    version = rea["registered_package_version"]
    if version == REA_VERSION:
        return
    current = version_core(version)
    if current is None or current > version_core(REA_VERSION):
        raise RuntimeError(
            f"Codex 已注册 REA（{' '.join(rea['registered_command'])}），版本更新或无法确定；"
            "保留现有注册，未执行 setup。")


def install_rea(root, with_hopper, rea):
    if rea["doctor_healthy"] and not with_hopper:
        return {"status": "ready", "version": rea["registered_package_version"]}
    guard_rea_registration(rea)
    extra = ["--install-hopper"] if with_hopper else []
    plan = rea_json("setup", "--client", "codex", "--dry-run", *extra)
    verify_rea_plan(plan, with_hopper)
    write_json(root / "rea-setup-plan.json", plan)
    print(json.dumps({"rea_plan": plan["plannedActions"]}, ensure_ascii=False), file=sys.stderr)
    result = rea_json("setup", "--client", "codex", "--yes", *extra,
                      timeout=HOPPER_TIMEOUT if with_hopper else NETWORK_TIMEOUT)
    write_json(root / "rea-setup-result.json", result)
    remediation = result.get("remediation")
    # macOS 装完 Hopper 后 REA 固定返回 needs_human，Codex 注册与 Skill 以 doctor 为准。
    if result.get("status") not in ("ready", "needs_human"):
        raise RuntimeError("REA setup 未完成: " + str(remediation or result.get("status")))
    health = rea_json("doctor", "--client", "codex", "--skill")
    write_json(root / "rea-doctor.json", health)
    if health.get("healthy") is not True:
        raise RuntimeError("REA 的限定 doctor 未通过: "
                           + str(remediation or "查看 rea-doctor.json 修复对应问题。"))
    if with_hopper and "hopperPath" not in result.get("doctor", {}):
        raise RuntimeError("Hopper 未安装: " + str(remediation))
    report = {"status": "configured", "version": REA_VERSION}
    if remediation:
        report["remediation"] = remediation
    return report


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent),
                                     prefix=".write-", delete=False) as handle:
        temp = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(args, readiness):
    if not readiness["macos"]:
        raise RuntimeError("安装必须在用户的 Mac 上运行；此环境不能准备该 Mac 的插件、MCP 或权限。")
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    report = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "plugins": {}, "rea": {}, "errors": [], "user_actions": []}

    # 各项分别记录结果，某一项失败后仍处理其余项。
    def attempt(section, key, action):
        try:
            section[key] = action()
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            section[key] = {"status": "failed", "error": str(exc)}
            report["errors"].append(f"{key}: {exc}")

    codex = readiness["codex_cli"]
    if codex:
        for key, name in PLUGINS.items():
            attempt(report["plugins"], key,
                    lambda: install_plugin(codex, name, readiness["plugins"][key]))
    else:
        report["errors"].append("插件安装需要 codex CLI；请安装 Codex CLI 或在 Codex 桌面版的 Plugins 中安装。")
    if isinstance(readiness["rea"], dict):
        attempt(report, "rea", lambda: install_rea(root, args.with_hopper, readiness["rea"]))
    else:
        report["errors"].append("REA 需要 Node.js 22.x >=22.19、24.x >=24.11 或稳定版 26+，以及 npm/npx。")

    if report["rea"].get("remediation"):
        report["user_actions"].append("REA: " + report["rea"]["remediation"])
    if not readiness["swift"]:
        report["user_actions"].append("准备可用的 Swift 工具链；需要 Xcode 的工程再安装或选择完整 Xcode。")
    report["user_actions"].append("按系统提示授予 Computer Use 屏幕录制和辅助功能权限，并允许访问目标 App；已授予时复用。")
    changed = [item for item in (*report["plugins"].values(), report["rea"])
               if item.get("status") in ("installed", "configured")]
    if changed:
        report["user_actions"].append("重启 Codex 加载新安装的插件和 MCP，随后在活动会话验证三个工具。")
    report["status"] = "partial" if report["errors"] else "dependencies_prepared"
    write_json(root / "installation.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="检查并准备 Computer Use、Build macOS Apps 插件与 REA MCP，仅配置 Codex。")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="只读检查，不写配置；首次运行会把 rea-agents 下载到 npm 缓存")
    mode.add_argument("--install", action="store_true", help="安装缺失的依赖，已就绪的项直接复用")
    parser.add_argument("--with-hopper", action="store_true", help="用户明确选择时安装 Hopper")
    args = parser.parse_args()
    if args.with_hopper and not args.install:
        parser.error("--with-hopper 需要 --install")
    try:
        readiness = check()
        report = install(args, readiness) if args.install else {"status": "checked", **readiness}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report.get("errors") else 0
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
