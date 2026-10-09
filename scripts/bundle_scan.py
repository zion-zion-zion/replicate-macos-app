import argparse
import json
import plistlib
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

XINCLUDE = "{http://www.w3.org/2003/XInclude}include"
TRUE_VALUES = (True, 1, "1", "YES", "yes", "true", "TRUE")
DATA_SUFFIXES = {".json", ".plist", ".xml", ".csv", ".yaml", ".yml", ".toml"}
SQLITE_MAGIC = b"SQLite format 3\x00"


def run(argv):
    return subprocess.run(argv, text=True, capture_output=True, check=True).stdout


def load_plist(path):
    with path.open("rb") as handle:
        return plistlib.load(handle)


def plist_file_as_json(path):
    # .strings 可能是旧式文本 plist，plistlib 不支持，用系统 plutil 转换。
    return json.loads(run(["plutil", "-convert", "json", "-o", "-", str(path)]))


def encode(value):
    if isinstance(value, bytes):
        return f"<data {len(value)} bytes>"
    if isinstance(value, plistlib.UID):
        return f"<UID {value.data}>"
    return value.isoformat()


def linked_libraries(executable):
    libraries = []
    for line in run(["otool", "-L", str(executable)]).splitlines():
        if line.startswith("\t"):
            path = line.strip().split(" (compatibility", 1)[0]
            if path not in libraries:
                libraries.append(path)
    return libraries


def signature(app):
    proc = subprocess.run(["codesign", "-d", "--entitlements", "-", "--xml", str(app)],
                          capture_output=True)
    if proc.returncode:
        message = proc.stderr.decode(errors="replace").strip()
        if "not signed at all" in message:
            return {"signed": False, "entitlements": {}}
        raise RuntimeError(f"codesign 退出码 {proc.returncode}: {message}")
    return {"signed": True,
            "entitlements": plistlib.loads(proc.stdout) if proc.stdout.strip() else {}}


def detect_stack(contents, libraries):
    frameworks = contents / "Frameworks"
    embedded = sorted(item.name for item in frameworks.iterdir()) if frameworks.is_dir() else []
    resources = contents / "Resources"

    def links(fragment):
        return any(fragment in library for library in libraries)

    checks = {
        "electron": "Electron Framework.framework" in embedded or (resources / "app.asar").exists(),
        "catalyst": links("/System/iOSSupport/"),
        "swiftui": links("/SwiftUI.framework/"),
        "appkit": links("/AppKit.framework/") or links("/Cocoa.framework/"),
        "qt": "QtCore.framework" in embedded,
        "flutter": "FlutterMacOS.framework" in embedded,
        "java": (contents / "Java").is_dir() or (contents / "runtime").is_dir()
                or any(contents.glob("PlugIns/*.jdk")) or any(contents.glob("*/jre")),
        "webkit": links("/WebKit.framework/"),
        "swift": any("libswift" in library for library in libraries),
        "sparkle": "Sparkle.framework" in embedded,
    }
    return {"tags": [name for name, present in checks.items() if present],
            "linked_libraries": libraries, "embedded_frameworks": embedded}


def document_types(info):
    return [{"name": item.get("CFBundleTypeName"), "role": item.get("CFBundleTypeRole"),
             "rank": item.get("LSHandlerRank"), "content_types": item.get("LSItemContentTypes", []),
             "extensions": item.get("CFBundleTypeExtensions", []),
             "document_class": item.get("NSDocumentClass")}
            for item in info.get("CFBundleDocumentTypes", [])]


def type_declarations(info, key):
    return [{"identifier": item.get("UTTypeIdentifier"), "description": item.get("UTTypeDescription"),
             "conforms_to": item.get("UTTypeConformsTo", []),
             "extensions": item.get("UTTypeTagSpecification", {}).get("public.filename-extension", [])}
            for item in info.get(key, [])]


