import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = 4
ENTRY_KINDS = (
    "menu", "context_menu", "toolbar", "window", "settings", "shortcut", "document_type",
    "url_scheme", "service", "applescript", "app_intent", "drag_drop", "dock_menu",
    "menu_bar_extra", "extension", "notification", "lifecycle",
)
EVIDENCE_KINDS = ("ax", "state", "gui", "file", "log", "bundle", "rea", "doc", "user",
                  "static", "runtime")
PATH_EVIDENCE = ("ax", "state", "bundle", "static", "runtime")
RUNTIME_EVIDENCE = ("ax", "state", "gui", "file", "log", "user", "runtime")
FEATURE_STATUS = ("hypothesis", "observed", "implemented", "passed", "blocked")
BLOCKER_KINDS = ("account", "server", "hardware", "license", "entitlement", "user")
SCENARIO_KINDS = ("script", "gui", "automated")
SCENARIO_STATUS = ("pending", "passed", "failed", "blocked")


def nonempty_text(value):
    return isinstance(value, str) and value.strip() != ""


def text_list(value, allow_empty=True):
    return (isinstance(value, list) and all(nonempty_text(item) for item in value)
            and (allow_empty or len(value) > 0))


class Checker:
    def __init__(self, root):
        self.root = root
        self.errors = []

    def evidence(self, owner, items, require_file=False):
        if not isinstance(items, list):
            self.errors.append(f"{owner}: evidence 必须是数组")
            return
        files = 0
        for item in items:
            if (not isinstance(item, dict) or item.get("kind") not in EVIDENCE_KINDS
                    or not nonempty_text(item.get("note"))):
                self.errors.append(f"{owner}: 每条证据需要 kind（{'/'.join(EVIDENCE_KINDS)}）和 note")
                continue
            path, kind = item.get("path"), item.get("kind")
            if kind in PATH_EVIDENCE and path is None:
                self.errors.append(f"{owner}: {kind} 证据需要 path 指向实际输出")
            if kind == "doc" and path is None and not re.match(r"https?://", str(item.get("url", ""))):
                self.errors.append(f"{owner}: doc 证据需要 url 或 path")
            if path is None:
                continue
            if not nonempty_text(path) or not (self.root / path).is_file():
                self.errors.append(f"{owner}: 证据文件不存在 {path}")
            else:
                files += 1
        if require_file and files == 0:
            self.errors.append(f"{owner}: 需要至少一个存在的证据文件")

    def blocker(self, owner, item, blocked):
        value = item.get("blocker")
        if blocked:
            if (not isinstance(value, dict) or value.get("kind") not in BLOCKER_KINDS
                    or not nonempty_text(value.get("detail"))):
                self.errors.append(f"{owner}: blocked 时 blocker 需要 kind（{'/'.join(BLOCKER_KINDS)}）和 detail")
        elif value is not None:
            self.errors.append(f"{owner}: 填写了 blocker，但状态不是 blocked")

    def inventory(self, items, feature_ids):
        for index, item in enumerate(items):
            owner = f"inventory[{index}]"
            if item.get("kind") not in ENTRY_KINDS or not nonempty_text(item.get("path")):
                self.errors.append(f"{owner}: 需要合法的 kind 和 path，kind 取值见 ledger.md")
            if ("feature" in item) == ("skip" in item):
                self.errors.append(f"{owner}: feature 与 skip 需要二选一")
            elif "feature" in item and (not isinstance(item["feature"], str)
                                        or item["feature"] not in feature_ids):
                self.errors.append(f"{owner}: 指向不存在的功能 {item['feature']}")
            elif "skip" in item and not nonempty_text(item["skip"]):
                self.errors.append(f"{owner}: skip 需要写明原因")
        keys = Counter((str(item.get("kind")), str(item.get("path"))) for item in items)
        for (kind, path), count in sorted(keys.items()):
            if count > 1:
                self.errors.append(f"inventory: 入口重复 {kind} {path}")

    def feature(self, item, entry_count):
        owner = item.get("id", "<缺少 id>")
        if not re.fullmatch(r"F-\d{3,}", str(item.get("id"))):
            self.errors.append(f"{owner}: id 格式应为 F-001")
        if not nonempty_text(item.get("name")):
            self.errors.append(f"{owner}: 缺少 name")
        if not text_list(item.get("preconditions")):
            self.errors.append(f"{owner}: preconditions 必须是文本数组")
        if not text_list(item.get("expected")):
            self.errors.append(f"{owner}: expected 必须是文本数组")
        status = item.get("status")
        if status not in FEATURE_STATUS:
            self.errors.append(f"{owner}: status 取值应为 {'/'.join(FEATURE_STATUS)}")
        self.evidence(owner, item.get("evidence"))
        if status in ("observed", "implemented", "passed"):
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if not any(isinstance(entry, dict) and entry.get("kind") in RUNTIME_EVIDENCE
                       for entry in evidence):
                self.errors.append(f"{owner}: 状态为 {status} 时需要在运行的原版上取得的证据"
                                   f"（{'/'.join(RUNTIME_EVIDENCE)}）")
            if not item.get("expected"):
                self.errors.append(f"{owner}: 状态为 {status} 时需要写明 expected")
        if entry_count == 0:
            self.errors.append(f"{owner}: inventory 中没有指向该功能的入口")
        self.blocker(owner, item, status == "blocked")

    def side(self, owner, value, require_file):
        if not isinstance(value, dict):
            self.errors.append(f"{owner}: 需要包含 result 和 evidence 的对象")
            return
        if value.get("result") is not None and not nonempty_text(value.get("result")):
            self.errors.append(f"{owner}: result 应为文本或 null")
        self.evidence(owner, value.get("evidence"), require_file)

    def scenario(self, item, feature_ids):
        owner = item.get("id", "<缺少 id>")
        if not re.fullmatch(r"S-\d{3,}", str(item.get("id"))):
            self.errors.append(f"{owner}: id 格式应为 S-001")
        features = item.get("features")
        if not text_list(features, allow_empty=False):
            self.errors.append(f"{owner}: features 需要至少一个功能 ID")
        else:
            for feature_id in features:
                if feature_id not in feature_ids:
                    self.errors.append(f"{owner}: 关联了不存在的功能 {feature_id}")
        kind, status = item.get("kind"), item.get("status")
        if kind not in SCENARIO_KINDS:
            self.errors.append(f"{owner}: kind 取值应为 {'/'.join(SCENARIO_KINDS)}")
        if status not in SCENARIO_STATUS:
            self.errors.append(f"{owner}: status 取值应为 {'/'.join(SCENARIO_STATUS)}")
        if not text_list(item.get("steps"), allow_empty=False):
            self.errors.append(f"{owner}: steps 需要至少一步")
        if not text_list(item.get("checks"), allow_empty=False):
            self.errors.append(f"{owner}: checks 需要至少一个观测点")
        if not text_list(item.get("fixtures")):
            self.errors.append(f"{owner}: fixtures 必须是文本数组")
        if not text_list(item.get("differences")):
            self.errors.append(f"{owner}: differences 必须是文本数组")
        script = item.get("script")
        if kind == "script" or script is not None:
            target = self.root / str(script)
            if not nonempty_text(script) or not target.is_file():
                self.errors.append(f"{owner}: script 场景需要存在的脚本文件 {script}")
            elif not os.access(target, os.X_OK):
                self.errors.append(f"{owner}: 脚本不可执行 {script}")
        outputs = status == "passed" and kind in ("gui", "script")
        self.side(f"{owner}.original", item.get("original"), outputs)
        self.side(f"{owner}.replica", item.get("replica"), outputs)
        if status == "passed":
            if item.get("differences"):
                self.errors.append(f"{owner}: 通过的场景不能有未解决的 differences")
            for side in ("original", "replica"):
                if not nonempty_text((item.get(side) or {}).get("result")):
                    self.errors.append(f"{owner}: 通过的场景需要记录 {side}.result")
        if status == "failed" and not item.get("differences"):
            self.errors.append(f"{owner}: 失败的场景需要写明 differences")
        self.blocker(owner, item, status == "blocked")


