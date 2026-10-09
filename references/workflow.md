# 功能证据、场景与复刻验收

## 项目记录

`replica/` 下保存复刻的全部记录：

- `feature-ledger.json`：功能清单，由 `init_project.py` 创建，含原版和 macOS 版本。
- `scenarios.json`：验证场景。
- `progress.md`：进度与续跑入口。
- `evidence/`：截图、输出文件、`bundle.json`、`bundle-strings.json`。

原版截图和测试输入只存入项目证据目录，不混入可分发 Skill。

## App 包盘点

运行 `python3 "$SKILL_DIR/scripts/inspect_bundle.py" APP_PATH PROJECT_DIR/replica/evidence`。`bundle.json` 包含：

- `stack.tags`：技术栈，取值有 `appkit`、`swiftui`、`catalyst`、`electron`、`qt`、`flutter`、`java`、`webkit`、`swift`、`sparkle`。
- `traits`：菜单栏常驻、声明的文档类型与文档类、沙盒、签名。
- `entries`：文档类型、导出与导入的 UTI、URL scheme、系统服务、AppleScript、App Intents、扩展、XPC 服务、`Contents/Library` 下的登录项与插件。
- `usage_descriptions`：原版申请的系统权限，对应需要这些权限的功能。
- `resources`：语言、nib 名称、各字符串表的条数、Electron 的 `app.asar` 路径。

`bundle-strings.json` 是开发语言的全部界面文案，用来发现尚未找到的入口、提示和错误信息，也用来核对复刻版文案。

把 `entries` 中的每一项转成清单条目，`source` 含 `bundle`，在 GUI 中实际观察后再更新调查状态。nib 名称和文案只是线索，需要 GUI 或 REA 证据确认。

### 按 App 类型选择路线

- AppKit（有 `appkit`，没有 `swiftui`）：菜单、nib 名称和字符串表覆盖大部分入口。以 AppKit 为主实现；`traits.document_classes` 非空时使用 NSDocument 架构，保留自动保存、版本浏览、最近文档和标题栏菜单行为。
- SwiftUI（有 `swiftui`）：以 SwiftUI 为主实现，按原版窗口和菜单行为选择 WindowGroup、DocumentGroup、Settings、MenuBarExtra，AppKit 只用于桥接。
- Mac Catalyst（有 `catalyst`）：界面常带 iPad 习惯，如侧边栏、弹出菜单、整页设置。用 SwiftUI + AppKit 实现，保留这些可见的交互方式。
- Electron（有 `electron`）：用 REA 的 JavaScript 应用分析调查 `resources.electron_asar`，找出菜单定义、IPC 通道、存储位置和文件格式；字符串表通常为空，文案来自 GUI 和 asar 调查。用 SwiftUI + AppKit 实现。
- WebView 外壳（有 `webkit`，没有 `swiftui` 和 `electron`，如 Tauri）：界面在网页中，按 GUI 探索和 REA 的资源调查建立清单。用 SwiftUI + AppKit 实现。
- Qt、Flutter、Java（有 `qt`、`flutter` 或 `java`）：文案和资源通常不在 `.lproj` 中，入口主要依靠 GUI 探索和 REA 的字符串、资源调查。用 SwiftUI + AppKit 实现。
- 菜单栏常驻（`traits.menu_bar_agent`）：没有 Dock 图标和主菜单，入口集中在菜单栏图标和弹出窗口；复刻版同样设置 `LSUIElement`。
- 沙盒（`traits.sandboxed`）：文件访问依赖打开面板和安全书签；复刻版按原版 entitlements 决定是否启用沙盒，保持文件访问行为一致。

用户指定技术栈时按用户要求。

## 功能粒度

一个功能是一个可以独立验证的用户操作及其结果，如“导出为 PDF”“切换侧边栏”“修改自动保存间隔”。

- 同一操作的多个入口（菜单、快捷键、工具栏按钮）记在同一功能的 `entries` 里。
- 同一入口在不同前置状态下结果不同（如未选中内容时菜单项禁用），写成该功能 `expected` 中的分支，用不同场景验证。
- 设置中每个影响行为的选项各算一个功能。纯展示、没有交互的界面元素归入使用它的功能。

## 入口类别

`entries[].kind` 取以下值。交付前每一类都要有对应功能，或在清单的 `absent_entry_kinds` 中写明不存在的依据，例如 `"service": "bundle.json 无 NSServices，服务菜单中也没有本 App 的条目"`。

- `menu`：菜单栏中的菜单项
- `context_menu`：右键菜单
- `toolbar`：工具栏与标题栏按钮
- `window`：窗口内的控件，如按钮、列表、编辑区、侧边栏
- `settings`：设置中的选项
- `shortcut`：快捷键，包括没有菜单项的快捷键
- `document_type`：可以打开、导入或导出的文件类型
- `url_scheme`：URL scheme
- `service`：系统服务菜单
- `applescript`：AppleScript 命令
- `app_intent`：快捷指令动作
- `drag_drop`：拖放目标与拖出内容
- `dock_menu`：Dock 图标菜单
- `menu_bar_extra`：菜单栏图标
- `extension`：共享、Quick Look、Finder 等扩展
- `notification`：通知
- `lifecycle`：启动、退出、窗口与状态恢复、登录时启动

