import argparse
import hashlib
import json
import os
import plistlib
import re
from collections import Counter
from pathlib import Path

from scenario_run import tree_sha256

SCHEMA_VERSION = 6
MANIFEST_SCHEMA_VERSION = 2
ENTRY_KINDS = (
    "menu", "context_menu", "toolbar", "window", "settings", "shortcut", "document_type",
    "url_scheme", "service", "applescript", "app_intent", "drag_drop", "dock_menu",
    "menu_bar_extra", "extension", "notification", "lifecycle",
)
EVIDENCE_KINDS = ("ax", "state", "run", "gui", "file", "log", "bundle", "rea", "doc", "user",
                  "static", "runtime")
PATH_EVIDENCE = ("ax", "state", "run", "bundle", "static", "runtime")
RUNTIME_EVIDENCE = ("ax", "state", "run", "gui", "file", "log", "user", "runtime")
FEATURE_STATUS = ("hypothesis", "observed", "implemented", "passed", "blocked")
BLOCKER_KINDS = ("account", "server", "hardware", "license", "entitlement", "user")
SCENARIO_KINDS = ("script", "gui", "automated")
SCENARIO_STATUS = ("pending", "passed", "failed", "blocked")
VERIFICATION_STATUS = ("pending", "passed", "failed", "blocked")
CLUE_SOURCES = ("nib", "framework", "xpc", "extension", "helper", "plugin", "library",
                "app_intent", "database", "data_model")

AX_HEADER = b"# ax-dump "
AX_PATH = re.compile(r"(MenuBar|Window|Menu|Sheet)(\[|#| >|$)")
AX_INTERACTIVE = {"MenuItem", "Button", "CheckBox", "RadioButton", "PopUpButton", "MenuButton",
                  "ComboBox", "Slider", "Incrementor", "TextField", "TextArea", "ColorWell",
                  "DateField", "Link", "DisclosureTriangle"}
# 这些容器里的元素随数据生成（行、单元格、列头），由所在控件对应的功能覆盖。
AX_DATA_CONTAINERS = {"Table", "Outline", "List", "Browser", "Grid", "Row", "Cell", "Column"}
AX_FRAMEWORK_SUBROLES = {"AXCloseButton", "AXMinimizeButton", "AXZoomButton", "AXFullScreenButton"}
UNCOVERED_SAMPLE = 20
WILDCARD = "[*]"
COMPARE_KINDS = (("different", "两侧内容不同"), ("only_original", "只在 A 一侧出现"),
                 ("only_replica", "只在 B 一侧出现"))


def nonempty_text(value):
    return isinstance(value, str) and value.strip() != ""


def text_list(value, allow_empty=True):
    return (isinstance(value, list) and all(nonempty_text(item) for item in value)
            and (allow_empty or len(value) > 0))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_ax_path(path):
    # 与 ax.swift 的 splitPath 一致：标签内的 "]" 和 "\" 已转义，" > " 只在标签外分段。
    parts, current, in_label, escaped, index = [], [], False, False, 0
    while index < len(path):
        char = path[index]
        if escaped:
            escaped = False
        elif in_label and char == "\\":
            escaped = True
        elif char in "[]":
            in_label = char == "["
        elif not in_label and path.startswith(" > ", index):
            parts.append("".join(current))
            current = []
            index += 3
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def ax_role(segment):
    return re.match(r"[^\[#]*", segment).group(0)


def segment_matches(pattern, segment):
    # Role[*] 匹配同一角色下任意带标签的段，包括带 #序号 的重复段。
    if not pattern.endswith(WILDCARD):
        return pattern == segment
    role = pattern[:-len(WILDCARD)]
    return ax_role(segment) == role and segment[len(role):].startswith("[")


def path_matches(pattern, path, prefix=False):
    # prefix 为 True 时 pattern 只需匹配 path 开头的若干段，skip 入口据此覆盖子元素。
    wanted, actual = split_ax_path(pattern), split_ax_path(path)
    if len(actual) < len(wanted) or (not prefix and len(actual) != len(wanted)):
        return False
    return all(segment_matches(item, segment) for item, segment in zip(wanted, actual))


