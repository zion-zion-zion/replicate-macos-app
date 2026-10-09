# 安装准备

本 Skill 面向本地 macOS 上的 Codex。安装 Skill 不会执行安装钩子；首次使用时由 `bootstrap.py` 准备依赖，之后检查并复用已就绪的项。

## 授权

用户在提示中显式调用 `$replicate-macos-app`，或明确要求准备环境时，视为已授权安装必要依赖，直接安装。本 Skill 因描述匹配被隐式启用时，先简短说明将安装 Build macOS Apps 和 Computer Use 插件、为 Codex 配置 REA MCP 并安装 REA Skill（用户级安装，对所有项目生效），取得同意后再安装。

## 步骤

1. 确认当前执行环境是目标 App 所在的本地 macOS。环境不符时说明本地运行要求，继续完成不依赖本地环境的工作。
2. 运行 `python3 "$SKILL_DIR/scripts/bootstrap.py" --install`。Python 不可用时先提示安装 Command Line Tools（`xcode-select --install`）。脚本逐项处理，已就绪的项直接复用：
   - Build macOS Apps、Computer Use：从 `codex plugin list --json --available` 找到插件，未安装时运行 `codex plugin add <插件>@<marketplace> --json`。
   - REA：固定 `rea-agents@6.1.0`。doctor 报告 Codex 注册与 REA Skill 都已就绪时直接复用；否则先用 `rea setup --client codex --dry-run` 生成计划，核对计划只包含配置 Codex 和安装 REA Skill，再用 `--yes` 应用，最后用 doctor 复核。
3. 核对输出中每一项的 `status`。部分失败时保留成功项，只修复失败项。
4. 一次性列出 `user_actions` 中需要用户亲自完成的事项；已初始化项目时同时写进 `progress.md` 的「等待用户处理」，并写明下一步。有新安装项时需要重启 Codex，重启后回到 SKILL.md 第 1 节第 3 步重新确认。

只读检查用 `--check`，它不写配置，首次运行会把 `rea-agents` 下载到 npm 缓存。

## 需要保留的现有配置

- Codex 已注册更新版本或无法确定版本（如 `@latest`、本地路径）的 REA 时，脚本保留该注册并报告失败。当前会话 REA 工具可用就继续；不可用时向用户说明现有注册并询问处理方式。
- 插件有多个 marketplace 来源时，脚本报告候选项，由用户选择。
- 插件已安装但未启用时，请用户在 Codex 的 Plugins 中启用。
- 脚本只配置 Codex，保留其他 MCP、其他客户端和用户已有的 Skill。

## Hopper

只在功能调查需要原生深度分析、现有 provider 不可用时处理。已有 provider 先运行针对它的 doctor，例如 `npm exec --yes --package=rea-agents@6.1.0 -- rea doctor --provider ghidra --format json`。安装 Hopper 需要用户明确选择，再运行 `bootstrap.py --install --with-hopper`，不购买许可证。装完后用户需要打开一次 Hopper，选择 Demo 模式或激活许可证，脚本会把这一步列入 `user_actions`。Hopper Demo 或 doctor 通过只说明 Hopper 可启动，能否分析真实目标以实际调用为准。

## 用户需要完成的事项

| 检查项 | 实际缺失时的用户操作 |
| --- | --- |
| 系统权限 | 按提示在「系统设置 → 隐私与安全性」授予 Computer Use 屏幕录制和辅助功能权限 |
| App 访问 | Codex 出现提示时允许访问本次目标 App |
| Node.js 与 npm | 安装 Node.js 22.x >=22.19、24.x >=24.11 或稳定版 26+，确认 `node`、`npm`、`npx` 可执行 |
| codex CLI | 安装 Codex CLI，或在 Codex 桌面版的 Plugins 中手动安装两个插件 |
| Swift 工具链 | 安装 Command Line Tools；需要 Xcode 工程时安装完整 Xcode |
| 新配置尚未加载 | 重启 Codex |
| 原版 App | 安装并启动原版，需要登录或许可证时由用户完成 |

系统权限由用户亲自授予，不改 TCC 数据库，不运行 `tccutil reset`。

## 连接验证

安装记录、插件列表和 doctor 只说明配置已写入，不能证明当前会话已加载。区分三种状态：配置已写入、工具在当前会话可调用、目标 App 可以操作。验证方式见 SKILL.md 第 1 节第 3 步。

终端能运行 REA 而 Codex 桌面版报 `npx` 或 `node` 找不到时，检查 REA MCP 的进程 PATH，只修复该 server 的启动路径或 env，保留参数、版本和其他 MCP，重启后验证。

## 上游资料

- REA 安装：https://github.com/morluto/rea/blob/main/docs/installation.md
- REA setup 接口：https://github.com/morluto/rea/blob/main/src/cli/setupCommands.ts
- Codex Skills：https://developers.openai.com/codex/skills/
