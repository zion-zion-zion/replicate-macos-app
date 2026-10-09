---
name: replicate-macos-app
description: Replicate an installed closed-source macOS app as an independently written native app. Explore the original through its bundle, Accessibility tree, on-disk state, REA MCP and Computer Use, rebuild it with the Build macOS Apps plugin skills, and verify both apps side by side with replayable scenarios. Use for macOS App 复刻、全功能复刻、clone or rebuild of an existing Mac app, including setup-only requests that install these tools for this workflow. Requires local macOS.
---

# macOS App 复刻

探索原版时，信息来源按成本从低到高使用：能读成结构化数据的直接读，视觉和交互留给 Computer Use。

- **包内容**：`scripts/bundle_scan.py` 读取技术栈、Info.plist 声明的入口、entitlements、本地化文案、nib、资源目录、数据模型、内置数据库、帮助文档和更新源。
- **AX 树**：`ax`（项目里的 `replica/bin/ax`，由 `scripts/ax.swift` 编译，不带参数运行显示用法）导出运行中 App 的菜单栏、菜单栏图标、窗口和右键菜单，每个元素带 role、标题、快捷键、勾选与启用状态和尺寸，也能按元素路径执行动作。
- **状态差分**：`scripts/state_diff.py` 在操作前后给偏好设置、容器、Application Support、缓存和窗口恢复状态拍快照并比较。
- **REA MCP**：需要读代码的问题：字符串和交叉引用、反编译、nib 内容、Electron 的 JS，以及用 `observe_native_calls` 记录运行时调用。调用方法按 `reverse-engineer-anything` Skill，以当前会话的工具列表为准。
- **外部资料**：官网、帮助文档、App Store 描述、更新说明。
- **Computer Use**：视觉布局、动效、拖放、AX 树读不到内容的自绘区域，以及 `gui` 场景的并排截图。调用方式以当前会话 Computer Use 插件的说明为准；用 bundle identifier 指定目标 App，两边同名时也不会操作错对象。
- **Build macOS Apps** 插件的 Skills（`build-macos-apps:*`）负责建工程、实现、构建运行、调试和测试。

复刻范围是原版的全部功能。用户提供目标 App、体验交付版本并指出差异；清点、调查、实现和验证由你自主完成，范围内的功能直接做。

把本 Skill 的目录记作 `SKILL_DIR`，用绝对路径运行脚本。项目记录、证据和场景的格式见 [references/ledger.md](references/ledger.md)。

## 1. 开始

1. 确定目标 App 和项目目录。目标未知时只询问 App 名称或路径，并解析为本机唯一的 `.app` 路径。用户未指定项目目录时，当前工作目录为空或已有 `replica/` 就直接使用，否则询问一次。项目根目录与 Codex 工作目录一致时，`build-run-debug` 生成的 Run 按钮才会生效。
2. 运行 `python3 "$SKILL_DIR/scripts/init_project.py" PROJECT_DIR --app-path APP_PATH`，在 `replica/` 下创建功能清单、场景、进度文件和证据目录，并编译 `replica/bin/ax`；已有文件保持不变。项目已有记录时，先读 `replica/progress.md`、功能清单和场景，从记录的下一步继续。
3. 在当前会话实际调用各工具：用 Computer Use 获取原版窗口状态，用 REA 打开原版 `.app`，启动原版后运行 `ax dump BUNDLE_ID --root MenuBar` 得到菜单项，确认技能列表中有 `build-macos-apps:build-run-debug`。都可用就进入第 2 节；有缺失时按 [references/setup.md](references/setup.md) 安装或授权，完成后回到这一步重新确认。

用户只要求安装准备时，跳过本节第 1、2 步，按 setup.md 安装，再完成第 3 步的确认（目标 App 未指定时，Computer Use 用任一已打开的 App 确认，辅助功能权限用 `swift "$SKILL_DIR/scripts/ax.swift" check` 确认），报告已就绪项和仍需用户操作的项后停止。

## 2. 清点入口

先求全，再求深：把原版的每一个入口登记进 `inventory`，再逐个功能深入。

1. **包内容**：运行 `python3 "$SKILL_DIR/scripts/bundle_scan.py" PROJECT_DIR`，结果写入 `replica/evidence/bundle/`。
   - `stack.tags` 含 `electron` 时，用 REA 的 `analyze_javascript_application` 分析输出中的 `electron_app`，菜单、窗口和功能逻辑以代码为准。
   - 从 `entries` 登记文档类型、导入导出类型、URL scheme、系统服务、AppleScript 命令、App Intents、扩展、XPC 服务和登录项；`usage_descriptions` 指向需要系统权限的功能。