def ax_path_known(path, ax_paths):
    return path in ax_paths or (WILDCARD in path and any(path_matches(path, known) for known in ax_paths))


def ax_header(path):
    with path.open("rb") as handle:
        first = handle.readline(1 << 16)
    if not first.startswith(AX_HEADER):
        return None
    return json.loads(first[len(AX_HEADER):])


def ax_elements(path):
    # 返回 (所有路径, 可操作元素路径)
    paths, interactive = set(), set()
    lines = path.read_text(encoding="utf-8").splitlines()[1:]
    for line in lines:
        fields = line.split("\t")
        element = fields[0]
        paths.add(element)
        segments = split_ax_path(element)
        role = ax_role(segments[-1])
        subrole = next((field[len("subrole="):] for field in fields[1:]
                        if field.startswith("subrole=")), None)
        if (role not in AX_INTERACTIVE or subrole in AX_FRAMEWORK_SUBROLES
                or (role == "MenuItem" and "[" not in segments[-1])
                or element.startswith("MenuBar > MenuBarItem[Apple]")
                or any(ax_role(segment) in AX_DATA_CONTAINERS for segment in segments[:-1])):
            continue
        interactive.add(element)
    return paths, interactive


def draft_kind(path):
    segments = split_ax_path(path)
    roles = [ax_role(segment) for segment in segments]
    if roles[0] == "MenuBar":
        return "menu"
    if roles[0] == "Menu":
        return "context_menu"
    if "Toolbar" in roles:
        return "toolbar"
    return "window"


def bundle_clues(bundle):
    entries, resources, stack = (bundle.get(key, {}) for key in ("entries", "resources", "stack"))
    clues = [("nib", name) for name in resources.get("nibs", [])]
    clues += [("framework", name) for name in stack.get("embedded_frameworks", [])]
    clues += [("xpc", item["name"]) for item in entries.get("xpc_services", [])]
    clues += [("extension", item["name"]) for item in entries.get("extensions", [])]
    clues += [("helper", name) for name in entries.get("helpers", [])]
    clues += [("plugin", name) for name in entries.get("other_plugins", [])]
    clues += [("library", f"{folder}/{name}")
              for folder, names in entries.get("library", {}).items() for name in names]
    clues += [("app_intent", item["id"]) for item in entries.get("app_intents", [])]
    clues += [("database", name) for name in resources.get("sqlite_databases", {})]
    clues += [("data_model", name) for name in resources.get("core_data_models", [])]
    return list(dict.fromkeys(clues))


