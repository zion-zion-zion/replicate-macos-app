import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 4
AX_SOURCE = Path(__file__).resolve().parent / "ax.swift"
PROGRESS = """# 复刻进度

## 目标

- 原版：{name} {version}（{build}），{bundle_id}
- 路径：{path}
- macOS：{macos_version}（{macos_build}）

## 当前阶段

开始

## 下一步

- 在当前会话确认 Computer Use、REA、Build macOS Apps 和 `bin/ax` 可用。

## 构建与启动

- 命令：建立 `script/build_and_run.sh` 后填写

## 等待用户处理

- 无

## 记录

"""


def app_identity(app):
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    return {"path": str(app), "bundle_id": info.get("CFBundleIdentifier"),
            "name": info.get("CFBundleDisplayName") or info.get("CFBundleName") or app.stem,
            "version": info.get("CFBundleShortVersionString"), "build": info.get("CFBundleVersion")}


def macos_identity():
    def sw_vers(flag):
        return subprocess.run(["sw_vers", flag], text=True, capture_output=True,
                              check=True).stdout.strip()
    return {"version": sw_vers("-productVersion"), "build": sw_vers("-buildVersion")}


def build_ax(root):
    # 解释执行 ax.swift 每次要十几秒，编译一次供清点和场景脚本反复调用。
    binary = root / "bin" / "ax"
    if binary.is_file() and binary.stat().st_mtime >= AX_SOURCE.stat().st_mtime:
        return {"path": str(binary), "status": "reused"}
    binary.parent.mkdir(exist_ok=True)
    subprocess.run(["xcrun", "swiftc", "-O", str(AX_SOURCE), "-o", str(binary)],
                   stdout=sys.stderr, check=True)
    return {"path": str(binary), "status": "built"}


def main():
    parser = argparse.ArgumentParser(description="初始化复刻项目的记录文件，不覆盖已有记录。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--app-path", required=True, type=Path)
    args = parser.parse_args()
    app = args.app_path.expanduser().resolve()
    if not (app / "Contents" / "Info.plist").is_file():
        parser.error(f"不是有效的 App bundle: {app}")
    identity, macos = app_identity(app), macos_identity()
    root = args.project_dir.expanduser().resolve() / "replica"
    for name in ("evidence", "scenarios"):
        (root / name).mkdir(parents=True, exist_ok=True)
    items = {
        ".gitignore": "bin/\n",
        "feature-ledger.json": json.dumps(
            {"schema_version": SCHEMA_VERSION, "app": identity, "macos": macos,
             "inventory": [], "absent_entry_kinds": {}, "features": []},
            ensure_ascii=False, indent=2) + "\n",
        "scenarios.json": json.dumps(
            {"schema_version": SCHEMA_VERSION, "scenarios": []}, indent=2) + "\n",
        "progress.md": PROGRESS.format(**identity, macos_version=macos["version"],
                                       macos_build=macos["build"]),
    }
    created, reused = [], []
    for name, value in items.items():
        target = root / name
        try:
            with target.open("x", encoding="utf-8") as handle:
                handle.write(value)
            created.append(str(target))
        except FileExistsError:
            reused.append(str(target))
    print(json.dumps({"created": created, "reused": reused, "ax": build_ax(root),
                      "app": identity, "macos": macos}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
