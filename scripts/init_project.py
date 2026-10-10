import argparse
import datetime
import json
import plistlib
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 4
AX_SOURCE = Path(__file__).resolve().parent / "ax.swift"
PROGRESS = """# 复刻进度

## 目标

- 原版 A：{name} {version}（{build}），{bundle_id}
- 路径：{path}
- macOS：{macos_version}（{macos_build}）
- 复刻版 B：{replica_name}，拥有完整源码、可独立运行

## 当前阶段

开始

## 下一步

- 读取已有记录，按目标选择调查方法并验证所需工具。
- 建立全功能清单；在 reference-manifest.json 记录 B 的构建与验收。

## 构建与启动

- 命令：建立可重复构建与启动入口后填写

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
    # 编译一次供清点和场景脚本重复调用；初始化调用方负责处理工具不可用。
    binary = root / "bin" / "ax"
    if binary.is_file() and binary.stat().st_mtime >= AX_SOURCE.stat().st_mtime:
        return {"path": str(binary), "status": "reused"}
    binary.parent.mkdir(exist_ok=True)
    subprocess.run(["xcrun", "swiftc", "-O", str(AX_SOURCE), "-o", str(binary)],
                   stdout=sys.stderr, check=True)
    return {"path": str(binary), "status": "built"}


def reference_manifest(identity, replica_name):
    return {
        "schema_version": 1,
        "role": "reference_app_construction",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "original": identity,
        "reference": {
            "name": replica_name, "bundle_id": None, "source_dir": None,
            "source_revision": None, "artifact_path": None,
            "build_command": None, "launch_command": None, "reset_command": None,
            "fixtures": [], "dependencies": [],
        },
        "construction": {"methods": [], "components": []},
        "verification": {
            **{name: {"status": "pending", "evidence": [], "notes": []}
               for name in ("fidelity", "independence", "reset")},
            "known_differences": [],
        },
        "freeze": {
            "reference_version": None, "frozen_at": None,
            "source_revision": None, "artifact_sha256": None,
        },
    }


def initialize(project_dir, app, skip_ax=False):
    app = Path(app).expanduser().resolve()
    if not (app / "Contents" / "Info.plist").is_file():
        raise ValueError(f"不是有效的 App bundle: {app}")
    identity = app_identity(app)
    replica_name = f"{identity['name']}-replicate"
    root = Path(project_dir).expanduser().resolve() / "replica"
    ledger_path = root / "feature-ledger.json"
    if ledger_path.is_file():
        existing = json.loads(ledger_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or not isinstance(existing.get("app"), dict):
            raise ValueError("已有功能清单缺少合法的 app 信息；请先检查记录，未覆盖。")
        for key in ("path", "bundle_id", "version", "build"):
            old = existing["app"].get(key)
            if old is not None and old != identity.get(key):
                raise ValueError(f"已有项目的原版 {key} 不一致；请使用独立项目或明确迁移原版版本。")
    macos = macos_identity()
    for name in ("evidence", "scenarios"):
        (root / name).mkdir(parents=True, exist_ok=True)
    manifest = reference_manifest(identity, replica_name)
    items = {
        ".gitignore": "bin/\n",
        "feature-ledger.json": json.dumps(
            {"schema_version": SCHEMA_VERSION, "app": identity, "macos": macos,
             "inventory": [], "absent_entry_kinds": {}, "features": []},
            ensure_ascii=False, indent=2) + "\n",
        "scenarios.json": json.dumps(
            {"schema_version": SCHEMA_VERSION, "scenarios": []}, indent=2) + "\n",
        "reference-manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        "progress.md": PROGRESS.format(**identity, replica_name=replica_name,
                                       macos_version=macos["version"],
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
    if skip_ax:
        ax = {"status": "skipped", "reason": "--skip-ax"}
    else:
        try:
            ax = build_ax(root)
        except (OSError, subprocess.SubprocessError) as exc:
            ax = {"status": "unavailable", "error": str(exc),
                  "note": "项目记录已创建；可修复 AX 工具或使用其他方法继续。"}
    return {"created": created, "reused": reused, "ax": ax,
            "app": identity, "macos": macos}


def main(argv=None):
    parser = argparse.ArgumentParser(description="初始化复刻项目记录，已有记录保持不变。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--app-path", required=True, type=Path)
    parser.add_argument("--skip-ax", action="store_true", help="跳过可选 AX 工具的编译")
    args = parser.parse_args(argv)
    try:
        result = initialize(args.project_dir, args.app_path, skip_ax=args.skip_ax)
    except (OSError, ValueError, plistlib.InvalidFileException, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()