class Checker:
    def __init__(self, root, original_id=None, replica_id=None):
        self.root = root
        self.original_id = original_id
        self.replica_id = replica_id
        # 交付前检查时为 reference.artifact_path 的内容哈希，B 一侧的 run 需要与它一致。
        self.replica_tree = None
        self.errors = []

    def origin(self, owner, item, side, scenario=None):
        # side 为 original 或 replica；能从文件内容确定来源的证据，核对它属于对应的 App。
        kind, path = item["kind"], self.root / item["path"]
        if kind == "ax":
            header = ax_header(path)
            if header is None:
                self.errors.append(f"{owner}: ax 证据需要 ax dump 的逐行输出（第一行以 # ax-dump 开头）{item['path']}")
                return
            bundle_id = header.get("bundle_id")
        elif kind == "state":
            data = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else None
            app = data.get("app") if isinstance(data, dict) else None
            bundle_id = app.get("bundle_id") if isinstance(app, dict) else app
            if not nonempty_text(bundle_id):
                self.errors.append(f"{owner}: state 证据需要 state_diff.py 输出的快照或差分 JSON {item['path']}")
                return
        elif kind == "run":
            run = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(run, dict) or not {"scenario", "side", "bundle_id", "exit_code",
                                                 "script", "script_sha256"} <= run.keys():
                self.errors.append(f"{owner}: run 证据需要 scenario_run.py 生成的 run.json {item['path']}")
                return
            if run["side"] != side:
                self.errors.append(f"{owner}: run 证据来自 {run['side']} 一侧，这里需要 {side} {item['path']}")
            if scenario is not None and run["scenario"] != scenario:
                self.errors.append(f"{owner}: run 证据属于场景 {run['scenario']} {item['path']}")
            bundle_id = run["bundle_id"]
        else:
            return
        if side == "original" and self.original_id and bundle_id != self.original_id:
            self.errors.append(f"{owner}: 证据来自 {bundle_id}，这里需要原版 A（{self.original_id}）的结果 {item['path']}")
        if side == "replica":
            if bundle_id == self.original_id:
                self.errors.append(f"{owner}: 证据来自原版 A，这里需要复刻版 B 的结果 {item['path']}")
            elif self.replica_id and bundle_id != self.replica_id:
                self.errors.append(f"{owner}: 证据来自 {bundle_id}，复刻版 B 的 bundle identifier 是 {self.replica_id} {item['path']}")

    def evidence(self, owner, items, require_file=False, side="original", scenario=None):
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
                self.origin(owner, item, side, scenario)
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

    def mapping(self, owner, item, feature_ids):
        if ("feature" in item) == ("skip" in item):
            self.errors.append(f"{owner}: feature 与 skip 需要二选一")
        elif "feature" in item and (not isinstance(item["feature"], str)
                                    or item["feature"] not in feature_ids):
            self.errors.append(f"{owner}: 指向不存在的功能 {item['feature']}")
        elif "skip" in item and not nonempty_text(item["skip"]):
            self.errors.append(f"{owner}: skip 需要写明原因")

    def inventory(self, items, feature_ids, ax_paths):
        for index, item in enumerate(items):
            owner = f"inventory[{index}]"
            if item.get("kind") not in ENTRY_KINDS or not nonempty_text(item.get("path")):
                self.errors.append(f"{owner}: 需要合法的 kind 和 path，kind 取值见 ledger.md")
                continue
            self.mapping(owner, item, feature_ids)
            path = item["path"]
            if ax_paths and AX_PATH.match(path) and not ax_path_known(path, ax_paths):
                self.errors.append(f"{owner}: AX 路径不在原版 A 的任何 AX 导出中 {path}")
        keys = Counter((str(item.get("kind")), str(item.get("path"))) for item in items)
        for (kind, path), count in sorted(keys.items()):
            if count > 1:
                self.errors.append(f"inventory: 入口重复 {kind} {path}")

    def clues(self, items, feature_ids, required):
        for index, item in enumerate(items):
            owner = f"clues[{index}]"
            if item.get("source") not in CLUE_SOURCES or not nonempty_text(item.get("name")):
                self.errors.append(f"{owner}: 需要合法的 source（{'/'.join(CLUE_SOURCES)}）和 name")
                continue
            self.mapping(owner, item, feature_ids)
            if required is not None and (item["source"], item["name"]) not in required:
                self.errors.append(f"{owner}: bundle.json 中没有 {item['source']} {item['name']}")
        keys = Counter((str(item.get("source")), str(item.get("name"))) for item in items)
        for (source, name), count in sorted(keys.items()):
            if count > 1:
                self.errors.append(f"clues: 线索重复 {source} {name}")

    def states(self, items, app, final, ax_unavailable):
        for index, item in enumerate(items):
            owner = item.get("id", f"states[{index}]")
            if not re.fullmatch(r"ST-\d{3,}", str(item.get("id"))):
                self.errors.append(f"{owner}: id 格式应为 ST-001")
            if not nonempty_text(item.get("name")) or not nonempty_text(item.get("reach")):
                self.errors.append(f"{owner}: 状态需要 name 和 reach（到达方式）")
            dumps = item.get("dumps")
            if not text_list(dumps):
                self.errors.append(f"{owner}: dumps 必须是 AX 导出的路径数组")
                continue
            for path in dumps:
                target = self.root / path
                header = ax_header(target) if target.is_file() else None
                if header is None:
                    self.errors.append(f"{owner}: dumps 需要 ax dump 的逐行输出 {path}")
                elif (header.get("bundle_id"), header.get("version"), header.get("build")) != \
                        (app.get("bundle_id"), app.get("version"), app.get("build")):
                    self.errors.append(f"{owner}: {path} 不是功能清单记录的原版 A 的 AX 导出")
            if final and ax_unavailable is None and not dumps:
                self.errors.append(f"{owner}: 交付前每个状态需要至少一份 A 的 AX 导出")

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

    def side(self, owner, value, require_file, side, scenario):
        if not isinstance(value, dict):
            self.errors.append(f"{owner}: 需要包含 result 和 evidence 的对象")
            return
        if value.get("result") is not None and not nonempty_text(value.get("result")):
            self.errors.append(f"{owner}: result 应为文本或 null")
        self.evidence(owner, value.get("evidence"), require_file, side, scenario)

    def runs(self, owner, value, side, script_sha):
        # 返回当前脚本在这一侧成功运行的 run 记录；B 一侧的记录还要带 compare，交付前还要对应当前的 B 构建。
        evidence = value.get("evidence") if isinstance(value, dict) else None
        for item in evidence if isinstance(evidence, list) else []:
            if not isinstance(item, dict) or item.get("kind") != "run" or not nonempty_text(item.get("path")):
                continue
            path = self.root / item["path"]
            if not path.is_file():
                continue
            run = json.loads(path.read_text(encoding="utf-8"))
            if (isinstance(run, dict) and run.get("side") == side and run.get("exit_code") == 0
                    and run.get("script_sha256") == script_sha
                    and (side != "replica" or (isinstance(run.get("compare"), dict) and (
                        self.replica_tree is None or run.get("app_sha256") == self.replica_tree)))):
                return run
        extra = ""
        if side == "replica":
            extra = "；B 一侧的 run 需要带 compare（与 A 一侧一起运行，或在 A 一侧已有当前脚本的成功运行后单独运行）"
            if self.replica_tree is not None:
                extra += "，交付前还要来自当前的 reference.artifact_path 构建"
        self.errors.append(f"{owner}: 通过的 script 场景需要当前脚本在 {side} 一侧成功运行的 run 证据"
                           f"（用 scenario_run.py 生成）{extra}")
        return None

    def compared(self, owner, compare, normalization):
        # 两侧输出不同或只在一侧出现的文件，需要在 normalization 写明按什么规则视为一致。
        for key, label in COMPARE_KINDS:
            for name in compare.get(key, []):
                if name not in normalization:
                    self.errors.append(f"{owner}: compare 中 {name} {label}；修复差异，或在 normalization 写明比较规则")

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
        else:
            for fixture in item["fixtures"]:
                if not (self.root / fixture).exists():
                    self.errors.append(f"{owner}: fixture 不存在 {fixture}")
        if not text_list(item.get("differences")):
            self.errors.append(f"{owner}: differences 必须是文本数组")
        normalization = item.get("normalization", {})
        if not isinstance(normalization, dict) or not all(
                nonempty_text(key) and nonempty_text(value) for key, value in normalization.items()):
            self.errors.append(f"{owner}: normalization 需要是「输出文件: 比较规则」的对象")
            normalization = {}
        script, script_sha = item.get("script"), None
        if kind == "script" or script is not None:
            target = self.root / str(script)
            if not nonempty_text(script) or not target.is_file():
                self.errors.append(f"{owner}: script 场景需要存在的脚本文件 {script}")
            elif not os.access(target, os.X_OK):
                self.errors.append(f"{owner}: 脚本不可执行 {script}")
            else:
                script_sha = sha256(target)
        passed = status == "passed"
        scenario_id = item.get("id")
        self.side(f"{owner}.original", item.get("original"), passed and kind in ("gui", "script"),
                  "original", scenario_id)
        self.side(f"{owner}.replica", item.get("replica"), passed, "replica", scenario_id)
        if status == "passed":
            if item.get("differences"):
                self.errors.append(f"{owner}: 通过的场景不能有未解决的 differences")
            for side in ("original", "replica"):
                if not nonempty_text((item.get(side) or {}).get("result")):
                    self.errors.append(f"{owner}: 通过的场景需要记录 {side}.result")
            original = (item.get("original") or {}).get("evidence")
            if not any(isinstance(entry, dict) and entry.get("kind") in RUNTIME_EVIDENCE
                       for entry in (original if isinstance(original, list) else [])):
                self.errors.append(f"{owner}: 通过的场景需要原版 A 的运行时证据"
                                   f"（{'/'.join(RUNTIME_EVIDENCE)}），静态线索不能作为 A 的结果")
            if kind == "script" and script_sha is not None:
                self.runs(f"{owner}.original", item.get("original"), "original", script_sha)
                run = self.runs(f"{owner}.replica", item.get("replica"), "replica", script_sha)
                if run is not None:
                    self.compared(owner, run["compare"], normalization)
        if status == "failed" and not item.get("differences"):
            self.errors.append(f"{owner}: 失败的场景需要写明 differences")
        self.blocker(owner, item, status == "blocked")


