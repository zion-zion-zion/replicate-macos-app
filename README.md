# replicate-macos-app

将闭源 macOS App 尽可能完整地复现为**可独立运行、拥有完整私有源码的参考 App**。面向在 Mac 上工作的 Codex，允许按目标自由组合 GUI/AX、REA、静态与动态分析、文件和网络观察、自写工具、第三方组件及人工证据；现有工具集不构成方法上限。

## 在项目中的位置

```text
闭源原版 A
    │ 构造者：综合使用可用方法，探索、实现、对照与验收
    ▼
参考 App B + 完整源码 + 构建/重置方法 + 验证记录
    │ 后续独立评测：隔离 B 源码，只开放约定的 Computer Use 接口
    ▼
被测 Agent 实现的 App C
```

本 Skill 负责 **A → B**。B 的源码是我们拥有的参考实现源码，不声称恢复了 A 的原始源码。构造者可以使用逆向和其他工具，不受后续被测 Agent 的 GUI-only 探索限制。最终要求是完整功能、真实状态、独立构建运行和可验证行为，不能靠调用原版二进制、占位按钮或硬编码测试结果完成。

具体 App 的参考源码、逆向材料、构造会话与隐藏测试保存在独立私有工作区；本公共仓库只分发通用 Skill 和工具。闭源原型不自动证明零污染，参考版本的生成、公开历史和访问隔离需要实际记录。

## 安装

通过 [Skills CLI](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app
```

在 Codex 中跨项目使用：

```bash
npx skills add https://github.com/zion-zion-zion/replicate-macos-app --skill replicate-macos-app --agent codex --global
```

安装命令只复制 Skill 指令、脚本和参考资料。首次使用时复用当前可用能力；需要准备默认工具组时按 [setup.md](references/setup.md) 安装 Build macOS Apps、Computer Use、REA MCP 与 REA Skill。安装器继续固定 `rea-agents@6.1.0`，不会因本次工作流更新擅自升级已有依赖。

默认工具组是便利入口，不是强制技术栈。也可以使用适合目标的其他工具与框架；缺少某一项不会阻塞不依赖它的工作。系统权限、账号和许可证只在实际需要时由用户完成，不能由安装成功推断当前会话已连接或原版已经可操作。

## 使用

在 Mac 上的 Codex 会话中提供目标 App 和工作目录：

```text
使用 $replicate-macos-app，完整复刻 /Applications/目标应用.app，
把项目放到 ~/Projects/目标应用复刻。
目标是构造拥有完整私有源码、可以独立运行的参考 App；
自主选择所需调查和实现方法，完成全功能盘点、实现和原版对照验证。
```

只准备环境：

```text
使用 $replicate-macos-app，只完成安装准备并核实连接。
```

显式调用本 Skill 或明确要求准备环境时，按 setup.md 处理必要依赖安装；隐式启用时先说明安装范围并取得同意。额外付费、系统安全变更和对外发布仍需对应授权。

## 工作流程

1. 固定原版与工作区，初始化功能、场景、进度和 `reference-manifest.json`；已有记录保持不变。
2. 建立完整入口与依赖地图，按具体未知问题选择方法，不规定所有 App 必须走同一工具顺序。
3. 用静态线索、运行时实验和输入输出证据调查行为；必要时扩展工具、编写脚本或拆分子任务。
4. 采用适合的架构和可用组件实现完整参考 App，不强制所有目标都使用 SwiftUI。
5. 在原版 A 和参考 B 上执行对应场景，检查界面、功能、状态、文件、异常与恢复，持续修复差异。
6. 从交付源码构建，并在无 A 和原版私有数据的干净 macOS 环境中验证独立运行与状态重置。
7. 固定 B 的源码修订和制品摘要，交付源码、可运行 App、构建/启动/重置方法、覆盖记录和真实差异。

参考构造和第二层评测的权限、材料与验收对象见 [reference-app.md](references/reference-app.md)。当前任务只构造 B，不自动执行 B → C 或发布参考源码。

## 脚本与验证

初始化仍兼容原有调用，新增可选的 `--skip-ax`：

```bash
python3 scripts/init_project.py PROJECT_DIR --app-path APP_PATH --skip-ax
python3 scripts/ledger_check.py PROJECT_DIR
python3 scripts/ledger_check.py PROJECT_DIR --final
```

不传 `--skip-ax` 时仍尝试编译 AX 工具，但编译失败会报告为 `unavailable`，其余项目记录仍可使用。旧项目补建参考实现清单，不覆盖原来的进度、功能和场景。原版身份或版本与旧项目不一致时停止，防止混用证据。

证据支持通用的 `static` 和 `runtime` 类型，不绑定某个分析工具。最终检查会拒绝空功能清单和空场景；通过校验仍不等于已经完成实际 App 验收，有阻塞必须明确报告。

运行仓库的合成数据测试：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖初始化、旧项目保留、工具不可用时继续、通用证据以及清单验收。它们不替代真实 macOS 原版探索、AX 权限和参考 App 的独立运行测试。

## 卸载

默认工具组为用户级安装，可分别撤销。`<marketplace>` 见 `codex plugin list`：

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

移除 Skill：`npx skills remove replicate-macos-app`，全局安装时加 `--global`。额外安装的分析工具按构造记录单独处理，不自动卸载共享依赖。

## 文件

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 参考应用构造工作流 |
| [references/setup.md](references/setup.md) | 默认工具安装与能力核对 |
| [references/methods.md](references/methods.md) | 按问题选择方法与扩展能力 |
| [references/ledger.md](references/ledger.md) | 入口、功能、证据和场景格式 |
| [references/reference-app.md](references/reference-app.md) | 独立性验收、版本冻结与隔离 |
| [scripts/bootstrap.py](scripts/bootstrap.py) | 保留的默认依赖安装器 |
| [scripts/init_project.py](scripts/init_project.py) | 初始化项目及参考实现清单，按需编译 AX |
| [scripts/bundle_scan.py](scripts/bundle_scan.py) | 包结构、入口、文案、资源与模型扫描 |
| [scripts/ax.swift](scripts/ax.swift) | AX 树导出与元素操作 |
| [scripts/state_diff.py](scripts/state_diff.py) | 偏好和数据目录快照与差分 |
| [scripts/ledger_check.py](scripts/ledger_check.py) | 记录与交付前覆盖检查 |
| [tests/test_workflow.py](tests/test_workflow.py) | 平台无关的回归测试 |
| [agents/openai.yaml](agents/openai.yaml) | 展示与调用配置 |
| [assets/icon.svg](assets/icon.svg) | Skill 图标 |