---
name: replicate-macos-app
description: Prepare REA MCP and Build macOS Apps skills, then explore, independently implement, and validate the complete functionality of a closed-source macOS app with Codex Computer Use. Use for macOS App 复刻、全功能复刻、组合工具安装准备、REA + Computer Use + Build macOS Apps workflows. Support setup-only requests. Require local macOS execution for installation and desktop exploration.
---

# macOS App 全功能复刻

先完成安装准备，再使用 Computer Use、REA 和原生开发 Skills 尽可能完整地复刻目标 App。让用户提供目标 App、体验可运行版本、指出差异；自主完成能力盘点、调查、实现和验证。不要把范围改成 MVP，也不要逐轮询问是否添加正常功能。

## 0. 安装准备

读取 [references/setup.md](references/setup.md)。把本 Skill 的实际目录记作 `SKILL_DIR`，使用绝对路径运行脚本。安装 Skill 不会执行安装钩子；首次使用时执行本节，以后先检查并复用已就绪的依赖。

1. 确认当前执行环境为目标 App 所在的本地 macOS。环境不符时，说明本地运行要求，继续完成不依赖本地环境的工作。
2. 运行 `python3 "$SKILL_DIR/scripts/bootstrap.py" --check`，检查 macOS、Node.js、npm、git、Swift 工具链及安装记录。Python 尚不可用时先提示准备 Command Line Tools。不要把 Computer Use `unknown` 当成权限失败。
3. 检查当前会话实际可调用的 REA 工具和官方 Build macOS Apps Skills。REA 已连接可用时添加 `--skip-rea`；仅在确认官方开发 Skills 全部可用时添加 `--skip-build-skills`。不要因同名泛用 Skill 存在就认为安装完成。
4. 首次使用或明确的环境准备请求已经授权安装必要依赖。简短说明会配置 Codex 的 REA MCP、安装 REA 工作流和 11 个原生开发 Skills，然后运行 `python3 "$SKILL_DIR/scripts/bootstrap.py" --install`，按上一步添加跳过参数。脚本先生成限定安装计划，再使用官方 setup 应用；只配置 Codex，不扩展到其他客户端。不反复请求确认。
5. 核对每项结果。部分失败时复用成功项，仅修复失败项。不要覆盖用户现有 Skill、删除其他 MCP、自动降级已可用的 REA，或把 setup 成功当成会话已经连接。
6. 一次性列出需用户亲自执行的缺失项：开启 Computer Use 的 server 和 skill 开关；授予系统提示的屏幕录制和辅助功能权限；允许访问目标 App；如新配置尚未加载则重连或重启 Codex。开发工具、登录、许可证只在实际缺失时提示。不要求所有应用权限，不修改 macOS 权限数据库。
7. 调用当前会话真实的 REA 只读工具，并用 Computer Use 获取指定 App 的初始画面。实际输入权限在第一项已授权、可撤销的目标操作中验证。区分“配置已写入”“工具已连接”“App 可操作”。
8. 仅在调查需要原生深度分析且现有 provider 不可用时处理 Hopper/Ghidra。已有 provider 先做针对它的 doctor。安装 Hopper 须有用户明确选择，再加 `--with-hopper`，不要购买许可证。不要把 Hopper Demo 或 doctor 通过当成所有反编译能力均可用。

用户只要求安装准备时，报告已安装项和仍需用户操作的项后停止，不启动复刻。

## 1. 明确目标与证据记录

读取 [references/workflow.md](references/workflow.md)。复用已指定的 App 路径和输出位置；目标未知时只询问 App 名称或路径，先继续环境准备。记录原版版本、构建号、macOS 版本及实际可访问范围。

使用 `scripts/init_project.py PROJECT_DIR --app-path APP_PATH` 初始化 `replica/feature-ledger.json`、`replica/scenarios.json`、`replica/progress.md` 与证据目录。已有记录保持不变。用来源、操作和输出支撑结论，把推断与已观察行为分开。

## 2. 交替探索 Computer Use 和 REA

先做轻量 App bundle 检查，确认类型、资源和版本。随后用 Computer Use 系统探索窗口、菜单、设置、右键、快捷键、拖拽、导入导出、状态恢复与异常输入，形成初始功能清单。

针对未理解的行为或可能遗漏的入口调用 REA，调查相关资源、处理逻辑、格式与持久化。读取当前工具的真实 schema；不假设仓库 main 的新工具存在于安装版本，不请求无目标的全量反编译。

将新发现转成 GUI 验证任务，再用 Computer Use 确认分支、边界和重启行为。持续交替两种工具，直至各入口已检查、候选功能已处理、行为有证据。不要用一次遍历来宣称绝对全量覆盖。

遵守用户已有的操作方式限制。指定仅截图与鼠标键盘时，不用 REA 的 Accessibility Tree 代替探索；macOS 辅助功能权限仍可能是输入控制所必需。操作原版时使用测试文件、隔离目录和可恢复设置。

## 3. 完整实现

根据行为证据独立编写可管理源码。默认使用 SwiftUI + AppKit，保留目标的行为和操作习惯，不强制套用 Liquid Glass 风格。有既定技术栈约束或具体功能需要时调整实现方式。

从当前 Skills 列表读取适用的官方开发 Skills；新安装项尚未显示时，直接读取安装报告给出的 `SKILL.md` 绝对路径。优先使用 `build-run-debug`、`swiftpm-macos`、`swiftui-patterns`、`appkit-interop`、`window-management`；按需要读取测试、日志、签名和重构相关 Skill。

实现清单中全部正常功能和已观察的分支。开发可以分步，但交付范围保持完整。未连通按钮、静态假数据和占位功能不能通过验收。不可访问的账号或服务能力保留条目并记录阻塞，继续其他功能。

建立可重复构建启动入口，确保启动本次构建的 `.app`。使用独立 bundle identifier、配置和测试数据，避免写入原版状态。

## 4. 行为验证与交付

对原版和复刻版执行对应的同一组场景，比较输出文件、状态转换、设置、快捷键、窗口行为和重启恢复。用 Computer Use 检查实际界面；对算法、格式、持久化及容易回归的行为执行有意义的自动化测试。

发现差异后自主回到调查、实现和验证，不要求用户逐个决定正常功能是否需要。体验反馈加入清单、修正后重跑相关场景。

交付可运行 `.app`、完整源码、构建启动方法、覆盖与验证结果、确实尚未解决的差异。各项状态和证据可检查后才报告完成，不隐藏阻塞。打包、公证、发布仅按用户要求执行。