def load(path, checker, version=SCHEMA_VERSION):
    if not path.is_file():
        checker.errors.append(f"缺少 {path}")
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        checker.errors.append(f"{path.name}: 顶层必须是 JSON 对象")
        return None
    if data.get("schema_version") != version:
        checker.errors.append(f"{path.name}: schema_version 应为 {version}")
    return data


def objects(checker, name, values):
    if not isinstance(values, list):
        checker.errors.append(f"{name} 必须是数组")
        return []
    if not all(isinstance(item, dict) for item in values):
        checker.errors.append(f"{name}: 每一项必须是对象")
    return [item for item in values if isinstance(item, dict)]


def ax_coverage(checker, ledger, inventory, list_all):
    dumps, all_paths, interactive = [], set(), set()
    app = ledger.get("app") or {}
    for path in sorted((checker.root / "evidence").rglob("*")):
        if not path.is_file():
            continue
        header = ax_header(path)
        if header is None or header.get("bundle_id") != app.get("bundle_id"):
            continue
        relative = str(path.relative_to(checker.root))
        if (header.get("version"), header.get("build")) != (app.get("version"), app.get("build")):
            checker.errors.append(f"{relative}: AX 导出来自 A 的 {header.get('version')}（{header.get('build')}），"
                                  f"功能清单记录的是 {app.get('version')}（{app.get('build')}）")
            continue
        paths, elements = ax_elements(path)
        dumps.append(relative)
        all_paths |= paths
        interactive |= elements
    registered = {item.get("path") for item in inventory}
    # skip 项连同其下的子元素一起视为已登记，例如系统提供的「服务」子菜单。
    skipped = tuple(f"{item['path']} > " for item in inventory
                    if "skip" in item and isinstance(item.get("path"), str))
    wildcards = {}
    for item in inventory:
        path = item.get("path")
        if isinstance(path, str) and WILDCARD in path:
            wildcards[path] = {element for element in interactive
                               if path_matches(path, element, prefix="skip" in item)}
    matched = set().union(*wildcards.values())
    uncovered = sorted(path for path in interactive - registered - matched if not path.startswith(skipped))
    entries = [{"kind": draft_kind(path), "path": path} for path in uncovered]
    summary = {"dumps": dumps, "interactive": len(interactive),
               "covered": len(interactive) - len(uncovered), "uncovered": len(uncovered),
               "uncovered_entries": entries if list_all else entries[:UNCOVERED_SAMPLE],
               "wildcards": {path: len(elements) for path, elements in sorted(wildcards.items())}}
    return all_paths, uncovered, summary


