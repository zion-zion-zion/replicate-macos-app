---
name: replicate-macos-app
description: Replicate an installed closed-source macOS app as an independently written native app. Explore the original with Computer Use and REA MCP, rebuild it with the Build macOS Apps plugin skills, and verify both apps side by side. Use for macOS App 复刻、全功能复刻、clone or rebuild of an existing Mac app, including setup-only requests that install these tools for this workflow. Requires local macOS.
---

# macOS App 复刻

三个工具各管一段：

- **Computer Use** 操作原版和复刻版：清点菜单、窗口、设置和右键菜单，观察行为，截取对照截图。调用方式以当前会话 Computer Use 插件的说明为准；用 bundle identifier 指定目标 App，两边同名时也不会操作错对象。
- **REA MCP** 解释界面看不到的部分：Info.plist 声明的入口、entitlements、资源、文件格式、存储位置和处理逻辑。调用方法按 `reverse-engineer-anything` Skill，以当前会话的工具列表为准。
- **Build macOS Apps** 插件的 Skills（`build-macos-apps:*`）负责建工程、实现、构建运行、调试和测试。

复刻范围是原版的全部功能。用户提供目标 App、体验交付版本并指出差异；清点、调查、实现和验证由你自主完成，范围内的功能直接做。

把本 Skill 的目录记作 `SKILL_DIR`，用绝对路径运行脚本。项目记录的格式和规则见 [references/ledger.md](references/ledger.md)。

## 1. 开始

1. 确定目标 App 和项目目录。目标未知时只询问 App 名称或路径，并解析为本机唯一的 `.app` 路径。用户未指定项目目录时，当前工作目录为空或已有 `replica/` 就直接使用，否则询问一次。项目根目录与 Codex 工作目录一致时，`build-run-debug` 生成的 Run 按钮才会生效。
2. 运行 `python3 "$SKILL_DIR/scripts/init_project.py" PROJECT_DIR --app-path APP_PATH`，在 `replica/` 下创建功能清单、场景、进度文件和证据目录，已有文件保持不变。项目已有记录时，先读 `replica/progress.md`、功能清单和场景，从记录的下一步继续。
3. 在当前会话实际调用三个工具：用 Computer Use 获取原版窗口状态，用 REA 打开原版 `.app`，确认技能列表中有 `build-macos-apps:build-run-debug`。都可用就进入第 2 节；有缺失时按 [references/setup.md](references/setup.md) 安装，完成后回到这一步重新确认。

用户只要求安装准备时，跳过本节第 1、2 步，按 setup.md 安装，再完成第 3 步的确认（目标 App 未指定时，Computer Use 用任一已打开的 App 确认），报告已就绪项和仍需用户操作的项后停止。

## 2. 清点入口

先求全，再求深：把原版的每一个入口登记进 `inventory`，再逐个功能深入。

- **REA**：从 Info.plist、entitlements 和 bundle 结构登记文档类型、导入导出类型、URL scheme、系统服务、AppleScript 命令、App Intents、扩展、XPC 服务和登录项，证据写 Evidence ID。`*UsageDescription` 指向需要系统权限的功能。
- **Computer Use**：逐个打开菜单栏的每个菜单和子菜单，登记每一项及其快捷键；打开设置的每个面板，登记每个影响行为的选项；再登记工具栏按钮（包括自定义工具栏面板里的项）、各主要区域的右键菜单、Dock 菜单、菜单栏图标、拖放目标和窗口内控件。
- 由系统提供、复刻版从框架默认获得的标准项（如「服务」子菜单、「隐藏其他」）登记为 `skip` 并写原因。

完成标志：菜单栏、设置、工具栏和 bundle 声明都已逐项登记，`python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR` 输出的 `entry_kinds.unchecked` 为空。

然后把入口归并为功能：同一操作的多个入口指向同一个功能 ID。

## 3. 逐个功能：观察、重建、对照

先做主流程（打开或新建、编辑、保存），再按菜单顺序推进。每个功能（或同一区域的一小组功能）走完下面三步，再进入下一个。

1. **观察**：用 Computer Use 在原版上实测，使用测试文件和隔离目录，覆盖不同前置状态、禁用状态、错误提示和重启后的恢复。界面解释不了的问题（文件格式、存储位置、默认值、算法、隐藏设置）交给 REA，从具体问题出发查资源、字符串、plist、nib 或代码。写下 `expected` 和证据，状态改为 `observed`。
2. **重建**：按 Build macOS Apps 的 Skills 实现。第一次实现前，用 `swiftpm-macos`（或沿用已有 Xcode 工程）建立工程，用 `build-run-debug` 建立 `script/build_and_run.sh` 和 Run 按钮。界面以 SwiftUI 场景为主，参照 `swiftui-patterns` 和 `window-management`；SwiftUI 达不到原版行为的部分（如复杂表格、文本编辑、菜单项校验）按 `appkit-interop` 用 AppKit 实现。运行日志用 `telemetry`，测试失败用 `test-triage`，沙盒和权限用 `signing-entitlements`。用户指定技术栈时按用户要求。复刻版使用独立的 bundle identifier、配置和数据目录，用自己编写的代码实现观察到的行为。功能完整连通后状态改为 `implemented`。
3. **对照**：为功能写场景，用 Computer Use 对原版和复刻版执行同一组步骤，比较界面、输出文件、状态变化和重启恢复，截图存入 `replica/evidence/`。文件格式、算法和持久化另写自动化测试。场景通过后功能状态改为 `passed`；有差异就写进场景的 `differences`，回到观察或重建。

规则：

- 连通到真实逻辑才算 `implemented`；未连通的按钮、静态假数据和占位实现保持原状态。
- `blocked` 只用于这些原因：账号、原厂服务端、硬件、付费许可、Apple 限定的 entitlement、用户明确排除。阻塞的功能保留条目，继续其他功能。
- Computer Use 拿不到画面（屏幕锁定、权限被撤销）时，在 `progress.md` 写明等待用户处理，继续实现和自动化测试，GUI 场景保持 `pending`。
- 每轮观察后把结论写进功能清单，只保留作为证据的截图。切换阶段、完成功能或需要用户操作时更新 `progress.md`。
- 遵守用户给出的操作方式限制。修改原版设置前记下原值，用完恢复。

## 4. 交付

`python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR --final` 没有错误后才报告完成。交付可运行的 `.app`、源码、构建启动命令、清单统计（入口数、功能数、通过数、阻塞项及原因）和尚未解决的差异。用户体验后指出的差异加入清单，修正后重跑相关场景。打包、公证和发布按用户要求执行。
