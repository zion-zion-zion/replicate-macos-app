import AppKit
import ApplicationServices

let usage = """
用法（未编译时用 swift ax.swift 代替 ax）：
  ax check
  ax dump BUNDLE_ID [--pid PID] [--root PATH] [--max-depth N] [--max-nodes N]
                    [--out FILE.json] [--flat FILE.txt] [--no-frames]
  ax perform BUNDLE_ID PATH [--pid PID] [--action AXPress]

元素路径由 " > " 连接的段组成，段写作 Role[标签] 或 Role，兄弟重复时追加 #序号；
dump 输出的 path 可以原样传给 perform 和 --root。没有 --out 和 --flat 时，逐行输出到标准输出。
"""

let attributeNames = [
    "AXRole", "AXSubrole", "AXTitle", "AXDescription", "AXIdentifier", "AXValue", "AXHelp",
    "AXEnabled", "AXFocused", "AXSelected", "AXPosition", "AXSize",
    "AXMenuItemCmdChar", "AXMenuItemCmdVirtualKey", "AXMenuItemCmdGlyph",
    "AXMenuItemCmdModifiers", "AXMenuItemMarkChar", "AXChildren",
]
let menuRoles: Set<String> = ["AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem"]
let ignoredErrors: Set<AXError> = [.attributeUnsupported, .noValue]
let valueLimit = 500

// 取值见 HIToolbox/Menus.h 的 kMenu*Glyph。
var glyphs: [Int: String] = [
    0x02: "⇥", 0x03: "⇤", 0x04: "⌤", 0x09: "␣", 0x0A: "⌦", 0x0B: "↩", 0x0C: "↩", 0x0D: "↩",
    0x17: "⌫", 0x1B: "⎋", 0x1C: "⌧", 0x62: "⇞", 0x63: "⇪", 0x64: "←", 0x65: "→", 0x66: "↖",
    0x67: "Help", 0x68: "↑", 0x69: "↘", 0x6A: "↓", 0x6B: "⇟", 0x6D: "ContextMenu",
    0x6E: "Power", 0x8C: "⏏",
]
for (offset, code) in (0x6F...0x7A).enumerated() { glyphs[code] = "F\(offset + 1)" }
for (offset, code) in (0x87...0x89).enumerated() { glyphs[code] = "F\(offset + 13)" }
for (offset, code) in (0x8F...0x92).enumerated() { glyphs[code] = "F\(offset + 16)" }

// 取值见 AppKit 的 NSEvent.h（NS*FunctionKey）与 NSText.h（NS*Character）。
var keyChars: [UInt32: String] = [
    0x03: "⌤", 0x08: "⌫", 0x09: "⇥", 0x0D: "↩", 0x19: "⇤", 0x1B: "⎋", 0x20: "␣", 0x7F: "⌫",
    0xF700: "↑", 0xF701: "↓", 0xF702: "←", 0xF703: "→", 0xF728: "⌦", 0xF729: "↖",
    0xF72B: "↘", 0xF72C: "⇞", 0xF72D: "⇟",
]
for code in UInt32(0xF704)...0xF726 { keyChars[code] = "F\(code - 0xF703)" }

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

struct Attributes {
    var values: [String: CFTypeRef] = [:]
    var unreadable: [String: Int32] = [:]

    func string(_ name: String) -> String? {
        guard let value = values[name], CFGetTypeID(value) == CFStringGetTypeID() else { return nil }
        let text = value as! String
        return text.isEmpty ? nil : text
    }

    func number(_ name: String) -> NSNumber? {
        guard let value = values[name] else { return nil }
        let type = CFGetTypeID(value)
        return type == CFNumberGetTypeID() || type == CFBooleanGetTypeID() ? (value as! NSNumber) : nil
    }

    func axValue(_ name: String) -> AXValue? {
        guard let value = values[name], CFGetTypeID(value) == AXValueGetTypeID() else { return nil }
        return (value as! AXValue)
    }

    var role: String { string("AXRole") ?? "AXUnknown" }
    var label: String? { string("AXTitle") ?? string("AXDescription") }

    var children: [AXUIElement] {
        guard let value = values["AXChildren"], CFGetTypeID(value) == CFArrayGetTypeID() else { return [] }
        return (value as! NSArray).compactMap { item in
            CFGetTypeID(item as CFTypeRef) == AXUIElementGetTypeID() ? (item as! AXUIElement) : nil
        }
    }