def services(info):
    return [{"menu_item": item.get("NSMenuItem", {}).get("default"), "message": item.get("NSMessage"),
             "send_types": item.get("NSSendTypes", []), "return_types": item.get("NSReturnTypes", [])}
            for item in info.get("NSServices", [])]


def scripting(info, resources):
    result = {"enabled": info.get("NSAppleScriptEnabled") in TRUE_VALUES,
              "sdef": info.get("OSAScriptingDefinition"), "includes": [], "suites": [],
              "legacy_suites": sorted(path.name for path in resources.glob("*.scriptSuite"))}
    if result["sdef"]:
        root = ET.parse(resources / result["sdef"]).getroot()
        result["includes"] = [item.get("href") for item in root.iter(XINCLUDE)]
        result["suites"] = [{"name": suite.get("name"),
                             "commands": [item.get("name") for item in suite.findall("command")],
                             "classes": [item.get("name") for item in suite.findall("class")]
                             + [item.get("extends") for item in suite.findall("class-extension")]}
                            for suite in root.iter("suite")]
    return result


def app_intents(resources):
    path = resources / "Metadata.appintents" / "extract.actionsdata"
    if not path.is_file():
        return []
    actions = json.loads(path.read_text(encoding="utf-8")).get("actions", {})
    return [{"id": key, "title": (value.get("title") or {}).get("key")}
            for key, value in sorted(actions.items())]


def nested_bundle(path):
    info_path = path / "Contents" / "Info.plist"
    if not info_path.is_file():
        info_path = path / "Info.plist"
    info = load_plist(info_path) if info_path.is_file() else {}
    extension = info.get("NSExtension", {})
    attributes = info.get("EXAppExtensionAttributes", {})
    return {"name": path.name, "bundle_id": info.get("CFBundleIdentifier"),
            "extension_point": extension.get("NSExtensionPointIdentifier")
            or attributes.get("EXExtensionPointIdentifier")}


def embedded_components(contents):
    library = contents / "Library"
    return {
        "extensions": [nested_bundle(path) for pattern in ("PlugIns/*.appex", "Extensions/*.appex")
                       for path in sorted(contents.glob(pattern))],
        "other_plugins": sorted(path.name for path in contents.glob("PlugIns/*")
                                if path.suffix != ".appex"),
        "xpc_services": [nested_bundle(path) for path in sorted(contents.glob("XPCServices/*.xpc"))],
        "library": {folder.name: sorted(item.name for item in folder.iterdir())
                    for folder in sorted(library.iterdir()) if folder.is_dir()}
        if library.is_dir() else {},
        "helpers": sorted(path.name for path in contents.glob("Helpers/*")),
    }


def region_directories(resources, region):
    names = [f"{region}.lproj"]
    if region in ("en", "English"):
        names += ["en.lproj", "English.lproj"]
    names.append("Base.lproj")
    found = []
    for name in names:
        if (resources / name).is_dir() and name not in found:
            found.append(name)
    return found


def string_tables(resources, region):
    tables = {}
    directories = region_directories(resources, region)
    for directory in directories:
        for path in sorted((resources / directory).iterdir()):
            if path.suffix in (".strings", ".stringsdict"):
                tables[f"{directory}/{path.name}"] = plist_file_as_json(path)
    for path in sorted(resources.glob("*.loctable")):
        languages = load_plist(path)
        language = next((code for code in (region, "en", "Base") if code in languages), None)
        if language is not None:
            tables[f"{path.name}[{language}]"] = languages[language]
    return directories, tables


def in_region(path, regions):
    # 只保留开发语言与 Base 的本地化目录，其余语言的同名资源不重复列出。
    return all(not part.endswith(".lproj") or part in regions for part in path.parts)


def help_book(info, app, resources, regions):
    folder = info.get("CFBundleHelpBookFolder")
    roots = sorted(resources.glob("*.help"))
    if folder:
        roots += [path for path in (resources / folder, *sorted(resources.glob(f"*.lproj/{folder}")))
                  if path.is_dir()]
    pages = sorted({str(page.relative_to(app)) for root in roots for page in root.rglob("*.htm*")
                    if in_region(page.relative_to(resources), regions)})
    return {"name": info.get("CFBundleHelpBookName"), "folder": folder, "pages": pages}


