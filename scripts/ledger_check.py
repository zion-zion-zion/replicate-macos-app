import argparse
import json
import re
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = 2
ENTRY_KINDS = (
    "menu", "context_menu", "toolbar", "window", "settings", "shortcut", "document_type",
    "url_scheme", "service", "applescript", "app_intent", "drag_drop", "dock_menu",
    "menu_bar_extra", "extension", "notification", "lifecycle",
)
SOURCES = ("gui", "bundle", "rea", "user")
EVIDENCE_KINDS = ("gui", "file", "bundle", "rea", "log")
INVESTIGATION = ("hypothesis", "observed", "verified", "blocked")
IMPLEMENTATION = ("pending", "implemented", "blocked")
VALIDATION = ("pending", "passed", "failed", "blocked")
SCENARIO_KINDS = ("gui", "file", "automated")
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
        self.warnings = []

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
            path = item.get("path")
            if path is None:
                continue
            if not nonempty_text(path) or not (self.root / path).is_file():
                self.errors.append(f"{owner}: 证据文件不存在 {path}")
            else:
                files += 1
        if require_file and files == 0:
            self.errors.append(f"{owner}: 需要至少一个存在的证据文件")

    def blocker(self, owner, item, statuses):
        blocked = "blocked" in statuses
        if blocked and not nonempty_text(item.get("blocker")):
            self.errors.append(f"{owner}: 状态为 blocked 时需要填写 blocker")
        if not blocked and item.get("blocker") is not None:
            self.errors.append(f"{owner}: 填写了 blocker，但没有任何状态为 blocked")

    def feature(self, item):
        owner = item.get("id", "<缺少 id>")
        if not re.fullmatch(r"F-\d{3,}", str(item.get("id"))):
            self.errors.append(f"{owner}: id 格式应为 F-001")
        if not nonempty_text(item.get("name")):
            self.errors.append(f"{owner}: 缺少 name")
        entries = item.get("entries")
        if not isinstance(entries, list) or not entries:
            self.errors.append(f"{owner}: entries 需要至少一个入口")
        else:
            for entry in entries:
                if (not isinstance(entry, dict) or entry.get("kind") not in ENTRY_KINDS
                        or not nonempty_text(entry.get("path"))):
                    self.errors.append(f"{owner}: 入口需要合法的 kind 和 path，kind 取值见 workflow.md")
        source = item.get("source")
        if not isinstance(source, list) or not source or any(value not in SOURCES for value in source):
            self.errors.append(f"{owner}: source 需要是 {'/'.join(SOURCES)} 的非空数组")
        if not text_list(item.get("preconditions")):
            self.errors.append(f"{owner}: preconditions 必须是文本数组")
        if not text_list(item.get("expected")):
            self.errors.append(f"{owner}: expected 必须是文本数组")
        investigation = item.get("investigation_status")
        implementation = item.get("implementation_status")
        validation = item.get("validation_status")
        for field, value, allowed in (("investigation_status", investigation, INVESTIGATION),
                                      ("implementation_status", implementation, IMPLEMENTATION),
                                      ("validation_status", validation, VALIDATION)):
            if value not in allowed:
                self.errors.append(f"{owner}: {field} 取值应为 {'/'.join(allowed)}")
        self.evidence(owner, item.get("evidence"))
        if investigation in ("observed", "verified") and not item.get("evidence"):
            self.errors.append(f"{owner}: 调查状态为 {investigation} 时需要证据")
        if investigation in ("observed", "verified") and not item.get("expected"):
            self.errors.append(f"{owner}: 调查状态为 {investigation} 时需要写明 expected")
        if validation == "passed" and implementation != "implemented":
            self.errors.append(f"{owner}: 验证通过的功能必须已实现")
        if implementation == "implemented" and investigation == "hypothesis":
            self.warnings.append(f"{owner}: 实现所依据的行为仍是 hypothesis，尚未实际观察")
        self.blocker(owner, item, (investigation, implementation, validation))

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
        screenshots = status == "passed" and kind == "gui"
        self.side(f"{owner}.original", item.get("original"), screenshots)
        self.side(f"{owner}.replica", item.get("replica"), screenshots)
        if status == "passed":
            if item.get("differences"):
                self.errors.append(f"{owner}: 通过的场景不能有未解决的 differences")
            for side in ("original", "replica"):
                if not nonempty_text((item.get(side) or {}).get("result")):
                    self.errors.append(f"{owner}: 通过的场景需要记录 {side}.result")
        if status == "failed" and not item.get("differences"):
            self.errors.append(f"{owner}: 失败的场景需要写明 differences")
        self.blocker(owner, item, (status,))