    var frame: CGRect? {
        guard let position = axValue("AXPosition"), let extent = axValue("AXSize") else { return nil }
        var origin = CGPoint.zero, size = CGSize.zero
        guard AXValueGetValue(position, .cgPoint, &origin), AXValueGetValue(extent, .cgSize, &size) else {
            return nil
        }
        return CGRect(origin: origin, size: size)
    }

    var shortcut: String? {
        let key: String
        if let char = string("AXMenuItemCmdChar") {
            key = char.unicodeScalars.map { scalar in
                if let name = keyChars[scalar.value] { return name }
                if scalar.properties.generalCategory == .control
                    || scalar.properties.generalCategory == .privateUse {
                    return String(format: "U+%04X", scalar.value)
                }
                return String(scalar)
            }.joined()
        } else if let glyph = number("AXMenuItemCmdGlyph")?.intValue, glyph != 0 {
            key = glyphs[glyph] ?? String(format: "glyph:0x%02X", glyph)
        } else if let virtualKey = number("AXMenuItemCmdVirtualKey")?.intValue {
            key = "key:\(virtualKey)"
        } else {
            return nil
        }
        // 取值见 AXAttributeConstants.h 的 kAXMenuItemModifier*；0 表示只有 ⌘。
        let modifiers = number("AXMenuItemCmdModifiers")?.intValue ?? 0
        return (modifiers & 4 != 0 ? "⌃" : "") + (modifiers & 2 != 0 ? "⌥" : "")
            + (modifiers & 1 != 0 ? "⇧" : "") + (modifiers & 8 == 0 ? "⌘" : "") + key
    }
}

func read(_ element: AXUIElement, _ location: String) -> Attributes {
    var raw: CFArray?
    let error = AXUIElementCopyMultipleAttributeValues(
        element, attributeNames as CFArray, AXCopyMultipleAttributeOptions(rawValue: 0), &raw)
    guard error == .success, let array = raw as? [CFTypeRef] else {
        fail("读取 \(location) 的属性失败：AXError \(error.rawValue)")
    }
    var attributes = Attributes()
    for (name, value) in zip(attributeNames, array) {
        if CFGetTypeID(value) == AXValueGetTypeID(), AXValueGetType(value as! AXValue) == .axError {
            var code: Int32 = 0
            AXValueGetValue(value as! AXValue, .axError, &code)
            if !ignoredErrors.contains(where: { $0.rawValue == code }) {
                attributes.unreadable[name] = code
            }
            continue
        }
        attributes.values[name] = value
    }
    return attributes
}

func actions(_ element: AXUIElement) -> (names: [String], error: Int32?) {
    var names: CFArray?
    let error = AXUIElementCopyActionNames(element, &names)
    if ignoredErrors.contains(error) { return ([], nil) }
    guard error == .success else { return ([], error.rawValue) }
    return ((names as? [String]) ?? [], nil)
}

func truncated(_ text: String) -> String {
    text.count <= valueLimit ? text : String(text.prefix(valueLimit)) + "…（共 \(text.count) 字符）"
}

func jsonValue(_ value: CFTypeRef) -> Any {
    let type = CFGetTypeID(value)
    switch type {
    case CFStringGetTypeID(): return truncated(value as! String)
    case CFBooleanGetTypeID(): return CFBooleanGetValue((value as! CFBoolean))
    case CFNumberGetTypeID(): return value as! NSNumber
    case CFAttributedStringGetTypeID(): return truncated((value as! NSAttributedString).string)
    case CFURLGetTypeID(): return (value as! URL).absoluteString
    case CFArrayGetTypeID(): return "<array \((value as! NSArray).count)>"
    case AXUIElementGetTypeID(): return "<element>"
    case AXValueGetTypeID():
        let axValue = value as! AXValue
        switch AXValueGetType(axValue) {
        case .cgPoint:
            var point = CGPoint.zero
            AXValueGetValue(axValue, .cgPoint, &point)
            return "{\(point.x), \(point.y)}"
        case .cgSize:
            var size = CGSize.zero
            AXValueGetValue(axValue, .cgSize, &size)
            return "{\(size.width), \(size.height)}"
        case .cgRect:
            var rect = CGRect.zero
            AXValueGetValue(axValue, .cgRect, &rect)
            return "{\(rect.origin.x), \(rect.origin.y), \(rect.width), \(rect.height)}"
        case .cfRange:
            var range = CFRange()
            AXValueGetValue(axValue, .cfRange, &range)
            return "{location \(range.location), length \(range.length)}"
        default: return "<AXValue>"
        }
    default: return "<\(CFCopyTypeIDDescription(type) as String)>"
    }
}

