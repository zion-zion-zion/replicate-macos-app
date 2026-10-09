# replicate-macos-app

macOS App 全功能复刻 Skill。面向运行在用户 Mac 上的 Codex，结合 Computer Use、REA 和原生开发 Skills，探索目标 App、独立实现其功能并验证行为。

## 安装

通过 [Skills CLI](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app
```

按提示选择 Agent 和安装方式。默认安装到当前项目；在 Codex 中跨项目使用时，指定全局安装：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app --agent codex --global
```

Skills CLI 当前版本要求 Node.js >=22.20.0。安装结果会显示 Skill 的实际路径。

安装命令会复制 Skill 指令、脚本和参考资料；REA MCP 与开发依赖在首次使用时按 [安装准备说明](references/setup.md) 配置。这些依赖是用户级安装，对所有项目生效，具体内容和撤销方法见[卸载](#卸载)。

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

提示中显式写出 `$replicate-macos-app` 即授权首次安装依赖；Codex 根据描述自动启用本 Skill 时，会先说明要安装的内容并征得同意。

完整使用需要本地 macOS、可用的开发工具和目标 App。用户按实际提示开启 Computer Use，并授予屏幕录制、辅助功能及目标 App 访问权限；必要的登录和许可证由用户完成。

## 工作流程

1. 确定目标 App 和项目目录，初始化功能清单、场景和进度记录。
2. 检查环境，配置 REA MCP 和 11 个官方 macOS 开发 Skills。
3. 盘点 App 包的入口、技术栈和界面文案，用 Computer Use 探索原版操作，用 REA 调查资源、格式与相关逻辑。
4. 记录功能清单、测试场景和证据，区分推断与实测行为。
5. 按原版技术栈选择以 AppKit 或 SwiftUI 为主独立实现，非原生原版用 SwiftUI + AppKit 实现，使用与原版隔离的配置和数据。
6. 对原版与复刻版执行相同场景并对比界面截图，修正差异，清单校验通过后交付可运行的 `.app`、源码和验证记录。

不可访问的账号或服务能力会记录为阻塞。功能覆盖以清单和验证证据为准。

## 卸载

首次使用会在本机做以下用户级改动，可以分别撤销。

原生开发 Skills：`~/.agents/skills` 下的 11 个 `build-macos-apps--*` 链接，插件副本和安装记录在 `~/.local/share/replicate-macos-app`。

```bash
find ~/.agents/skills -maxdepth 1 -type l -name 'build-macos-apps--*' -delete
rm -rf ~/.local/share/replicate-macos-app
```

REA：Codex `config.toml` 中名为 `rea` 的 MCP 注册，以及 `~/.agents/skills/reverse-engineer-anything`。其他场景也不再使用 REA 时执行：

```bash
codex mcp remove rea
rm -rf ~/.agents/skills/reverse-engineer-anything
```

本 Skill：执行 `npx skills remove replicate-macos-app`，全局安装时加 `--global`。

## 文件

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent 工作流入口 |
| [references/setup.md](references/setup.md) | 安装准备与连接核对 |
| [references/workflow.md](references/workflow.md) | 功能记录、场景与验收 |
| [scripts/bootstrap.py](scripts/bootstrap.py) | 检查环境、安装依赖并记录结果 |
| [scripts/init_project.py](scripts/init_project.py) | 初始化复刻项目的清单、场景、进度记录与证据目录 |
| [scripts/inspect_bundle.py](scripts/inspect_bundle.py) | 盘点 App 包的入口、技术栈、权限和界面文案 |
| [scripts/ledger_check.py](scripts/ledger_check.py) | 校验功能清单、场景与证据，交付前检查覆盖 |
| [agents/openai.yaml](agents/openai.yaml) | Agent 展示与调用配置 |
| [assets/icon.svg](assets/icon.svg) | Skill 图标 |