def load(path, checker):
    if not path.is_file():
        checker.errors.append(f"缺少 {path}")
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        checker.errors.append(f"{path.name}: schema_version 应为 {SCHEMA_VERSION}")
    return data


def objects(checker, name, values):
    if not isinstance(values, list):
        checker.errors.append(f"{name} 必须是数组")
        return []
    if not all(isinstance(item, dict) for item in values):
        checker.errors.append(f"{name}: 每一项必须是对象")
    return [item for item in values if isinstance(item, dict)]


def check(root, final):
    checker = Checker(root)
    ledger = load(root / "feature-ledger.json", checker)
    scenario_file = load(root / "scenarios.json", checker)
    if ledger is None or scenario_file is None:
        return checker, {}
    inventory = objects(checker, "inventory", ledger.get("inventory"))
    features = objects(checker, "features", ledger.get("features"))
    scenarios = objects(checker, "scenarios", scenario_file.get("scenarios"))
    for name, values in (("features", features), ("scenarios", scenarios)):
        ids = Counter(item.get("id") for item in values)
        for duplicate in sorted(key for key, count in ids.items() if count > 1):
            checker.errors.append(f"{name}: ID 重复 {duplicate}")

    feature_ids = {item.get("id") for item in features}
    checker.inventory(inventory, feature_ids)
    entry_counts = Counter(item["feature"] for item in inventory
                           if isinstance(item.get("feature"), str))
    for item in features:
        checker.feature(item, entry_counts[item.get("id")])
    for item in scenarios:
        checker.scenario(item, feature_ids)

    linked = {feature_id: [] for feature_id in feature_ids}
    for item in scenarios:
        targets = item.get("features") if isinstance(item.get("features"), list) else []
        for feature_id in targets:
            if feature_id in linked:
                linked[feature_id].append(item.get("status"))
    for item in features:
        owner, statuses = item.get("id"), linked.get(item.get("id"), [])
        if item.get("status") == "passed":
            if "passed" not in statuses:
                checker.errors.append(f"{owner}: passed 需要至少一个通过的关联场景")
            if "failed" in statuses:
                checker.errors.append(f"{owner}: 仍有失败的关联场景，不能标为 passed")

    absent = ledger.get("absent_entry_kinds", {})
    if not isinstance(absent, dict):
        checker.errors.append("absent_entry_kinds 必须是对象")
        absent = {}
    for kind, note in absent.items():
        if kind not in ENTRY_KINDS or not nonempty_text(note):
            checker.errors.append(f"absent_entry_kinds.{kind}: 需要合法的入口类别和不存在的依据")
    # 只有 skip 项的类别不算覆盖，需要在 absent_entry_kinds 写明依据。
    covered = sorted({item.get("kind") for item in inventory
                      if "feature" in item and item.get("kind") in ENTRY_KINDS})
    for kind in covered:
        if kind in absent:
            checker.errors.append(f"absent_entry_kinds.{kind}: 已有入口指向功能，不能同时标为不存在")
    unchecked = [kind for kind in ENTRY_KINDS if kind not in covered and kind not in absent]

    if final:
        if not features:
            checker.errors.append("交付前需要非空的功能清单，不能用空记录通过验收")
        if not scenarios:
            checker.errors.append("交付前需要非空的验证场景，不能用空记录通过验收")
        for item in features:
            if item.get("status") not in ("passed", "blocked"):
                checker.errors.append(f"{item.get('id')}: 交付前需要 passed 或 blocked")
        for item in scenarios:
            if item.get("status") not in ("passed", "blocked"):
                checker.errors.append(f"{item.get('id')}: 交付前场景需要 passed 或 blocked")
        for kind in unchecked:
            checker.errors.append(f"入口类别 {kind}: 交付前需要有指向功能的入口，或在 absent_entry_kinds 写明不存在的依据")

    summary = {
        "inventory": {"total": len(inventory),
                      "mapped": sum(1 for item in inventory if "feature" in item),
                      "skipped": sum(1 for item in inventory if "skip" in item)},
        "features": {"total": len(features),
                     "status": dict(Counter(item.get("status") for item in features))},
        "scenarios": {"total": len(scenarios),
                      "status": dict(Counter(item.get("status") for item in scenarios))},
        "entry_kinds": {"covered": covered, "absent": sorted(absent), "unchecked": unchecked},
    }
    return checker, summary


def main():
    parser = argparse.ArgumentParser(description="校验复刻项目的入口清单、功能、场景与证据。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--final", action="store_true", help="交付前检查：所有功能和场景都需要 passed 或 blocked")
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve() / "replica"
    checker, summary = check(root, args.final)
    print(json.dumps({"final": args.final, **summary, "errors": checker.errors},
                     ensure_ascii=False, indent=2))
    raise SystemExit(1 if checker.errors else 0)


if __name__ == "__main__":
    main()