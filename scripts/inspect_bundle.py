import argparse
import json
import plistlib
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

XINCLUDE = "{http://www.w3.org/2003/XInclude}include"
TRUE_VALUES = (True, 1, "1", "YES", "yes", "true", "TRUE")


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


def resource_summary(resources, tables):
    nibs = set()
    for pattern in ("*.nib", "*.storyboardc", "*.lproj/*.nib", "*.lproj/*.storyboardc"):
        nibs.update(path.stem for path in resources.glob(pattern))
    asar = resources / "app.asar"
    return {
        "localizations": sorted(path.stem for path in resources.glob("*.lproj")),
        "nibs": sorted(nibs),
        "asset_catalogs": sorted(path.name for path in resources.glob("*.car")),
        "string_tables": {name: len(values) for name, values in tables.items()},
        "electron_asar": str(asar) if asar.exists() else None,
    }


def inspect(app):
    contents = app / "Contents"
    info = load_plist(contents / "Info.plist")
    resources = contents / "Resources"
    executable = contents / "MacOS" / info["CFBundleExecutable"]
    sign = signature(app)
    entitlements = sign["entitlements"]
    region = info.get("CFBundleDevelopmentRegion", "en")
    directories, tables = string_tables(resources, region)
    report = {
        "schema_version": 1,
        "app_path": str(app),
        "identity": {
            "bundle_id": info.get("CFBundleIdentifier"),
            "name": info.get("CFBundleDisplayName") or info.get("CFBundleName"),
            "version": info.get("CFBundleShortVersionString"),
            "build": info.get("CFBundleVersion"),
            "minimum_system": info.get("LSMinimumSystemVersion"),
            "development_region": region,
            "category": info.get("LSApplicationCategoryType"),
            "principal_class": info.get("NSPrincipalClass"),
            "main_nib": info.get("NSMainNibFile"),
            "main_storyboard": info.get("NSMainStoryboardFile"),
            "help_book": info.get("CFBundleHelpBookName"),
        },
        "stack": detect_stack(contents, linked_libraries(executable)),
        "traits": {
            "menu_bar_agent": info.get("LSUIElement") in TRUE_VALUES,
            "background_only": info.get("LSBackgroundOnly") in TRUE_VALUES,
            "declares_documents": bool(info.get("CFBundleDocumentTypes")),
            "document_classes": sorted({item["document_class"] for item in document_types(info)
                                        if item["document_class"]}),
            "sandboxed": entitlements.get("com.apple.security.app-sandbox") is True,
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
        "resources": resource_summary(resources, tables),
        "strings_file": "bundle-strings.json",
    }
    strings = {"app_path": str(app), "region_directories": directories, "tables": tables}
    return report, strings


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=encode) + "\n",
                    encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="盘点 macOS App 包中可静态读取的功能入口与技术栈。")
    parser.add_argument("app_path", type=Path)
    parser.add_argument("output_dir", type=Path, help="通常为 PROJECT_DIR/replica/evidence")
    args = parser.parse_args()
    app = args.app_path.expanduser().resolve()
    if not (app / "Contents" / "Info.plist").is_file():
        parser.error(f"不是有效的 App bundle: {app}")
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    report, strings = inspect(app)
    write_json(output / "bundle.json", report)
    write_json(output / "bundle-strings.json", strings)
    entries = report["entries"]
    print(json.dumps({
        "bundle_json": str(output / "bundle.json"),
        "strings_json": str(output / "bundle-strings.json"),
        "stack": report["stack"]["tags"],
        "traits": report["traits"],
        "counts": {
            "document_types": len(entries["document_types"]),
            "url_schemes": sum(len(item["schemes"]) for item in entries["url_schemes"]),
            "services": len(entries["services"]),
            "applescript_commands": sum(len(suite["commands"])
                                        for suite in entries["applescript"]["suites"]),
            "app_intents": len(entries["app_intents"]),
            "extensions": len(entries["extensions"]),
            "xpc_services": len(entries["xpc_services"]),
            "strings": sum(report["resources"]["string_tables"].values()),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