func escapeLabel(_ label: String) -> String {
    label.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "]", with: "\\]")
        .replacingOccurrences(of: "\n", with: "\\n").replacingOccurrences(of: "\t", with: "\\t")
}

// 同一父元素下 role 与标签都相同的兄弟才加序号；没有标签的按 role 比较。
func segments(_ items: [(AXUIElement, Attributes)]) -> [String] {
    var totals: [String: Int] = [:]
    let keys = items.map { item -> String in
        let role = String(item.1.role.dropFirst(item.1.role.hasPrefix("AX") ? 2 : 0))
        return item.1.label.map { "\(role)[\(escapeLabel($0))]" } ?? role
    }
    for key in keys { totals[key, default: 0] += 1 }
    var seen: [String: Int] = [:]
    return keys.map { key in
        seen[key, default: 0] += 1
        return totals[key] == 1 ? key : "\(key)#\(seen[key]!)"
    }
}

func splitPath(_ path: String) -> [String] {
    let chars = Array(path)
    var parts: [String] = [], current = "", inLabel = false, escaped = false, index = 0
    while index < chars.count {
        let char = chars[index]
        if escaped {
            escaped = false
        } else if inLabel && char == "\\" {
            escaped = true
        } else if char == "[" || char == "]" {
            inLabel = char == "["
        } else if !inLabel && char == " " && index + 2 < chars.count
                    && chars[index + 1] == ">" && chars[index + 2] == " " {
            parts.append(current)
            current = ""
            index += 3
            continue
        }
        current.append(char)
        index += 1
    }
    parts.append(current)
    return parts
}

// 菜单项与它的 AXMenu 子元素合并成一层，路径直接写到菜单项。
func children(of attributes: Attributes, _ location: String) -> [(AXUIElement, Attributes)] {
    var result: [(AXUIElement, Attributes)] = []
    for child in attributes.children {
        let childAttributes = read(child, location + " 的子元素")
        if ["AXMenuBarItem", "AXMenuItem"].contains(attributes.role) && childAttributes.role == "AXMenu" {
            result += childAttributes.children.map { ($0, read($0, location + " 的菜单项")) }
        } else {
            result.append((child, childAttributes))
        }
    }
    return result
}

func roots(_ app: AXUIElement) -> [(AXUIElement, Attributes)] {
    var elements = read(app, "App").children
    for name in ["AXWindows", "AXExtrasMenuBar"] {
        var value: CFTypeRef?
        let error = AXUIElementCopyAttributeValue(app, name as CFString, &value)
        if ignoredErrors.contains(error) { continue }
        guard error == .success, let value else { fail("读取 App 的 \(name) 失败：AXError \(error.rawValue)") }
        let extra = CFGetTypeID(value) == CFArrayGetTypeID()
            ? (value as! NSArray).map { $0 as! AXUIElement } : [value as! AXUIElement]
        elements += extra.filter { item in !elements.contains { CFEqual($0, item) } }
    }
    return elements.map { ($0, read($0, "App 的顶层元素")) }
}

func resolve(_ app: AXUIElement, _ path: String) -> (element: AXUIElement, attributes: Attributes) {
    var candidates = roots(app)
    var current: (AXUIElement, Attributes)?
    var resolved: [String] = []
    for segment in splitPath(path) {
        let names = segments(candidates)
        guard let index = names.firstIndex(of: segment) else {
            fail("找不到 \(segment)（已匹配：\(resolved.joined(separator: " > "))）。这一层可选：\n"
                 + names.joined(separator: "\n"))
        }
        current = candidates[index]
        resolved.append(segment)
        candidates = children(of: candidates[index].1, resolved.joined(separator: " > "))
    }
    guard let current else { fail("路径为空") }
    return current
}

struct Options {
    var bundleID = "", pid: pid_t?, root: String?, path: String?, action = "AXPress"
    var maxDepth = Int.max, maxNodes = 20000, out: String?, flat: String?, frames = true
}

final class Dumper {
    let options: Options
    var count = 0
    var lines: [String] = []

