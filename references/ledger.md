# 项目记录

`replica/` 下保存复刻的全部记录，由 `init_project.py` 创建：

- `feature-ledger.json`：原版与 macOS 版本、入口清单、功能清单。
- `scenarios.json`：对照场景。
- `progress.md`：当前阶段、下一步、构建命令、等待用户处理的事项，以及按时间追加的记录。
- `evidence/`：截图、输出文件和测试输入。

证据中的 `path` 相对 `replica/`。原版截图和测试输入只放在项目里。

## 入口清单

`inventory` 中每一项是原版的一个入口，指向一个功能，或用 `skip` 写明不单独实现的原因，二者选一：

```json
{"kind": "menu", "path": "文件 > 导出为 PDF…", "feature": "F-001"}
{"kind": "shortcut", "path": "⌥⌘E", "feature": "F-001"}
{"kind": "menu", "path": "App 名 > 服务", "skip": "系统提供的服务子菜单"}
```

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

每个类别要么至少有一个指向功能的入口，要么在 `absent_entry_kinds` 写明不存在的依据，例如 `"service": "Info.plist 无 NSServices（REA Evidence ev_…），服务菜单中也没有本 App 的条目"`。只有 `skip` 项的类别同样需要写依据。

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
  "persistence": "记住上次导出目录",
  "evidence": [
    {"kind": "gui", "path": "evidence/F-001-menu.png", "note": "菜单项位置与快捷键"},
    {"kind": "rea", "note": "Evidence ev_…：导出默认页边距 72pt"}
  ],
  "status": "observed",
  "blocker": null
}
```

`evidence[].kind` 取 `gui / file / rea / log / user`，`note` 必填；REA 证据在 `note` 中写 Evidence ID。

`status` 依次推进：

- `hypothesis`：只有 REA 或文案推断，尚未在原版上看到。
- `observed`：已在原版上实测，写明 `expected` 和证据。
- `implemented`：复刻版已连通真实逻辑。
- `passed`：至少一个关联场景通过，且没有失败的关联场景。
- `blocked`：`blocker` 写成 `{"kind": "...", "detail": "..."}`，`kind` 取 `account`（账号）、`server`（原厂服务端）、`hardware`（硬件）、`license`（付费许可）、`entitlement`（Apple 限定的 entitlement）、`user`（用户明确排除）。

非 `blocked` 时 `blocker` 为 `null`。保留旧 ID 和证据，未完成的分支留在 `expected` 里。

## 场景

```json
{
  "id": "S-001",
  "features": ["F-001"],
  "kind": "gui",
  "fixtures": ["evidence/fixtures/sample.md"],
  "start_state": "打开 sample.md，导出目录为空",
  "steps": ["选择 文件 > 导出为 PDF…", "保存到导出目录"],
  "checks": ["保存面板默认文件名", "导出文件页数与页边距"],
  "original": {"result": null, "evidence": []},
  "replica": {"result": null, "evidence": []},
  "differences": [],
  "status": "pending",
  "blocker": null
}
```

`kind` 取 `gui`（界面操作）、`file`（比较输出文件）、`automated`（自动化测试）；`status` 取 `pending / passed / failed / blocked`，`blocker` 规则同功能。

- 相同输入分别放入两边的隔离目录，比较内容、命名、顺序、窗口、提示、保存与恢复行为。
- `gui` 场景两边都存截图，按 `S-001-original.png`、`S-001-replica.png` 命名并写进各自的 `evidence`。两边使用同一系统外观（浅色或深色）和语言，复刻版默认窗口尺寸与原版一致。逐项比较布局、控件类型、文案、图标、间距、启用状态和焦点。
- 通过的场景两边都有 `result`，`differences` 为空；失败的场景写明差异。修复前保留复现，修改后重跑该场景和直接受影响的场景。

## 检查

开发中随时运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR`，检查格式、证据文件、入口与功能、场景与功能的关联。输出中的 `entry_kinds.unchecked` 是既没有入口也没有不存在依据的类别。

交付前加 `--final`：每个功能为 `passed` 或 `blocked`，每个场景为 `passed` 或 `blocked`，`unchecked` 为空。
