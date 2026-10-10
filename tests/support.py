import os
import plistlib
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

macos_only = unittest.skipUnless(sys.platform == "darwin", "需要 macOS 系统工具")


def run_script(name, *args, env=None):
    # env 中的键覆盖当前环境变量
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          text=True, capture_output=True,
                          env=None if env is None else {**os.environ, **env})


def make_app(base, bundle_id="org.example.synthetic", version="1.0", build="1", extra=None,
             name="Synthetic"):
    app = Path(base) / f"{name}.app"
    (app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    # 主程序复制系统自带的 Mach-O，otool 和 codesign 可以正常读取
    shutil.copy("/usr/bin/true", app / "Contents" / "MacOS" / name)
    info = {"CFBundleIdentifier": bundle_id, "CFBundleName": name,
            "CFBundleExecutable": name, "CFBundleShortVersionString": version,
            "CFBundleVersion": build, **(extra or {})}
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    return app


def init_project(project, app, *flags, env=None):
    return run_script("init_project.py", project, "--app-path", app, *flags, env=env)