def manifest_checks(checker, manifest, ledger, final):
    project = checker.root.parent
    reference = manifest.get("reference") if isinstance(manifest.get("reference"), dict) else {}
    verification = manifest.get("verification") if isinstance(manifest.get("verification"), dict) else {}
    freeze = manifest.get("freeze") if isinstance(manifest.get("freeze"), dict) else {}
    statuses = {}
    for name in ("fidelity", "independence", "reset"):
        value = verification.get(name) if isinstance(verification.get(name), dict) else {}
        statuses[name] = value.get("status")
        if value.get("status") not in VERIFICATION_STATUS:
            checker.errors.append(f"reference-manifest.verification.{name}: status 取值应为 {'/'.join(VERIFICATION_STATUS)}")
        evidence = value.get("evidence")
        if not text_list(evidence):
            checker.errors.append(f"reference-manifest.verification.{name}: evidence 必须是路径数组")
        elif value.get("status") == "passed":
            if not evidence:
                checker.errors.append(f"reference-manifest.verification.{name}: passed 需要证据")
            for path in evidence:
                if not (checker.root / path).is_file():
                    checker.errors.append(f"reference-manifest.verification.{name}: 证据文件不存在 {path}")
    summary = {"name": reference.get("name"), "bundle_id": reference.get("bundle_id"),
               "verification": statuses, "frozen": bool(freeze.get("artifact_sha256"))}
    if not final:
        return summary
    # independence 需要干净环境，允许保持 pending，交付时向用户说明。
    for name in ("fidelity", "reset"):
        if statuses[name] != "passed":
            checker.errors.append(f"reference-manifest.verification.{name}: 交付前需要 passed")
    owner = "reference-manifest.reference"
    for key in ("name", "bundle_id", "artifact_path", "build_command", "launch_command", "reset_command"):
        if not nonempty_text(reference.get(key)):
            checker.errors.append(f"{owner}.{key}: 交付前需要填写")
    name, bundle_id = reference.get("name"), reference.get("bundle_id")
    if bundle_id and bundle_id == (ledger.get("app") or {}).get("bundle_id"):
        checker.errors.append(f"{owner}.bundle_id: 不能与原版 A 相同")
    if nonempty_text(reference.get("artifact_path")):
        app = project / reference["artifact_path"]
        info_path = app / "Contents" / "Info.plist"
        if app.suffix != ".app" or not info_path.is_file():
            checker.errors.append(f"{owner}.artifact_path: 需要指向 B 的 .app {reference['artifact_path']}")
        else:
            info = plistlib.loads(info_path.read_bytes())
            if info.get("CFBundleIdentifier") != bundle_id:
                checker.errors.append(f"{owner}: .app 的 CFBundleIdentifier 是 {info.get('CFBundleIdentifier')}，记录的是 {bundle_id}")
            names = {".app 文件名": app.stem, "CFBundleName": info.get("CFBundleName"),
                     "CFBundleDisplayName": info.get("CFBundleDisplayName", name)}
            for label, value in names.items():
                if value != name:
                    checker.errors.append(f"{owner}: {label} 是 {value}，需要使用 B 的名称 {name}")
    for key in ("reference_version", "frozen_at", "source_revision", "artifact", "artifact_sha256"):
        if not nonempty_text(freeze.get(key)):
            checker.errors.append(f"reference-manifest.freeze.{key}: 交付前需要冻结版本")
    if nonempty_text(freeze.get("artifact")) and nonempty_text(freeze.get("artifact_sha256")):
        artifact = project / freeze["artifact"]
        if not artifact.is_file():
            checker.errors.append(f"reference-manifest.freeze.artifact: 需要是存在的文件（例如 .zip 归档）{freeze['artifact']}")
        elif sha256(artifact) != freeze["artifact_sha256"]:
            checker.errors.append("reference-manifest.freeze.artifact_sha256: 与制品的实际 SHA-256 不一致")
    return summary


