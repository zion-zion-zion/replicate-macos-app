import argparse
import datetime
import hashlib
import json
import os
import plistlib
import subprocess
from pathlib import Path

from bundle_scan import SQLITE_MAGIC, signature, sqlite_schema

HASH_LIMIT = 16 * 1024 * 1024
PRINT_LIMIT = 50
LIBRARY = Path.home() / "Library"
ACCESS_HINT = ("请给运行本脚本的 App（如 Codex 或终端）授予「完全磁盘访问权限」，"
               "或在系统提示访问其他 App 的数据时允许，然后重试。")


def app_identity(app):
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    entitlements = signature(app)["entitlements"]
    names = [info.get(key) for key in ("CFBundleName", "CFBundleDisplayName", "CFBundleExecutable")]
    return {"path": str(app), "bundle_id": info["CFBundleIdentifier"],
            "names": list(dict.fromkeys(name for name in names if name)),
            "sandboxed": entitlements.get("com.apple.security.app-sandbox") is True,
            "app_groups": entitlements.get("com.apple.security.application-groups", [])}


def denied(path, error):
    return SystemExit(f"无权读取 {path}：{error}。{ACCESS_HINT}")


def require_access(path):
    try:
        with os.scandir(path):
            pass
    except PermissionError as error:
        raise denied(path, error) from error


def require_tree_access(container, target):
    # 无权读取其他 App 的容器时，defaults 会返回空字典而不报错；容器顶层可列出时内部仍可能受限，逐层确认。
    current = container
    require_access(current)
    for part in target.relative_to(container).parts:
        current = current / part
        try:
            if not current.is_dir():
                return
        except PermissionError as error:
            raise denied(current, error) from error
        require_access(current)


def scalar(value):
    if isinstance(value, bytes):
        return f"<data {len(value)} bytes sha256:{hashlib.sha256(value).hexdigest()[:16]}>"
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, plistlib.UID):
        return f"<UID {value.data}>"
    if isinstance(value, (dict, list)):
        return {} if isinstance(value, dict) else []
    return value