def load(path, checker):
    if not path.is_file():
        checker.errors.append(f"缺少 {path}")
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        checker.errors.append(f"{path.name}: schema_version 应为 {SCHEMA_VERSION}")
    return data


def check(root, final):
    checker = Checker(root)
    ledger = load(root / "feature-ledger.json", checker)
    scenario_file = load(root / "scenarios.json", checker)
    if ledger is None or scenario_file is None:
        return checker, {}
    collections = {}
    for name, values in (("features", ledger.get("features")),
                         ("scenarios", scenario_file.get("scenarios"))):
        if not isinstance(values, list):
            checker.errors.append(f"{name} 必须是数组")
            values = []
        if not all(isinstance(item, dict) for item in values):
            checker.errors.append(f"{name}: 每一项必须是对象")
        collections[name] = [item for item in values if isinstance(item, dict)]
        ids = [item.get("id") for item in collections[name]]
        for duplicate in sorted(key for key, count in Counter(ids).items() if count > 1):
            checker.errors.append(f"{name}: ID 重复 {duplicate}")
    features, scenarios = collections["features"], collections["scenarios"]
    absent = ledger.get("absent_entry_kinds", {})
    feature_ids = {item.get("id") for item in features}
    for item in features:
        checker.feature(item)
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
        if item.get("validation_status") == "passed":
            if "passed" not in statuses:
                checker.errors.append(f"{owner}: 验证通过需要至少一个通过的关联场景")
            if "failed" in statuses:
                checker.errors.append(f"{owner}: 仍有失败的关联场景，不能标为验证通过")

    if not isinstance(absent, dict):
        checker.errors.append("absent_entry_kinds 必须是对象")
        absent = {}
    for kind, note in absent.items():
        if kind not in ENTRY_KINDS or not nonempty_text(note):
            checker.errors.append(f"absent_entry_kinds.{kind}: 需要合法的入口类别和不存在的依据")
    covered = sorted({entry.get("kind") for item in features
                      for entry in (item.get("entries") if isinstance(item.get("entries"), list) else [])
                      if isinstance(entry, dict) and entry.get("kind") in ENTRY_KINDS})
    for kind in covered:
        if kind in absent:
            checker.errors.append(f"absent_entry_kinds.{kind}: 已有功能使用该入口类别，不能同时标为不存在")
    unchecked = [kind for kind in ENTRY_KINDS if kind not in covered and kind not in absent]

    if final:
        for item in features:
            statuses = (item.get("investigation_status"), item.get("implementation_status"),
                        item.get("validation_status"))
            if "blocked" in statuses:
                continue
            if item.get("implementation_status") != "implemented" or item.get("validation_status") != "passed":
                checker.errors.append(f"{item.get('id')}: 交付前需要已实现并验证通过，或标为 blocked")
            if not linked.get(item.get("id")):
                checker.errors.append(f"{item.get('id')}: 交付前需要至少一个关联场景")
        for item in scenarios:
            if item.get("status") not in ("passed", "blocked"):
                checker.errors.append(f"{item.get('id')}: 交付前场景需要通过或标为 blocked")
        for kind in unchecked:
            checker.errors.append(f"入口类别 {kind}: 交付前需要有对应功能，或在 absent_entry_kinds 写明不存在的依据")

    summary = {
        "features": {
            "total": len(features),
            **{field: dict(Counter(item.get(field) for item in features))
               for field in ("investigation_status", "implementation_status", "validation_status")},
        },
        "scenarios": {"total": len(scenarios),
                      "status": dict(Counter(item.get("status") for item in scenarios))},
        "entry_kinds": {"covered": covered, "absent": sorted(absent), "unchecked": unchecked},
    }
    return checker, summary


def main():
    parser = argparse.ArgumentParser(description="校验复刻项目的功能清单、场景与证据。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--final", action="store_true", help="交付前检查：所有功能和场景都需要完成或标为 blocked")
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve() / "replica"
    checker, summary = check(root, args.final)
    print(json.dumps({"final": args.final, **summary, "errors": checker.errors,
                      "warnings": checker.warnings}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if checker.errors else 0)


if __name__ == "__main__":
    main()
