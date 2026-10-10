# 安装默认工具组

默认工具组有三项，都是用户级安装，只配置 Codex：

| 工具 | 用途 | 安装方式 |
| --- | --- | --- |
| Build macOS Apps 插件 | 构建、运行、调试原生 App 的 Skills | `codex plugin add` |
| Computer Use 插件 | 截屏并操作 GUI | `codex plugin add` |
| REA（`rea-agents@6.1.0`） | 逆向分析 MCP 和 REA Skill | `rea setup --client codex` |

安装本 Skill 时不会执行任何安装脚本；首次使用时复用已经就绪的工具，按当前任务补装。

## 安装授权

- 用户显式调用 `$replicate-macos-app`，或明确要求准备环境：直接安装默认工具组。
- 本 Skill 被自动触发：先告诉用户将安装上表三项（用户级安装），得到同意后再安装。
- 默认工具组以外的分析工具：先说明用途和安装范围，再安装。

## 安装步骤

1. 运行 `python3 "$SKILL_DIR/scripts/bootstrap.py" --install`。Python 不可用时，先运行 `xcode-select --install` 安装 Command Line Tools。安装器逐项处理，已就绪的直接复用：
   - 插件：从 `codex plugin list --json --available` 找到插件，未安装时执行 `codex plugin add`。
   - REA：先用 `rea setup --client codex --dry-run` 生成安装计划，确认计划只包含配置 Codex 和安装 REA Skill，再正式执行，最后用 `rea doctor` 复核。
2. 查看安装器输出里每一项的状态。部分失败时保留成功的项，只修复当前工作需要的失败项；已有可用的替代工具时直接继续。
3. 把需要用户亲自完成的操作（见下文表格）一次性告诉用户；已有复刻项目时同时写进 `progress.md`。
4. 用户重启或重连 Codex、加载新配置后，回到 SKILL.md 第 2 步，对要用的工具做真实调用。

只检查、不安装时运行 `bootstrap.py --check`。它不写任何客户端配置，但第一次运行会把 `rea-agents` 下载到 npm 缓存。

## 已有配置的处理

安装器保留用户现有的配置：

- Codex 已注册更高版本的 REA，或版本无法判断（如 `@latest`、本地路径）：保留原注册并报告，先检查当前会话里实际可用的 REA 工具。
- 同一插件有多个 marketplace 来源：列出候选，让用户选择。插件已安装但未启用：提示用户启用。
- 只改动需要的 Codex 配置，其他 MCP、其他客户端和用户已有的 Skills 保持原样。

## 其他分析工具

- 需要静态或动态分析时，先看 REA 当前的 provider、调试器和已有工具能否满足。工具名和参数以实际版本的 schema、`--help` 和官方文档为准。
- Hopper 是可选的反编译器。已有 Hopper 时先运行对应的 doctor；需要新装时，由用户明确选择后运行 `bootstrap.py --install --with-hopper`，许可证由用户自行购买。demo 版或 doctor 通过只代表准备了一部分，能否分析 A 要实际调用一次才知道。
- 使用 LLDB、Frida、其他反编译器、网络和文件观察工具时，保存验证输出。验证单个工具时，只改动这个工具需要的设置。

## 需要用户亲自完成的事项

只在实际缺失时提出：

| 项目 | 用户要做的事 |
| --- | --- |
| Computer Use | 启用插件，按系统提示授予屏幕录制和辅助功能权限，允许它访问 A |
| AX 工具 | `ax` 报权限不足时，为运行它的 App（如 Codex 或终端）授予辅助功能权限 |
| A 的私有数据目录 | 调查确实需要、且读取被拒绝时，按系统提示授权访问；开始时无需申请完全磁盘访问 |
| 开发工具 | 按所选技术栈准备工具链；Swift 和 Xcode 只在构建或编译 AX 工具时需要 |
| 安装器依赖 | 按实际报错准备受支持的 Node.js、npm/npx 和 codex CLI，版本要求以安装器的检查结果为准 |
| 新配置未加载 | 重连或重启 Codex，然后在当前会话中验证工具 |
| A 本身 | 安装并启动 A，需要时自己完成登录或许可证激活 |

系统权限由用户本人在「系统设置」中授予。不修改 TCC 数据库，不运行 `tccutil reset`；一般的依赖安装授权不包含关闭系统保护。

## 连接核对

核对方式见 SKILL.md 第 2 步。另外注意两点：

- Computer Use 能截到画面后，再在授权范围内执行一次可撤销的输入，才算确认能操作 A。
- 终端里能运行 REA，桌面客户端却报找不到 `npx` 或 `node` 时，只修复这个 MCP 注册里的启动路径或 env，参数、版本和其他注册保持不变，修复后重新核对连接。

用户只要求准备工具时，报告已就绪、未验证、需要用户处理的三类项目，然后停止。

## 上游资料

- REA 安装：https://github.com/morluto/rea/blob/main/docs/installation.md
- REA setup 接口：https://github.com/morluto/rea/blob/main/src/cli/setupCommands.ts
- Codex Skills：https://developers.openai.com/codex/skills/
