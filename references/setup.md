# 安装准备

本 Skill 的原版探索和 App 验收在本地 macOS 执行。安装 Skill 不会执行安装钩子；首次使用时复用已就绪能力，按当前任务补充工具。以下安装器准备默认工具组，不代表只允许使用这些方法，也不要求所有项成功才开始其他工作。

## 授权

用户显式调用 `$replicate-macos-app`，或明确要求准备环境时，视为授权准备必要的默认依赖。隐式启用时，先说明将安装 Build macOS Apps 和 Computer Use 插件、为 Codex 配置 REA MCP 并安装 REA Skill（用户级安装），取得同意后安装。

新增分析工具按实际问题选择，先说明用途与安装范围，复用已有软件；付费购买、账号访问、系统安全变更和对外发布不包含在一般依赖安装授权中。

## 默认工具组

1. 确认执行环境是目标 App 所在的本地 macOS。环境不符时继续可完成的文档、代码或平台无关测试，不声称替用户 Mac 完成安装、授权或 App 验收。
2. 运行 `python3 "$SKILL_DIR/scripts/bootstrap.py" --install`。Python 不可用时先准备 Command Line Tools（`xcode-select --install`）。安装器逐项复用已有能力：
   - Build macOS Apps、Computer Use：从 `codex plugin list --json --available` 找到插件，未安装时调用对应的 `codex plugin add`。
   - REA：保留固定的 `rea-agents@6.1.0`。先用 `rea setup --client codex --dry-run` 生成限定计划，核对只配置 Codex 和安装 REA Skill，再应用并复核。
3. 核对每项状态。部分失败时保留成功项，只修复当前工作需要的失败项；已有可用替代能力时继续，不为追求安装报告全绿反复重装。
4. 集中列出当前确需用户完成的权限与连接操作，写入 `progress.md`。新配置加载后回到 SKILL.md 第 2 节，验证实际选择的能力。

`--check` 不写客户端配置，但首次执行可能下载 `rea-agents` 到 npm 缓存。bootstrap.py 是已有默认工具组的安装器，不负责自动安装方法目录中的所有工具。

## 保留现有配置

- Codex 已注册更新版本或无法确定版本（如 `@latest`、本地路径）的 REA 时，安装器保留注册并报告问题。先检查当前会话实际工具，不能自动降级。
- 插件有多个 marketplace 来源时列出候选，由用户选择；已安装但未启用时提示启用。
- 只修改需要的 Codex 配置，保留其他 MCP、其他客户端与用户已有 Skills。
- 不使用 AX 时初始化项目可加 `--skip-ax`。默认编译失败时 `ax.status` 为 `unavailable`，项目记录仍然可用；选择替代方法或针对性修复。

## 深度分析及其他工具

需要静态或动态分析时，先检查当前 REA provider、调试器或直接可用的工具。以实际版本的 schema、CLI 帮助和官方文档为准，不硬编码未经验证的工具名。

Hopper 是可选项。已有 provider 先运行对应 doctor；安装 Hopper 需要用户明确选择，再执行 `bootstrap.py --install --with-hopper`，不代购许可证。Demo 或 doctor 通过只说明部分准备状态，分析目标是否成功仍需实际调用。

LLDB、Frida、其他反编译器、网络与文件观察工具、自写脚本和其他开发框架都可按需采用。保存安装来源、版本和验证输出。不要为了验证一个工具先改变整台机器的安全设置。

## 实际缺失时需要用户完成的事项

| 检查项 | 用户操作 |
| --- | --- |
| Computer Use | 启用插件，按系统提示授予屏幕录制和辅助功能权限，允许访问本次目标 App |
| AX | `ax` 报权限不足时，为实际执行宿主授权辅助功能；不使用 AX 时不用因此停止其他工作 |
| 原版私有数据目录 | 只在调查确实需要且读取被拒绝时，提示对应数据访问授权；不一开始要求完全磁盘访问 |
| 开发工具 | 按所选技术栈准备工具链；Swift/Xcode 只用于需要它们的构建或 AX 工具 |
| 默认安装器依赖 | 按实际报错准备受支持的 Node.js、npm/npx 和 codex CLI；具体要求以固定版本帮助与检查结果为准 |
| 新配置未加载 | 重连或重启 Codex，然后验证当前会话中的工具 |
| 原版 App | 安装、启动并按实际需要自行完成登录或许可证步骤 |

系统权限由用户亲自授予，不修改 TCC 数据库，不运行 `tccutil reset`，不把一般依赖安装授权解释成关闭系统保护的许可。

## 连接验证

分别检查：配置已写入、当前会话可调用、能处理目标。对每个选用工具做范围明确的真实调用；GUI 能获取画面后，在授权范围内执行可撤销的输入，才能确认可操作性。没有使用的工具可以保持未检查。

终端可运行 REA 而桌面客户端报找不到 `npx` 或 `node` 时，只修复该 MCP 的启动路径或 env，保留参数、版本和其他注册。修复后重新核对实际连接，不重装整套依赖。

只准备环境时报告已就绪、未验证和需人工处理的项，然后停止，不开始具体 App 的构造。

## 上游资料

- REA 安装：https://github.com/morluto/rea/blob/main/docs/installation.md
- REA setup 接口：https://github.com/morluto/rea/blob/main/src/cli/setupCommands.ts
- Codex Skills：https://developers.openai.com/codex/skills/