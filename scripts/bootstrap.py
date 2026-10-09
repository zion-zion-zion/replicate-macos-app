#!/usr/bin/env python3
"""检查并准备 Mac 上的 REA MCP 与官方原生开发 Skills。"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REA_VERSION = "6.1.0"
PLUGIN_REVISION = "0722921d5542fc593105c27bd52630babd8b8c2a"
PLUGIN_VERSION = "0.1.4"
PLUGIN_REPO = "https://github.com/openai/plugins.git"
SKILLS = (
    "build-run-debug", "test-triage", "signing-entitlements", "swiftpm-macos",
    "packaging-notarization", "swiftui-patterns", "liquid-glass",
    "window-management", "appkit-interop", "view-refactor", "telemetry",
)


def run(argv, timeout=60):
    # 使用参数数组；不把路径或 JSON 当作 shell 代码。
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", NO_COLOR="1")
    proc = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, env=env)
    if proc.returncode:
        raise RuntimeError(f"{argv[0]} 退出码 {proc.returncode}: "
                           f"{(proc.stderr or proc.stdout).strip()[-1600:]}")
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


def state_dir():
    value = os.environ.get("REPLICA_STATE_DIR")
    return Path(value).expanduser().resolve() if value else Path.home() / ".local/share/replicate-macos-app"


def skills_dir():
    value = os.environ.get("REPLICA_SKILLS_DIR")
    return Path(value).expanduser().resolve() if value else Path.home() / ".agents/skills"


def check():
    mac = sys.platform == "darwin"
    version = probe(["node", "--version"]) if shutil.which("node") else None
    git = bool(shutil.which("git") and probe(["git", "--version"]))
    swift = probe(["xcrun", "--find", "swift"]) if mac else None
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
        "npm": shutil.which("npm"), "npx": shutil.which("npx"),
        "git_ready": git, "swift": swift,
        "codex_config": str(Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")) / "config.toml"),
        "computer_use": "unknown: 需在活动会话检查开关、权限和实际画面",
        "live_rea_mcp": "unknown: 安装记录不代表当前会话已连接",
        "installation_record": installed,
    }


def verify_plugin(folder):
    manifest = folder / ".codex-plugin/plugin.json"
    if not manifest.is_file():
        raise RuntimeError("开发 Skills 的插件 manifest 缺失。")
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if metadata.get("name") != "build-macos-apps" or metadata.get("version") != PLUGIN_VERSION:
        raise RuntimeError("开发 Skills 的来源或版本不符合固定依赖。")
    missing = [name for name in SKILLS if not (folder / "skills" / name / "SKILL.md").is_file()]
    if missing:
        raise RuntimeError("开发 Skills 缺失: " + ", ".join(missing))


def ensure_plugin_cache(root):
    target = root / f"build-macos-apps-{PLUGIN_REVISION}"
    if target.exists():
        verify_plugin(target)
        if (target / "source-revision.txt").read_text().strip() != PLUGIN_REVISION:
            raise RuntimeError("现有依赖目录的 revision 不符；保留目录，请检查。")
        return target
    with tempfile.TemporaryDirectory(prefix=".upstream-", dir=str(root)) as temp:
        checkout = Path(temp) / "checkout"
        run(["git", "init", "--quiet", str(checkout)])
        run(["git", "-C", str(checkout), "sparse-checkout", "init", "--cone"])
        run(["git", "-C", str(checkout), "sparse-checkout", "set", "plugins/build-macos-apps"])
        run(["git", "-C", str(checkout), "fetch", "--quiet", "--depth", "1", PLUGIN_REPO, PLUGIN_REVISION])
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"])
        if run(["git", "-C", str(checkout), "rev-parse", "HEAD"]) != PLUGIN_REVISION:
            raise RuntimeError("下载内容未对应指定 Git revision。")
        plugin = checkout / "plugins/build-macos-apps"
        verify_plugin(plugin)
        # 上游不一定有根 LICENSE；保留插件 manifest 与实际存在的许可文件。
        for license_file in checkout.glob("LICENSE*"):
            if license_file.is_file():
                shutil.copy2(license_file, plugin / ("UPSTREAM-" + license_file.name))
        (plugin / "source-revision.txt").write_text(PLUGIN_REVISION + "\n")
        os.replace(plugin, target)
    return target


def install_build_skills(root, destination):
    folder = ensure_plugin_cache(root)
    links = {name: destination / f"build-macos-apps--{name}" for name in SKILLS}
    # 先检查所有冲突，再创建链接；不覆盖用户已有文件或目录。
    for name, link in links.items():
        source = folder / "skills" / name
        if link.exists() or link.is_symlink():
            if not link.is_symlink() or link.resolve() != source.resolve():
                raise RuntimeError(f"保留已有内容，安装路径冲突: {link}")
    destination.mkdir(parents=True, exist_ok=True)
    for name, link in links.items():
        if not link.is_symlink():
            link.symlink_to(folder / "skills" / name, target_is_directory=True)
    return {"status": "installed", "version": PLUGIN_VERSION,
            "revision": PLUGIN_REVISION,
            "skill_paths": {name: str(links[name] / "SKILL.md") for name in SKILLS}}


def rea_json(*args):
    output = run(["npm", "exec", "--yes", f"--package=rea-agents@{REA_VERSION}",
                  "--", "rea", *args, "--format", "json"])
    value = json.loads(output)
    if not isinstance(value, dict):
        raise RuntimeError("REA 返回了非对象 JSON；停止写入并检查已安装版本。")
    return value


def verify_rea_plan(plan, with_hopper):
    if plan.get("status") != "planned" or not isinstance(plan.get("plannedActions"), list):
        raise RuntimeError("REA 未返回有效限定安装计划。")
    allowed = {"configure_client", "install_skill"}
    if with_hopper:
        allowed.add("install_hopper")
    for action in plan["plannedActions"]:
        if action.get("kind") not in allowed:
            raise RuntimeError("REA 计划包含请求范围之外的操作；未应用。")
        if action.get("kind") == "configure_client" and action.get("id") != "configure_client:codex":
            raise RuntimeError("REA 计划尝试配置非 Codex 客户端；未应用。")


def install_rea(root, with_hopper):
    extra = ["--install-hopper"] if with_hopper else []
    plan = rea_json("setup", "--client", "codex", "--dry-run", *extra)
    verify_rea_plan(plan, with_hopper)
    write_json(root / "rea-setup-plan.json", plan)
    print(json.dumps({"rea_plan": plan["plannedActions"]}, ensure_ascii=False), file=sys.stderr)
    result = rea_json("setup", "--client", "codex", "--yes", *extra)
    write_json(root / "rea-setup-result.json", result)
    if result.get("status") != "ready":
        raise RuntimeError("REA setup 尚未就绪: " + str(result.get("remediation") or result.get("status")))
    health = rea_json("doctor", "--client", "codex", "--skill")
    write_json(root / "rea-doctor.json", health)
    if health.get("healthy") is not True:
        raise RuntimeError("REA 的限定 doctor 未通过；查看 rea-doctor.json 修复对应问题。")
    return {"status": "configured", "version": REA_VERSION,
            "registration_verified": True, "live_connection": "unknown",
            "next": "重连或重启 Codex 后调用当前会话中的真实 REA 工具。"}


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
        raise RuntimeError("安装必须在用户的 Mac 上运行；此环境不能准备该 Mac 的 MCP 或权限。")
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    report = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "build_skills": {}, "rea": {}, "errors": [], "user_actions": []}
    tasks = []
    if args.skip_build_skills:
        report["build_skills"] = {"status": "skipped", "reason": "由调用方验证后复用"}
    elif not readiness["git_ready"]:
        report["errors"].append("开发 Skills 安装需要可用的 git；请准备 Command Line Tools。")
    else:
        tasks.append(("build_skills", lambda: install_build_skills(root, skills_dir())))
    if args.skip_rea:
        report["rea"] = {"status": "skipped", "reason": "由调用方验证后复用"}
    elif not readiness["node_supported"] or not readiness["npm"] or not readiness["npx"]:
        report["errors"].append("REA 需要 Node.js 22.x >=22.19、24.x >=24.11 或稳定版 26+，以及 npm/npx。")
    else:
        tasks.append(("rea", lambda: install_rea(root, args.with_hopper)))
    # 两类依赖分别记录结果，某一项失败后仍处理不依赖它的另一项。
    for name, action in tasks:
        try:
            report[name] = action()
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            report[name] = {"status": "failed", "error": str(exc)}
            report["errors"].append(f"{name}: {exc}")
    if not readiness["swift"]:
        report["user_actions"].append("准备可用的 Swift 工具链；需要 Xcode 的工程再安装或选择完整 Xcode。")
    report["user_actions"].extend([
        "在本地客户端开启 Computer Use 的 server 和 skill；已开启时复用。",
        "按提示授予屏幕录制、辅助功能和本次目标 App 访问权限；已授予时复用。",
        "新配置尚未加载时重连或重启 Codex，随后在活动会话验证 REA 和 GUI 操作。",
    ])
    report["status"] = "partial" if report["errors"] else "dependencies_prepared"
    write_json(root / "installation.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读检查，不下载或写配置")
    mode.add_argument("--install", action="store_true", help="准备依赖，仅配置 Codex")
    parser.add_argument("--skip-rea", action="store_true")
    parser.add_argument("--skip-build-skills", action="store_true")
    parser.add_argument("--with-hopper", action="store_true", help="用户明确选择时安装 Hopper")
    args = parser.parse_args()
    if args.with_hopper and (not args.install or args.skip_rea):
        parser.error("--with-hopper 需要 --install，且不能同时跳过 REA")
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