def sqlite_schema(path, immutable=True):
    # 运行中的 App 可能正在写入，读取它的数据库时不能用 immutable。
    query = "mode=ro&immutable=1" if immutable else "mode=ro"
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?{query}", uri=True, timeout=5)
    try:
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = [name for kind, name, _ in rows if kind == "table"]
        counts = {name: connection.execute(
                      'SELECT count(*) FROM "{}"'.format(name.replace('"', '""'))).fetchone()[0]
                  for name in tables}
    finally:
        connection.close()
    return {"objects": [{"type": kind, "name": name, "sql": sql} for kind, name, sql in rows],
            "row_counts": counts}


def data_resources(app, resources, regions):
    files = [path for path in resources.rglob("*")
             if path.is_file() and not path.is_symlink() and in_region(path.relative_to(resources), regions)]
    databases = {}
    for path in files:
        with path.open("rb") as handle:
            if handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC:
                databases[str(path.relative_to(app))] = sqlite_schema(path)
    models = [path for path in resources.rglob("*.mom*")
              if path.suffix == ".momd" or (path.suffix == ".mom" and path.parent.suffix != ".momd")]
    return {
        "suffix_counts": dict(Counter(path.suffix.lower() or "<无扩展名>" for path in files).most_common()),
        "core_data_models": sorted(str(path.relative_to(app)) for path in models),
        "sqlite_databases": databases,
        "data_files": sorted(str(path.relative_to(app)) for path in files
                             if path.suffix.lower() in DATA_SUFFIXES and path.name != "Info.plist"),
    }


def asset_catalogs(app, resources, regions, output):
    summary = {}
    for path in sorted(resources.rglob("*.car")):
        if not in_region(path.relative_to(resources), regions):
            continue
        entries = json.loads(run(["assetutil", "--info", str(path)]))
        relative = str(path.relative_to(app))
        target = output / f"assets-{relative.replace('/', '_')}.json"
        target.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        names = {}
        for entry in entries:
            if "Name" in entry:
                names.setdefault(entry["Name"], set()).add(entry.get("AssetType"))
        summary[relative] = {"detail_file": target.name, "asset_count": len(names),
                             "names": {name: sorted(filter(None, kinds)) for name, kinds in sorted(names.items())}}
    return summary


def nib_files(app, resources, regions):
    return sorted(str(path.relative_to(app)) for pattern in ("*.nib", "*.storyboardc")
                  for path in resources.rglob(pattern)
                  if in_region(path.relative_to(resources), regions)
                  and not any(parent.suffix in (".nib", ".storyboardc")
                              for parent in path.relative_to(resources).parents))