    init(_ options: Options) { self.options = options }

    func node(_ element: AXUIElement, _ attributes: Attributes, _ path: String,
              _ depth: Int, _ windowOrigin: CGPoint?) -> [String: Any] {
        count += 1
        if count > options.maxNodes {
            fail("元素超过 \(options.maxNodes) 个；用 --root 缩小范围，或调大 --max-depth/--max-nodes 的限制")
        }
        let role = attributes.role
        var result: [String: Any] = ["path": path, "role": role]
        for (key, name) in [("subrole", "AXSubrole"), ("title", "AXTitle"), ("description", "AXDescription"),
                            ("identifier", "AXIdentifier"), ("help", "AXHelp"), ("mark", "AXMenuItemMarkChar")] {
            if let text = attributes.string(name) { result[key] = text }
        }
        for (key, name) in [("enabled", "AXEnabled"), ("focused", "AXFocused"), ("selected", "AXSelected")] {
            if let flag = attributes.number(name) { result[key] = flag.boolValue }
        }
        if let value = attributes.values["AXValue"] { result["value"] = jsonValue(value) }
        if let shortcut = attributes.shortcut { result["shortcut"] = shortcut }
        let available = actions(element)
        if !available.names.isEmpty { result["actions"] = available.names }
        var unreadable = attributes.unreadable
        if let error = available.error { unreadable["actions"] = error }
        if !unreadable.isEmpty { result["unreadable"] = unreadable }

        var origin = windowOrigin
        if role == "AXWindow" && origin == nil { origin = attributes.frame?.origin }
        if options.frames, let origin, !menuRoles.contains(role), let frame = attributes.frame {
            let base = role == "AXWindow" && windowOrigin == nil ? CGPoint.zero : origin
            result["frame"] = [frame.minX - base.x, frame.minY - base.y, frame.width, frame.height]
                .map { Int($0.rounded()) }
        }
        lines.append(flatLine(result))

        if depth >= options.maxDepth {
            if !attributes.children.isEmpty { result["truncated"] = true }
            return result
        }
        let items = children(of: attributes, path)
        let names = segments(items)
        result["children"] = zip(names, items).map { name, item in
            node(item.0, item.1, path + " > " + name, depth + 1, origin)
        }
        return result
    }

    func flatLine(_ node: [String: Any]) -> String {
        var fields = [node["path"] as! String]
        if let shortcut = node["shortcut"] { fields.append("shortcut=\(shortcut)") }
        if let mark = node["mark"] { fields.append("mark=\(mark)") }
        if node["enabled"] as? Bool == false { fields.append("disabled") }
        if node["selected"] as? Bool == true { fields.append("selected") }
        if node["focused"] as? Bool == true { fields.append("focused") }
        if let subrole = node["subrole"] { fields.append("subrole=\(subrole)") }
        if let description = node["description"], node["title"] != nil { fields.append("desc=\(description)") }
        if let help = node["help"] as? String { fields.append("help=\(encoded(help))") }
        if let value = node["value"] { fields.append("value=\(encoded(value))") }
        if let frame = node["frame"] as? [Int] { fields.append("frame=" + frame.map(String.init).joined(separator: ",")) }
        if let unreadable = node["unreadable"] as? [String: Int32] {
            fields.append("unreadable=" + unreadable.keys.sorted().joined(separator: ","))
        }
        return fields.joined(separator: "\t")
    }

    func encoded(_ value: Any) -> String {
        let data = try! JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed, .withoutEscapingSlashes])
        return String(decoding: data, as: UTF8.self)
    }
}

func runningApp(_ options: Options) -> NSRunningApplication {
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: options.bundleID)
    if let pid = options.pid {
        guard let app = apps.first(where: { $0.processIdentifier == pid }) else {
            fail("\(options.bundleID) 没有 pid 为 \(pid) 的运行实例")
        }
        return app
    }
    guard !apps.isEmpty else { fail("\(options.bundleID) 没有运行；先启动 App") }
    guard apps.count == 1 else {
        fail("\(options.bundleID) 有多个运行实例，用 --pid 指定：" + apps.map { "\($0.processIdentifier)" }.joined(separator: ", "))
    }
    return apps[0]
}

func requireTrust() {
    guard AXIsProcessTrusted() else {
        fail("当前进程没有辅助功能权限。请在「系统设置 → 隐私与安全性 → 辅助功能」中允许运行本命令的 App（如 Codex 或终端），然后重试。")
    }
}

