# 项目记录

`replica/` 下保存复刻的全部记录，由 `init_project.py` 创建：

- `feature-ledger.json`：原版与 macOS 版本、入口清单、功能清单。
- `scenarios.json`：对照场景；`scenarios/` 存放 `script` 场景的脚本。
- `progress.md`：当前阶段、下一步、构建命令、等待用户处理的事项，以及按时间追加的记录。
- `evidence/`：`bundle/`（包内容）、`ax/`（AX 树）、`state/`（状态快照与差分）、截图、输出文件和测试输入。
- `bin/ax`：由 `ax.swift` 编译，已被 `replica/.gitignore` 忽略。

证据中的 `path` 相对 `replica/`。原版截图和测试输入只放在项目里。

## 元素路径

`ax dump` 输出的每一行以元素路径开头，例如 `MenuBar > MenuBarItem[文件] > MenuItem[导出为 PDF…]`、`Window[未命名] > Toolbar > Button[分享]`。路径由 ` > ` 连接的段组成，段写作 `Role[标签]`（标签取 AXTitle，没有时取 AXDescription）或 `Role`，同一父元素下有重复时追加 `#序号`。菜单项与它的子菜单合并为一层。同一路径可以原样传给 `ax perform` 和 `ax dump --root`。

## 入口清单

`inventory` 中每一项是原版的一个入口，指向一个功能，或用 `skip` 写明不单独实现的原因，二者选一：

```json
{"kind": "menu", "path": "MenuBar > MenuBarItem[文件] > MenuItem[导出为 PDF…]", "feature": "F-001"}
{"kind": "shortcut", "path": "⌥⌘E", "feature": "F-001"}
{"kind": "menu", "path": "MenuBar > MenuBarItem[App 名] > MenuItem[服务]", "skip": "系统提供的服务子菜单"}
```

AX 树里能找到的入口，`path` 用元素路径；Dock 菜单、自绘区域等 AX 树读不到的入口，用能定位它的描述，如 `Dock 菜单 > 新建窗口`。

`kind` 取值：

- `menu`：菜单栏中的菜单项
- `context_menu`：右键菜单
- `toolbar`：工具栏与标题栏按钮
- `window`：窗口内的控件，如按钮、列表、编辑区、侧边栏
- `settings`：设置中的选项
- `shortcut`：快捷键，包括没有菜单项的快捷键
- `document_type`：可以打开、导入或导出的文件类型
- `url_scheme`：URL scheme
- `service`：本 App 提供的系统服务
- `applescript`：AppleScript 命令
- `app_intent`：快捷指令动作
- `drag_drop`：拖放目标与拖出内容
- `dock_menu`：Dock 图标菜单
- `menu_bar_extra`：菜单栏图标
- `extension`：共享、Quick Look、Finder 等扩展
- `notification`：通知
- `lifecycle`：启动、退出、窗口与状态恢复、登录时启动

每个类别要么至少有一个指向功能的入口，要么在 `absent_entry_kinds` 写明不存在的依据，例如 `"service": "bundle.json 的 entries.services 为空，服务菜单中也没有本 App 的条目"`。只有 `skip` 项的类别同样需要写依据。

## 功能

一个功能是一个可以独立验证的用户操作及其结果，如「导出为 PDF」「切换侧边栏」「修改自动保存间隔」。

- 同一操作的多个入口（菜单、快捷键、工具栏按钮）指向同一个功能。
- 同一入口在不同前置状态下结果不同（如未选中内容时菜单项禁用），写成 `expected` 中的分支，用不同场景验证。
- 设置中每个影响行为的选项各算一个功能。纯展示的界面元素归入使用它的功能。

```json
{
  "id": "F-001",
  "name": "导出为 PDF",
  "preconditions": ["已打开文档"],
  "expected": ["弹出保存面板，默认文件名为文档名", "无文档时菜单项禁用"],
  "persistence": "偏好 key LastExportDirectory 记住上次导出目录",
  "evidence": [
    {"kind": "ax", "path": "evidence/ax/no-document.txt", "note": "无文档时菜单项 disabled，快捷键 ⌥⌘E"},
    {"kind": "state", "path": "evidence/state/F-001-before--F-001-after.json", "note": "导出后写入 LastExportDirectory"},
    {"kind": "rea", "note": "Evidence ev_…：导出默认页边距 72pt"}
  ],
  "status": "observed",
  "blocker": null
}
```

`evidence[].kind` 取值，`note` 都必填：

