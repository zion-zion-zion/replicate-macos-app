# replicate-macos-app

macOS App 全功能复刻 Skill。面向运行在用户 Mac 上的 Codex：用 Computer Use 和 REA MCP 探索闭源原版，用 Build macOS Apps 插件的 Skills 重建原生 App，并逐项对照验证。

## 安装

通过 [Skills CLI](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app
```

按提示选择 Agent 和安装方式。默认安装到当前项目；在 Codex 中跨项目使用时，指定全局安装：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app --agent codex --global
```

Skills CLI 当前版本要求 Node.js >=22.20.0。

安装命令只复制 Skill 指令、脚本和参考资料。首次使用时，Skill 会在当前会话实际调用三个工具，缺什么就按 [安装准备说明](references/setup.md) 装什么：

| 依赖 | 安装方式 |
| --- | --- |
| Build macOS Apps 插件 | `codex plugin add build-macos-apps@<marketplace>` |
| Computer Use 插件 | `codex plugin add computer-use@<marketplace>` |
| REA MCP 与 REA Skill | 固定 `rea-agents@6.1.0`，先生成限定计划，再用官方 `rea setup --client codex` 应用 |

这些都是用户级安装，对所有项目生效。用户需要亲自授予 Computer Use 屏幕录制和辅助功能权限，并在新安装后重启 Codex；开发工具、登录和许可证只在实际缺失时提示。

## 使用

在 Mac 上的 Codex 会话中提供目标 App 名称或路径，例如：

```text
使用 $replicate-macos-app，完整复刻 /Applications/目标应用.app，
把项目放到 ~/Projects/目标应用复刻。
```

只准备环境时：

```text
使用 $replicate-macos-app，只完成安装准备并核实连接。
```

提示中显式写出 `$replicate-macos-app` 即授权安装缺失的依赖；Codex 根据描述自动启用本 Skill 时，会先说明要安装的内容并征得同意。

## 工作流程

1. 确定目标 App 和项目目录，初始化入口清单、功能清单、场景和进度记录；在当前会话确认三个工具可用，缺失时安装。
2. 用 REA 登记 Info.plist 和 bundle 声明的入口，用 Computer Use 逐项登记菜单、设置、工具栏、右键菜单等界面入口。
3. 逐个功能：用 Computer Use 观察原版，界面解释不了的部分用 REA 调查；按 Build macOS Apps 的 Skills 实现；对原版和复刻版执行同一场景并对比截图与输出。
4. 清单校验通过后，交付可运行的 `.app`、源码和验证记录。

账号、原厂服务端、硬件、付费许可、Apple 限定 entitlement 或用户排除的功能记录为阻塞，其余功能都需要实现并验证。

## 卸载

首次使用会在本机做以下用户级改动，可以分别撤销。`<marketplace>` 见 `codex plugin list`。

插件：

```bash
codex plugin remove build-macos-apps@<marketplace>
codex plugin remove computer-use@<marketplace>
```

REA：Codex `config.toml` 中名为 `rea` 的 MCP 注册，以及 `~/.agents/skills/reverse-engineer-anything`。其他场景也不再使用 REA 时执行：

```bash
codex mcp remove rea
rm -rf ~/.agents/skills/reverse-engineer-anything
```

安装记录：

```bash
rm -rf ~/.local/share/replicate-macos-app
```

本 Skill：执行 `npx skills remove replicate-macos-app`，全局安装时加 `--global`。

## 文件

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent 工作流入口 |
| [references/setup.md](references/setup.md) | 安装准备与连接核对 |
| [references/ledger.md](references/ledger.md) | 入口清单、功能、场景的格式与规则 |
| [scripts/bootstrap.py](scripts/bootstrap.py) | 检查环境、安装缺失的依赖并记录结果 |
| [scripts/init_project.py](scripts/init_project.py) | 初始化复刻项目的记录文件与证据目录 |
| [scripts/ledger_check.py](scripts/ledger_check.py) | 校验记录，交付前检查覆盖 |
| [agents/openai.yaml](agents/openai.yaml) | Agent 展示与调用配置 |
| [assets/icon.svg](assets/icon.svg) | Skill 图标 |