## 功能清单格式

```json
{
  "id": "F-001",
  "name": "导出为 PDF",
  "entries": [
    {"kind": "menu", "path": "文件 > 导出为 PDF…"},
    {"kind": "shortcut", "path": "⌥⌘E"}
  ],
  "source": ["gui", "bundle"],
  "input": "当前文档",
  "preconditions": ["已打开文档"],
  "expected": ["弹出保存面板，默认文件名为文档名", "无文档时菜单项禁用"],
  "persistence": "记住上次导出目录",
  "evidence": [{"kind": "gui", "path": "evidence/F-001-menu.png", "note": "菜单项位置与快捷键"}],
  "investigation_status": "observed",
  "implementation_status": "pending",
  "validation_status": "pending",
  "blocker": null
}
```

- `source` 取 `gui / bundle / rea / user`，`evidence[].kind` 取 `gui / file / bundle / rea / log`。`path` 相对 `replica/`，可省略；REA 证据在 `note` 中写明 Evidence ID。
- 调查状态用 `hypothesis / observed / verified / blocked`，实现状态用 `pending / implemented / blocked`，验证状态用 `pending / passed / failed / blocked`。静态推断保持 `hypothesis`，实际观察后改为 `observed`，并写明 `expected` 和证据。
- 任一状态为 `blocked` 时在 `blocker` 写明原因，否则为 `null`。保留旧 ID 和证据，不默默删除未完成分支。

报告已发现、已验证和已阻塞的数量，以清单界定覆盖。

## 场景与差异检查

```json
{
  "id": "S-001",
  "features": ["F-001"],
  "kind": "gui",
  "fixtures": ["fixtures/sample.md"],
  "start_state": "打开 sample.md，导出目录为空",
  "steps": ["选择 文件 > 导出为 PDF…", "保存到导出目录"],
  "checks": ["保存面板默认文件名", "导出文件页数与页边距"],
  "cleanup": "删除导出文件",
  "original": {"result": null, "evidence": []},
  "replica": {"result": null, "evidence": []},
  "differences": [],
  "status": "pending",
  "blocker": null
}
```

`kind` 取 `gui`（界面操作）、`file`（比较输出文件）、`automated`（自动化测试），`status` 取 `pending / passed / failed / blocked`。相同输入分别放入隔离目录，比较内容、命名、顺序、窗口、提示、保存与恢复行为。通过的场景不能有未解决的 `differences`；失败的场景写明差异。

界面对比：Computer Use 返回截图文件时（node_repl 版本中 `get_app_state` 的 `screenshot.url` 是 `file://` URL），把原版和复刻版对应界面的截图复制到 `evidence/`，按 `S-001-original.png`、`S-001-replica.png` 命名，写进场景的 `original.evidence` 和 `replica.evidence`。两边在同一系统外观（浅色或深色）和语言下截取，复刻版的默认窗口尺寸与原版一致。逐项比较布局、控件类型、文案、图标、间距、启用状态和焦点，差异写进 `differences`。`kind` 为 `gui` 的场景通过时，两边都需要截图文件。

修复前保留复现。修改后重跑对应场景及直接受影响的行为。精确文件与算法用程序断言，用户可见行为用 GUI 实测；编译通过不等于行为通过。

## REA 调查

先提出有功能意义的问题，如“冲突文件如何处理”。查对应资源、字符串、符号、事件或格式，保留位置和来源，用自己的代码实现已验证行为。出现系统框架与第三方库时收窄范围。GUI 与资源无法解释时追加深度分析；新发现形成可验证场景。

## 进度与续跑

`progress.md` 由 `init_project.py` 按模板创建。切换阶段、完成一个功能或需要用户操作时，更新“当前阶段”“下一步”“等待用户处理”；建立 `script/build_and_run.sh` 后填写构建命令；场景验证通过后记录 commit 和场景 ID。“记录”一节按时间追加做了什么和结果。

项目还不是 git 仓库时先 `git init`，每完成一个功能提交一次 commit。中断或重启 Codex 后，先读 `progress.md`、功能清单和场景，再从记录的下一步继续。Computer Use 截图占用上下文较多，每轮探索后把观察写进清单，只保留需要作为证据的截图。

## 交付条件

正常可访问功能完成实现和验证；启动本次构建的 `.app`；数据与原版隔离；源码可重复构建；错误和边界已检查；阻塞或差异明确记录；用户无需逐项追加范围内功能。

开发中随时运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR` 检查清单格式、证据文件和场景关联。交付前运行同一命令并加 `--final`，没有错误后才报告完成。