- `ax`：`ax dump` 的输出，`path` 必填
- `state`：`state_diff.py` 的快照或差分，`path` 必填
- `gui`：Computer Use 截图
- `file`：原版输出的文件
- `log`：运行日志
- `bundle`：`bundle_scan.py` 的输出，`path` 必填
- `rea`：REA 结论，`note` 中写 Evidence ID
- `doc`：外部资料，填 `url` 或 `path`
- `user`：用户提供的信息

`status` 依次推进：

- `hypothesis`：只有包内容、REA、文案或外部资料，尚未在运行的原版上确认。
- `observed`：已在运行的原版上确认，至少有一条 `ax`、`state`、`gui`、`file`、`log` 或 `user` 证据，写明 `expected`。
- `implemented`：复刻版已连通真实逻辑。
- `passed`：至少一个关联场景通过，且没有失败的关联场景。
- `blocked`：`blocker` 写成 `{"kind": "...", "detail": "..."}`，`kind` 取 `account`（账号）、`server`（原厂服务端）、`hardware`（硬件）、`license`（付费许可）、`entitlement`（Apple 限定的 entitlement）、`user`（用户明确排除）。

非 `blocked` 时 `blocker` 为 `null`。保留旧 ID 和证据，未完成的分支留在 `expected` 里。

## 场景

```json
{
  "id": "S-001",
  "features": ["F-001"],
  "kind": "script",
  "script": "scenarios/S-001.sh",
  "fixtures": ["evidence/fixtures/sample.md"],
  "start_state": "打开 sample.md，导出目录为空",
  "steps": ["选择 文件 > 导出为 PDF…", "保存到导出目录"],
  "checks": ["文件菜单各项的启用状态", "导出文件页数与页边距"],
  "original": {"result": null, "evidence": []},
  "replica": {"result": null, "evidence": []},
  "differences": [],
  "status": "pending",
  "blocker": null
}
```

`kind` 取值：

- `script`：可重放的脚本，比较两边输出的 AX 树、文件和状态差分。
- `gui`：视觉布局、动效、拖放等需要看画面的检查，用 Computer Use 操作并截图。
- `automated`：复刻版的自动化测试，覆盖文件格式、算法和持久化。

`status` 取 `pending / passed / failed / blocked`，`blocker` 规则同功能。

### script 场景

`script` 是相对 `replica/` 的可执行文件，调用方式为 `scenarios/S-001.sh BUNDLE_ID OUT_DIR`，原版输出到 `evidence/S-001/original/`，复刻版输出到 `evidence/S-001/replica/`：

- 从 `start_state` 开始：在 `OUT_DIR` 下准备隔离目录和 fixtures 的副本，用 `open -b "$1"` 启动 App 或打开文件。
- 菜单和控件动作用 `"$(dirname "$0")/../bin/ax" perform "$1" <元素路径>`；打开菜单、窗口或面板后先 `sleep 1` 等界面稳定再导出，否则可能读到正在重建的元素（AXError -25202）。键盘输入先激活 App，再用 `osascript` 调 System Events 的 `keystroke`。
- 把观测结果写进 `OUT_DIR`：相关窗口或菜单的 `ax dump --flat`（比较结构时加 `--no-frames`）、输出文件。状态变化在运行脚本前后用 `state_diff.py` 记录。
- 用 `diff -ru` 比较两边的输出目录；bundle identifier、App 名等预期不同的内容在 `checks` 中说明。

### 比较要求

- 相同输入分别放入两边的隔离目录，比较内容、命名、顺序、窗口、提示、保存与恢复行为。
- `gui` 场景两边都存截图，按 `S-001-original.png`、`S-001-replica.png` 命名并写进各自的 `evidence`。两边使用同一系统外观（浅色或深色）和语言，复刻版默认窗口尺寸与原版一致。逐项比较布局、控件类型、文案、图标、间距、启用状态和焦点。
- 通过的场景两边都有 `result`，`differences` 为空，`script` 和 `gui` 场景两边各有存在的证据文件；失败的场景写明差异。修复前保留复现，修改后重跑该场景和直接受影响的场景。

## 检查

开发中随时运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR`，检查格式、证据文件、入口与功能、场景与功能的关联。输出中的 `entry_kinds.unchecked` 是既没有入口也没有不存在依据的类别。

交付前加 `--final`：每个功能为 `passed` 或 `blocked`，每个场景为 `passed` 或 `blocked`，`unchecked` 为空。
