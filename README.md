# replicate-macos-app

一个 Codex Skill：把闭源的 macOS App 复刻成一个拥有完整源码、可以独立构建运行的新 App。

- 复刻版覆盖原版的全部正常功能，状态变化、文件读写、错误处理和重启恢复都是真实实现。
- 调查原版时，Codex 按具体问题选择方法：GUI 和辅助功能（AX）自动化、逆向分析、静态和动态分析、文件和网络观察、自写脚本，或请你提供信息。
- 复刻版的源码是依据原版行为重新编写的实现。
- 复刻版默认命名为 `原版名称-replicate`，例如 SQLiteFlow 的复刻版叫 SQLiteFlow-replicate；没有指定项目目录时，新建的项目目录也用这个名称。

## 运行要求

- 目前只支持 Codex，需要在原版 App 所在的 Mac 上使用。
- 默认工具组：Build macOS Apps 插件、Computer Use 插件和 REA（逆向分析 MCP 与 Skill，固定 `rea-agents@6.1.0`）。首次使用时 Skill 会检查并按需安装，详见 [setup.md](references/setup.md)。也可以改用其他工具；缺少某一项时，不依赖它的工作照常进行。

## 安装

通过 [Skills CLI](https://github.com/vercel-labs/skills) 安装，用 `--agent codex` 指定 Codex。

安装到当前项目：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app --agent codex
```

跨项目使用（安装到 `~/.agents/skills/`）：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app --agent codex --global
```

安装命令只复制 Skill 的说明、脚本和参考资料，不安装任何依赖。`.agents/skills/` 目录也会被其他客户端读取；在 Codex 以外的环境中触发时，Skill 会说明目前只支持 Codex 并停止。

## 使用

完整复刻：

```text
使用 $replicate-macos-app，完整复刻 /Applications/目标应用.app，
把项目放到 ~/Projects/目标应用-replicate。
```

只准备工具：

```text
使用 $replicate-macos-app，只完成安装准备并核实连接。
```

## 需要你做的事

- **同意安装**：显式调用本 Skill 时，Codex 直接安装默认工具组；Skill 被自动触发时，会先征求你的同意。付费、系统安全设置变更和对外发布会单独征求同意。
- **授予权限**：按系统提示授予屏幕录制和辅助功能权限；原版需要登录或许可证时，由你自己完成。
- **试用反馈**：试用复刻版，指出和原版不一样的地方。

## 工作流程

1. 确定原版和项目目录，初始化记录。
2. 准备并验证要用的工具。
3. 清点原版的全部入口和功能。
4. 用实验调查每个功能的实际行为。
5. 实现复刻版。
6. 在原版和复刻版上运行相同的场景并修复差异；再在没有原版的干净 macOS 上验证复刻版能独立运行。
7. 固定版本，交付源码、可运行的 App、构建和重置方法、覆盖记录和已知差异。

## 脚本与测试

```bash
python3 scripts/init_project.py PROJECT_DIR --app-path APP_PATH   # 初始化记录；加 --skip-ax 跳过 AX 工具编译
python3 scripts/ledger_check.py PROJECT_DIR                       # 检查记录、AX 覆盖、静态线索和证据来源
python3 scripts/ledger_check.py PROJECT_DIR --uncovered           # 列出原版 AX 导出中全部未登记的元素
python3 scripts/scenario_run.py PROJECT_DIR S-001                 # 在原版和复刻版上各运行一次场景脚本
python3 scripts/ledger_check.py PROJECT_DIR --final               # 冻结后的交付检查
```

- 重复运行 `init_project.py` 只补建缺失的文件，已有记录保持不变。原版的路径、bundle identifier 或版本与已有记录不同时，它报错退出，避免混用不同版本的证据。
- AX 工具编译失败时报告为 `unavailable`，其余记录照常创建。`ax dump` 输出的第一行记录被导出 App 的身份，`ledger_check.py` 据此区分原版和复刻版的导出。
- `ledger_check.py` 检查记录的结构、关联、原版 AX 元素和包内组件的登记情况，以及证据是否来自对应的 App；复刻版的实际表现另外验收。
- `scenario_run.py` 运行前核对两个 `.app` 的身份，每次运行的退出码、脚本哈希和输出文件写入 `replica/evidence/runs/`。

运行仓库测试（使用合成 App 和临时目录，不需要原版 App）：

```bash
python3 -m unittest discover -s tests -v
```

- `ledger_check.py`、`scenario_run.py` 和 `bootstrap.py` 的测试与平台无关。
- `init_project.py`、`bundle_scan.py` 和 `state_diff.py` 的测试调用 `sw_vers`、`codesign`、`otool`、`plutil`、`defaults` 等系统工具，只在 macOS 上运行；AX 编译测试还需要 Xcode Command Line Tools。不满足条件时这些测试会跳过。
- 状态差分测试把 `HOME` 指向临时目录，每次使用新的 bundle identifier，不改动你的 `~/Library`。

原版的实际探索、AX 权限和复刻版的独立运行需要在真实 Mac 上验证。

## 卸载

默认工具组是用户级安装，可以分别卸载。`<marketplace>` 用 `codex plugin list` 查看：

```bash
codex plugin remove build-macos-apps@<marketplace>
codex plugin remove computer-use@<marketplace>
```

其他工作也不再需要 REA 时：

```bash
codex mcp remove rea
rm -rf ~/.agents/skills/reverse-engineer-anything
```

删除本 Skill 的安装记录：

```bash
rm -rf ~/.local/share/replicate-macos-app
```

移除 Skill：`npx skills remove replicate-macos-app --agent codex`，全局安装时加 `--global`。复刻过程中另外安装的分析工具记录在各项目的 `progress.md` 中，需要时按记录单独卸载；多个程序共用的依赖保留。

## 文件

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 复刻流程 |
| [references/setup.md](references/setup.md) | 默认工具组的安装与连接核对 |
| [references/methods.md](references/methods.md) | 按问题选择调查方法 |
| [references/ledger.md](references/ledger.md) | 入口、功能、证据和场景的格式 |
| [references/reference-app.md](references/reference-app.md) | 复刻版的构建记录、独立运行验收与冻结 |
| [scripts/bootstrap.py](scripts/bootstrap.py) | 默认工具组安装器 |
| [scripts/init_project.py](scripts/init_project.py) | 初始化项目记录，按需编译 AX 工具 |
| [scripts/bundle_scan.py](scripts/bundle_scan.py) | 扫描包结构、入口、文案、资源和数据模型 |
| [scripts/ax.swift](scripts/ax.swift) | 导出 AX 树、操作界面元素 |
| [scripts/state_diff.py](scripts/state_diff.py) | 偏好设置和数据目录的快照与差分 |
| [scripts/ledger_check.py](scripts/ledger_check.py) | 记录检查与交付前检查 |
| [scripts/scenario_run.py](scripts/scenario_run.py) | 在原版和复刻版上运行场景脚本并保存运行记录 |
| [tests/](tests/) | 各脚本的回归测试，`support.py` 提供合成 App 和脚本调用 |
| [agents/openai.yaml](agents/openai.yaml) | Codex 中的展示与调用配置 |
| [assets/icon.svg](assets/icon.svg) | Skill 图标 |