def check(root, final, list_uncovered=False):
    checker = Checker(root)
    ledger = load(root / "feature-ledger.json", checker)
    scenario_file = load(root / "scenarios.json", checker)
    if ledger is None or scenario_file is None:
        return checker, {}
    manifest_path = root / "reference-manifest.json"
    manifest = load(manifest_path, checker, MANIFEST_SCHEMA_VERSION) if final or manifest_path.exists() else None
    app = ledger.get("app") if isinstance(ledger.get("app"), dict) else {}
    checker.original_id = app.get("bundle_id")
    if isinstance(manifest, dict) and isinstance(manifest.get("reference"), dict):
        checker.replica_id = manifest["reference"].get("bundle_id")
        artifact = manifest["reference"].get("artifact_path")
        if final and nonempty_text(artifact) and (root.parent / artifact / "Contents" / "Info.plist").is_file():
            checker.replica_tree = tree_sha256(root.parent / artifact)

    inventory = objects(checker, "inventory", ledger.get("inventory"))
    clues = objects(checker, "clues", ledger.get("clues", []))
    states = objects(checker, "states", ledger.get("states", []))
    features = objects(checker, "features", ledger.get("features"))
    scenarios = objects(checker, "scenarios", scenario_file.get("scenarios"))
    for name, values in (("states", states), ("features", features), ("scenarios", scenarios)):
        ids = Counter(item.get("id") for item in values)
        for duplicate in sorted(key for key, count in ids.items() if count > 1):
            checker.errors.append(f"{name}: ID 重复 {duplicate}")

    feature_ids = {item.get("id") for item in features}
    ax_paths, uncovered, ax_summary = ax_coverage(checker, ledger, inventory, list_uncovered)
    checker.inventory(inventory, feature_ids, ax_paths)
    bundle_path = root / "evidence" / "bundle" / "bundle.json"
    required = (set(bundle_clues(json.loads(bundle_path.read_text(encoding="utf-8"))))
                if bundle_path.is_file() else None)
    checker.clues(clues, feature_ids, required)
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
    mapped_clues = {(item.get("source"), item.get("name")) for item in clues}
    unmapped = ([{"source": source, "name": name} for source, name in sorted(required - mapped_clues)]
                if required is not None else None)
    ax_unavailable = ledger.get("ax_unavailable")
    if ax_unavailable is not None and not nonempty_text(ax_unavailable):
        checker.errors.append("ax_unavailable: 需要写明 AX 无法读取原版 A 的原因")
    checker.states(states, app, final, ax_unavailable)

    reference = (manifest_checks(checker, manifest, ledger, final)
                 if isinstance(manifest, dict) else None)
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
        if not ax_summary["dumps"] and ax_unavailable is None:
            checker.errors.append("交付前需要原版 A 的 AX 导出（ax dump 的逐行输出，放在 evidence/ 下）；"
                                  "AX 确实读不到 A 时在 ax_unavailable 写明原因")
        if not states:
            checker.errors.append("交付前需要在 states 列出 A 的各个界面状态及到达方式")
        if uncovered:
            checker.errors.append(f"A 的 AX 导出中有 {len(uncovered)} 个可操作元素没有登记到 inventory；"
                                  "用 --uncovered 列出全部")
        if required is None:
            checker.errors.append("交付前需要 evidence/bundle/bundle.json；先运行 bundle_scan.py")
        elif unmapped:
            checker.errors.append(f"clues: {len(unmapped)} 条静态线索没有指向功能或写明 skip，见 clues.unmapped")

    summary = {
        "inventory": {"total": len(inventory),
                      "mapped": sum(1 for item in inventory if "feature" in item),
                      "skipped": sum(1 for item in inventory if "skip" in item)},
        "ax": ax_summary,
        "states": {"total": len(states),
                   "with_dump": sum(1 for item in states if text_list(item.get("dumps"), allow_empty=False))},
        "clues": {"required": None if required is None else len(required),
                  "mapped": sum(1 for item in clues if "feature" in item),
                  "skipped": sum(1 for item in clues if "skip" in item),
                  "unmapped": unmapped},
        "features": {"total": len(features),
                     "status": dict(Counter(item.get("status") for item in features))},
        "scenarios": {"total": len(scenarios),
                      "status": dict(Counter(item.get("status") for item in scenarios))},
        "entry_kinds": {"covered": covered, "absent": sorted(absent), "unchecked": unchecked},
        "reference": reference,
    }
    return checker, summary


def main():
    parser = argparse.ArgumentParser(description="校验复刻项目的入口清单、静态线索、功能、场景、证据与 B 的构建记录。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--final", action="store_true",
                        help="交付前检查：所有功能和场景都需要 passed 或 blocked，覆盖和冻结记录完整")
    parser.add_argument("--uncovered", action="store_true",
                        help="列出 A 的 AX 导出中全部未登记的可操作元素（默认只列前 20 个）")
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve() / "replica"
    checker, summary = check(root, args.final, args.uncovered)
    print(json.dumps({"final": args.final, **summary, "errors": checker.errors},
                     ensure_ascii=False, indent=2))
    raise SystemExit(1 if checker.errors else 0)


if __name__ == "__main__":
    main()
