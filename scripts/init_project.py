#!/usr/bin/env python3
"""初始化复刻项目的证据文件，不覆盖已有记录。"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--app-path", required=True)
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve() / "replica"
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    items = {
        "feature-ledger.json": json.dumps(
            {"schema_version": 1, "app_path": args.app_path,
             "app_version": None, "macos_version": None, "features": []},
            ensure_ascii=False, indent=2) + "\n",
        "scenarios.json": json.dumps(
            {"schema_version": 1, "scenarios": []}, indent=2) + "\n",
        "progress.md": "# 复刻进度\n\n记录准备、探索、实现、验证结果及继续入口。\n",
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
    print(json.dumps({"created": created, "reused": reused}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