def flatten(value, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(value, dict) and value:
        for key, item in value.items():
            flatten(item, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            flatten(item, f"{prefix}[{index}]", out)
    elif isinstance(value, bytes) and value.startswith(b"bplist00"):
        flatten(plistlib.loads(value), f"{prefix}<bplist>", out)
    elif prefix or not isinstance(value, (dict, list)):
        out[prefix or "$"] = scalar(value)
    return out


def preference_domains(identity):
    bundle_id = identity["bundle_id"]
    domains = {}
    if identity["sandboxed"]:
        container = LIBRARY / "Containers" / bundle_id
        domains[bundle_id] = (container, container / "Data/Library/Preferences" / f"{bundle_id}.plist", False)
    else:
        domains[bundle_id] = (None, bundle_id, False)
        domains[f"{bundle_id} (currentHost)"] = (None, bundle_id, True)
    for group in identity["app_groups"]:
        container = LIBRARY / "Group Containers" / group
        domains[group] = (container, container / "Library/Preferences" / f"{group}.plist", False)
    return domains


def read_preferences(identity):
    result = {}
    for label, (container, domain, current_host) in preference_domains(identity).items():
        if container is not None:
            if not container.exists():
                result[label] = None
                continue
            require_tree_access(container, domain.parent)
        argv = ["defaults", *(["-currentHost"] if current_host else []), "export", str(domain), "-"]
        output = subprocess.run(argv, capture_output=True, check=True).stdout
        result[label] = flatten(plistlib.loads(output))
    return result


def locations(identity, extra):
    bundle_id = identity["bundle_id"]
    paths = [LIBRARY / "Application Support" / bundle_id,
             *(LIBRARY / "Application Support" / name for name in identity["names"]),
             LIBRARY / "Caches" / bundle_id, LIBRARY / "HTTPStorages" / bundle_id,
             LIBRARY / "WebKit" / bundle_id,
             LIBRARY / "Saved Application State" / f"{bundle_id}.savedState",
             *(LIBRARY / "Logs" / name for name in identity["names"])]
    if identity["sandboxed"]:
        paths.append(LIBRARY / "Containers" / bundle_id)
    paths += [LIBRARY / "Group Containers" / group for group in identity["app_groups"]]
    paths += [path.expanduser().resolve() for path in extra]
    return list(dict.fromkeys(str(path) for path in paths))


def describe(path):
    stat = path.lstat()
    entry = {"type": "file", "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    with path.open("rb") as handle:
        header = handle.read(len(SQLITE_MAGIC))
        if stat.st_size <= HASH_LIMIT:
            digest = hashlib.sha256(header)
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
    if path.suffix == ".plist":
        with path.open("rb") as handle:
            entry["plist"] = flatten(plistlib.load(handle))
    elif header == SQLITE_MAGIC:
        entry["sqlite"] = sqlite_schema(path, immutable=False)
    return entry


def scan(root):
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        return None
    require_access(root)

    def on_error(error):
        if isinstance(error, PermissionError):
            raise denied(error.filename, error) from error
        raise error

    entries = {}
    for directory, dirnames, filenames in os.walk(root, onerror=on_error):
        base = Path(directory)
        for name in dirnames + filenames:
            path = base / name
            relative = str(path.relative_to(root))
            try:
                if path.is_symlink():
                    entries[relative] = {"type": "symlink", "target": os.readlink(path)}
                elif path.is_dir():
                    entries[relative] = {"type": "dir"}
                elif path.is_file():
                    entries[relative] = describe(path)
            except PermissionError as error:
                raise denied(path, error) from error
    return entries


def diff_maps(before, after):
    result = {
        "added": {key: after[key] for key in sorted(after.keys() - before.keys())},
        "removed": {key: before[key] for key in sorted(before.keys() - after.keys())},
        "changed": {key: [before[key], after[key]] for key in sorted(before.keys() & after.keys())
                    if before[key] != after[key]},
    }
    return {key: value for key, value in result.items() if value}


def diff_entry(before, after):
    if before["type"] != after["type"]:
        return {"type": [before["type"], after["type"]]}
    if before["type"] == "symlink":
        return {"target": [before["target"], after["target"]]} if before != after else None
    if before["type"] == "dir":
        return None
    if "sha256" in before and "sha256" in after:
        same = before["sha256"] == after["sha256"]
    else:
        same = (before["size"], before["mtime_ns"]) == (after["size"], after["mtime_ns"])
    if same:
        return {"touched": True} if before["mtime_ns"] != after["mtime_ns"] else None
    detail = {}
    if before["size"] != after["size"]:
        detail["size"] = [before["size"], after["size"]]
    if "plist" in before or "plist" in after:
        detail["plist"] = diff_maps(before.get("plist", {}), after.get("plist", {}))
    if "sqlite" in before or "sqlite" in after:
        old, new = before.get("sqlite", {}), after.get("sqlite", {})
        detail["sqlite"] = {key: value for key, value in {
            "row_counts": diff_maps(old.get("row_counts", {}), new.get("row_counts", {})),
            "schema_changed": old.get("objects") != new.get("objects"),
        }.items() if value}
    return detail or {"content_changed": True}


def diff_locations(before, after):
    result = {}
    for location in dict.fromkeys([*before, *after]):
        old, new = before.get(location) or {}, after.get(location) or {}
        modified, touched = [], []
        for path in sorted(old.keys() & new.keys()):
            detail = diff_entry(old[path], new[path])
            if detail == {"touched": True}:
                touched.append(path)
            elif detail:
                modified.append({"path": path, **detail})
        changes = {"added": [{"path": path, "type": new[path]["type"]} for path in sorted(new.keys() - old.keys())],
                   "removed": [{"path": path, "type": old[path]["type"]} for path in sorted(old.keys() - new.keys())],
                   "modified": modified, "touched": touched}
        changes = {key: value for key, value in changes.items() if value}
        if before.get(location) is None and after.get(location) is not None:
            changes["created"] = True
        if before.get(location) is not None and after.get(location) is None:
            changes["deleted"] = True
        if changes:
            result[location] = changes
    return result


def state_dir(project_dir):
    path = project_dir.expanduser().resolve() / "replica" / "evidence" / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot(args):
    root = args.project_dir.expanduser().resolve() / "replica"
    if args.app_path:
        app = args.app_path.expanduser().resolve()
    else:
        app = Path(json.loads((root / "feature-ledger.json").read_text(encoding="utf-8"))["app"]["path"])
    if not (app / "Contents" / "Info.plist").is_file():
        raise SystemExit(f"不是有效的 App bundle: {app}")
    target = state_dir(args.project_dir) / f"{args.name}.json"
    if target.exists():
        raise SystemExit(f"快照 {args.name} 已存在：{target}；换一个名称")
    identity = app_identity(app)
    data = {"name": args.name, "app": identity,
            "taken_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "preferences": read_preferences(identity),
            "locations": {location: scan(location) for location in locations(identity, args.path)}}
    with target.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({
        "snapshot": str(target.relative_to(root)), "app": identity["bundle_id"],
        "preferences": {label: None if values is None else len(values)
                        for label, values in data["preferences"].items()},
        "locations": {location: None if entries is None else len(entries)
                      for location, entries in data["locations"].items()},
    }, ensure_ascii=False, indent=2))


def diff(args):
    directory = state_dir(args.project_dir)
    before, after = (json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
                     for name in (args.before, args.after))
    if before["app"]["bundle_id"] != after["app"]["bundle_id"]:
        raise SystemExit(f"两个快照属于不同 App：{before['app']['bundle_id']} 与 {after['app']['bundle_id']}")
    preferences = {}
    for label in dict.fromkeys([*before["preferences"], *after["preferences"]]):
        changes = diff_maps(before["preferences"].get(label) or {}, after["preferences"].get(label) or {})
        if changes:
            preferences[label] = changes
    result = {"before": args.before, "after": args.after, "app": after["app"]["bundle_id"],
              "preferences": preferences,
              "locations": diff_locations(before["locations"], after["locations"])}
    target = directory / f"{args.before}--{args.after}.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shown = json.loads(json.dumps(result))
    for changes in shown["locations"].values():
        for key in ("added", "removed", "modified", "touched"):
            if len(changes.get(key, [])) > PRINT_LIMIT:
                changes[key] = changes[key][:PRINT_LIMIT] + [f"…另有 {len(changes[key]) - PRINT_LIMIT} 项，见完整文件"]
    shown["file"] = str(target.relative_to(directory.parent.parent))
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="对 App 的偏好设置和数据目录拍快照，并比较两次快照。")
    commands = parser.add_subparsers(dest="command", required=True)
    take = commands.add_parser("snapshot", help="拍快照，写入 replica/evidence/state/NAME.json")
    take.add_argument("project_dir", type=Path)
    take.add_argument("name")
    take.add_argument("--app-path", type=Path, help="默认为功能清单记录的原版；对复刻版拍快照时指定")
    take.add_argument("--path", type=Path, action="append", default=[],
                      help="额外纳入的目录，例如测试文件所在的隔离目录；可重复")
    take.set_defaults(handler=snapshot)
    compare = commands.add_parser("diff", help="比较两次快照，写入 replica/evidence/state/BEFORE--AFTER.json")
    compare.add_argument("project_dir", type=Path)
    compare.add_argument("before")
    compare.add_argument("after")
    compare.set_defaults(handler=diff)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