2. **AX 树**：启动原版，运行 `ax dump BUNDLE_ID --out replica/evidence/ax/<状态>.json --flat replica/evidence/ax/<状态>.txt`。菜单栏、菜单栏图标（`ExtrasMenuBar`）、工具栏和窗口控件按输出逐行登记，`path` 用输出中的元素路径，带快捷键的项另登记一条 `shortcut`。再用 `ax perform` 打开每个设置面板和自定义工具栏面板；对各主要区域执行 `--action AXShowMenu` 打开右键菜单，菜单出现在该元素下的 `Menu`，导出后对它执行 `AXCancel` 关闭。每进入一个新状态，等界面稳定后导出一次。
3. **Computer Use**：补登 AX 树读不到的入口：Dock 菜单、自绘区域里的控件、拖放目标、只能通过手势到达的界面。
4. **文案与资料**：通读 `strings.json`、帮助页（`help_book.pages`）、官网、App Store 描述和更新说明（`update_feed`）。其中提到的每个功能、设置、对话框和错误提示，都要在清单中对应到入口或功能的 `expected` 分支；对应不上的，按文案回到原版找到入口后补登。文案表为空时（gettext 的 `.mo`、Qt 的 `.qm`、写在代码里的文案），用 REA 搜索字符串。
5. 由系统提供、复刻版从框架默认获得的标准项（如「服务」子菜单、「隐藏其他」）登记为 `skip` 并写原因。

完成标志：`python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR` 输出的 `entry_kinds.unchecked` 为空，文案与资料中提到的功能都能在清单中找到入口。

然后把入口归并为功能：同一操作的多个入口指向同一个功能 ID。

## 3. 逐个功能：观察、重建、对照

先做主流程（打开或新建、编辑、保存），再按菜单顺序推进。每个功能（或同一区域的一小组功能）走完下面三步，再进入下一个。

1. **观察**：在原版上实测，使用测试文件和隔离目录，覆盖不同前置状态、禁用状态、错误提示和重启后的恢复。
   - 操作前后各运行一次 `python3 "$SKILL_DIR/scripts/state_diff.py" snapshot PROJECT_DIR <名称> --path <隔离目录>`，再用 `state_diff.py diff PROJECT_DIR <前> <后>` 得到偏好 key 与默认值、写入的文件、plist 键值和数据库行数的变化。
   - 操作后用 `ax dump BUNDLE_ID --root <窗口或面板路径>` 记录启用、勾选、文案和布局。
   - 运行日志用 `log stream --predicate 'process == "<identity.executable>"'` 观察。
   - 文件格式、算法、默认值和隐藏设置从具体问题出发交给 REA；静态分析回答不了的调用顺序用 `observe_native_calls`。
   - 视觉细节、动效和拖放用 Computer Use 观察并截图。

   写下 `expected` 和证据，状态改为 `observed`。
2. **重建**：按 Build macOS Apps 的 Skills 实现。第一次实现前，用 `swiftpm-macos`（或沿用已有 Xcode 工程）建立工程，用 `build-run-debug` 建立 `script/build_and_run.sh` 和 Run 按钮。界面以 SwiftUI 场景为主，参照 `swiftui-patterns` 和 `window-management`；SwiftUI 达不到原版行为的部分（如复杂表格、文本编辑、菜单项校验）按 `appkit-interop` 用 AppKit 实现。运行日志用 `telemetry`，测试失败用 `test-triage`，沙盒和权限用 `signing-entitlements`。用户指定技术栈时按用户要求。复刻版使用独立的 bundle identifier、配置和数据目录，用自己编写的代码实现观察到的行为。功能完整连通后状态改为 `implemented`。
3. **对照**：为功能写场景。能由 `ax perform`、AppleScript 和命令行驱动的写成 `script` 场景，对原版和复刻版各运行一次，比较两边输出的 AX 树、文件和状态差分；视觉布局、动效和拖放写成 `gui` 场景，用 Computer Use 对两边执行同一组步骤并截图；文件格式、算法和持久化另写 `automated` 测试。场景通过后功能状态改为 `passed`；有差异就写进场景的 `differences`，回到观察或重建。

规则：

- 连通到真实逻辑才算 `implemented`；未连通的按钮、静态假数据和占位实现保持原状态。
- `blocked` 只用于这些原因：账号、原厂服务端、硬件、付费许可、Apple 限定的 entitlement、用户明确排除。阻塞的功能保留条目，继续其他功能。
- 需要用户处理的事项（Computer Use 拿不到画面、脚本报告缺少辅助功能或完全磁盘访问权限）写进 `progress.md` 的等待用户处理，继续不依赖该项的工作；Computer Use 不可用时 `gui` 场景保持 `pending`。
- 每轮观察后把结论写进功能清单，只保留作为证据的输出。切换阶段、完成功能或需要用户操作时更新 `progress.md`。
- 遵守用户给出的操作方式限制。修改原版设置前用 `state_diff.py` 拍快照记下原值，用完恢复。

## 4. 交付

`python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR --final` 没有错误后才报告完成。交付可运行的 `.app`、源码、构建启动命令、清单统计（入口数、功能数、通过数、阻塞项及原因）和尚未解决的差异。用户体验后指出的差异加入清单，修正后重跑相关场景。打包、公证和发布按用户要求执行。