func parse(_ arguments: [String], positional count: Int) -> Options {
    var options = Options(), positional: [String] = [], index = 0
    func next() -> String {
        index += 1
        guard index < arguments.count else { fail("\(arguments[index - 1]) 缺少参数值\n\n" + usage) }
        return arguments[index]
    }
    func integer() -> Int {
        let flag = arguments[index], text = next()
        guard let value = Int(text), value >= 0 else { fail("\(flag) 需要非负整数：\(text)") }
        return value
    }
    while index < arguments.count {
        switch arguments[index] {
        case "--pid": options.pid = pid_t(integer())
        case "--root": options.root = next()
        case "--action": options.action = next()
        case "--max-depth": options.maxDepth = integer()
        case "--max-nodes": options.maxNodes = integer()
        case "--out": options.out = next()
        case "--flat": options.flat = next()
        case "--no-frames": options.frames = false
        case let flag where flag.hasPrefix("--"): fail("未知选项 \(flag)\n\n" + usage)
        case let value: positional.append(value)
        }
        index += 1
    }
    guard positional.count == count else { fail(usage) }
    options.bundleID = positional[0]
    if count > 1 { options.path = positional[1] }
    return options
}

func write(_ text: String, to path: String) {
    let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
    try! FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try! text.write(to: url, atomically: true, encoding: .utf8)
}

func dump(_ options: Options) {
    requireTrust()
    let running = runningApp(options)
    let app = AXUIElementCreateApplication(running.processIdentifier)
    AXUIElementSetMessagingTimeout(app, 5)
    let dumper = Dumper(options)
    let tree: [[String: Any]]
    if let rootPath = options.root {
        let root = resolve(app, rootPath)
        var origin: CGPoint?
        let parts = splitPath(rootPath)
        if parts.count > 1 {
            let top = resolve(app, parts[0]).attributes
            if top.role == "AXWindow" { origin = top.frame?.origin }
        }
        tree = [dumper.node(root.element, root.attributes, rootPath, 0, origin)]
    } else {
        let items = roots(app)
        tree = zip(segments(items), items).map { dumper.node($0.1.0, $0.1.1, $0.0, 0, nil) }
    }
    let report: [String: Any] = [
        "bundle_id": options.bundleID, "pid": Int(running.processIdentifier),
        "app_path": (running.bundleURL?.path).map { $0 as Any } ?? NSNull(),
        "root": options.root.map { $0 as Any } ?? NSNull(),
        "frames": options.frames ? "窗口为屏幕坐标，窗口内元素相对所在窗口左上角" : "未记录",
        "node_count": dumper.count, "roots": tree,
    ]
    let flat = dumper.lines.joined(separator: "\n") + "\n"
    if let out = options.out {
        let data = try! JSONSerialization.data(withJSONObject: report,
                                               options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
        write(String(decoding: data, as: UTF8.self) + "\n", to: out)
    }
    if let path = options.flat { write(flat, to: path) }
    if options.out == nil && options.flat == nil { print(flat, terminator: "") }
}

func perform(_ options: Options) {
    requireTrust()
    let running = runningApp(options)
    let app = AXUIElementCreateApplication(running.processIdentifier)
    AXUIElementSetMessagingTimeout(app, 5)
    let target = resolve(app, options.path!)
    let available = actions(target.element)
    if let error = available.error { fail("读取 \(options.path!) 的动作失败：AXError \(error)") }
    guard available.names.contains(options.action) else {
        fail("\(options.path!) 不支持 \(options.action)；可用动作：\(available.names.joined(separator: ", "))")
    }
    let error = AXUIElementPerformAction(target.element, options.action as CFString)
    guard error == .success else { fail("执行 \(options.action) 失败：AXError \(error.rawValue)") }
    print("\(options.action)\t\(options.path!)")
}

let arguments = Array(CommandLine.arguments.dropFirst())
switch arguments.first {
case "check":
    let prompt = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    if AXIsProcessTrustedWithOptions(prompt) {
        print("trusted")
    } else {
        fail("当前进程没有辅助功能权限，系统已弹出授权提示。授权后重新运行 check。")
    }
case "dump": dump(parse(Array(arguments.dropFirst()), positional: 1))
case "perform": perform(parse(Array(arguments.dropFirst()), positional: 2))
default: fail(usage)
}