def inspect(app, output):
    contents = app / "Contents"
    info = load_plist(contents / "Info.plist")
    resources = contents / "Resources"
    executable = contents / "MacOS" / info["CFBundleExecutable"]
    sign = signature(app)
    entitlements = sign["entitlements"]
    region = info.get("CFBundleDevelopmentRegion", "en")
    directories, tables = string_tables(resources, region)
    stack = detect_stack(contents, linked_libraries(executable))
    # Electron 的 JS 在 app.asar 里，或以 app/ 目录直接存放。
    electron_app = next((str(path) for path in (resources / "app.asar", resources / "app")
                         if "electron" in stack["tags"] and path.exists()), None)
    report = {
        "schema_version": 2,
        "app_path": str(app),
        "identity": {
            "bundle_id": info.get("CFBundleIdentifier"),
            "name": info.get("CFBundleDisplayName") or info.get("CFBundleName"),
            "version": info.get("CFBundleShortVersionString"),
            "build": info.get("CFBundleVersion"),
            "executable": info["CFBundleExecutable"],
            "minimum_system": info.get("LSMinimumSystemVersion"),
            "development_region": region,
            "category": info.get("LSApplicationCategoryType"),
            "principal_class": info.get("NSPrincipalClass"),
            "main_nib": info.get("NSMainNibFile"),
            "main_storyboard": info.get("NSMainStoryboardFile"),
            "update_feed": info.get("SUFeedURL"),
        },
        "stack": stack,
        "traits": {
            "menu_bar_agent": info.get("LSUIElement") in TRUE_VALUES,
            "background_only": info.get("LSBackgroundOnly") in TRUE_VALUES,
            "declares_documents": bool(info.get("CFBundleDocumentTypes")),
            "document_classes": sorted({item["document_class"] for item in document_types(info)
                                        if item["document_class"]}),
            "sandboxed": entitlements.get("com.apple.security.app-sandbox") is True,
            "app_groups": entitlements.get("com.apple.security.application-groups", []),
            "signed": sign["signed"],
        },
        "entries": {
            "document_types": document_types(info),
            "exported_types": type_declarations(info, "UTExportedTypeDeclarations"),
            "imported_types": type_declarations(info, "UTImportedTypeDeclarations"),
            "url_schemes": [{"name": item.get("CFBundleURLName"),
                             "schemes": item.get("CFBundleURLSchemes", [])}
                            for item in info.get("CFBundleURLTypes", [])],
            "services": services(info),
            "applescript": scripting(info, resources),
            "app_intents": app_intents(resources),
            **embedded_components(contents),
        },
        "usage_descriptions": {key: value for key, value in info.items()
                               if key.endswith("UsageDescription")},
        "entitlements": entitlements,
        "resources": {
            "localizations": sorted(path.stem for path in resources.glob("*.lproj")),
            "string_region_directories": directories,
            "string_tables": {name: len(values) for name, values in tables.items()},
            "nibs": nib_files(app, resources, directories),
            "asset_catalogs": asset_catalogs(app, resources, directories, output),
            "help_book": help_book(info, app, resources, directories),
            "electron_app": electron_app,
            **data_resources(app, resources, directories),
        },
    }
    strings = {"app_path": str(app), "region_directories": directories, "tables": tables}
    return report, strings


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=encode) + "\n",
                    encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="读取原版 App 包中可静态获得的入口、技术栈、文案和资源。")
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve() / "replica"
    ledger = json.loads((root / "feature-ledger.json").read_text(encoding="utf-8"))
    app = Path(ledger["app"]["path"])
    if not (app / "Contents" / "Info.plist").is_file():
        parser.error(f"功能清单记录的 App 不存在: {app}")
    output = root / "evidence" / "bundle"
    output.mkdir(parents=True, exist_ok=True)
    report, strings = inspect(app, output)
    write_json(output / "bundle.json", report)
    write_json(output / "strings.json", strings)
    entries, resources = report["entries"], report["resources"]
    print(json.dumps({
        "files": sorted(str(path.relative_to(root)) for path in output.iterdir()),
        "stack": report["stack"]["tags"],
        "traits": report["traits"],
        "update_feed": report["identity"]["update_feed"],
        "electron_app": resources["electron_app"],
        "counts": {
            "document_types": len(entries["document_types"]),
            "url_schemes": sum(len(item["schemes"]) for item in entries["url_schemes"]),
            "services": len(entries["services"]),
            "applescript_commands": sum(len(suite["commands"])
                                        for suite in entries["applescript"]["suites"]),
            "app_intents": len(entries["app_intents"]),
            "extensions": len(entries["extensions"]),
            "xpc_services": len(entries["xpc_services"]),
            "strings": sum(resources["string_tables"].values()),
            "nibs": len(resources["nibs"]),
            "assets": sum(item["asset_count"] for item in resources["asset_catalogs"].values()),
            "help_pages": len(resources["help_book"]["pages"]),
            "core_data_models": len(resources["core_data_models"]),
            "sqlite_databases": len(resources["sqlite_databases"]),
            "data_files": len(resources["data_files"]),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
