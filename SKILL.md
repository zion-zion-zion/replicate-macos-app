---
name: replicate-macos-app
description: Use when the user wants to replicate (复刻) or rebuild a closed-source macOS app as a standalone app with full source code, or wants only this skill's toolchain installed and checked. Requires the original app on the local Mac.
---

# macOS 闭源 App 复刻

## 目标

把闭源的原版 App（下文称 **A**）复刻成新 App（下文称 **B**）。B 要同时满足：

- 覆盖 A 的全部正常功能，包括菜单、设置、快捷键、文件读写、错误提示和重启后的状态恢复。
- 拥有完整源码，可以从源码重新构建。
- 在没有安装 A 的 Mac 上独立运行。

B 的源码是依据 A 的行为重新编写的实现，交付时这样向用户说明。

## 分工

- **你**：清点功能、调查行为、实现、对照验证和修正，全程自主推进。开发可以分阶段，最终交付全部功能；范围内的功能直接实现，无需逐项询问用户。
- **用户**：指定 A 和项目位置，完成需要本人操作的授权（系统权限、登录、付费），试用 B 并指出差异。
- **方法**：按具体问题选择，可以组合 GUI 和辅助功能（AX）自动化、逆向分析、静态和动态分析、文件与网络观察、自写脚本、第三方库、子 Agent，或向用户索取证据。默认工具组是 REA（逆向分析工具，提供 MCP 和 Skill）、Computer Use（截屏并操作 GUI）和 Build macOS Apps（构建原生 App 的一组 Skills）。

## 路径与参考文件

`SKILL_DIR` 指本 Skill 所在目录，`PROJECT_DIR` 指复刻项目目录。脚本一律用绝对路径运行。所有记录和证据放在 `PROJECT_DIR/replica/`。

| 文件 | 何时读取 |
| --- | --- |
| [references/setup.md](references/setup.md) | 安装或修复默认工具组 |
| [references/methods.md](references/methods.md) | 为具体问题挑选调查方法，或现有工具不够用 |
| [references/ledger.md](references/ledger.md) | 填写入口、功能、证据和对照场景 |
| [references/reference-app.md](references/reference-app.md) | 填写 `reference-manifest.json`、验收 B 的独立运行、冻结版本 |

## 授权与数据

- 用户明确限制的操作，照其限制执行。
- 以下操作先取得用户的对应授权：付费购买、使用账号、更改系统安全设置、破坏性的系统修改，以及上传或发布 A 的资源、分析材料和 B 的源码。
- 只安装当前调查需要的工具，优先复用已有软件和配置；新装的工具在 `progress.md` 记录来源和版本。
- 调查时使用测试账号、合成文件和隔离目录。修改 A 的设置前保存原值或快照，测试结束后恢复。
- 写进证据和记录文件的凭据、个人数据先脱敏；证据只保留能复核结论的最小输出。
- 从 A 提取的资源只作分析证据。交付物只包含 B 的源码、B 的资源，以及已确认使用依据并记录在 `reference-manifest.json` 的组件。

## 流程

### 1. 确定目标和项目

1. 用户已给出的 App、版本和项目位置直接使用。不知道目标时，只问 App 名称或路径，并解析到本机唯一的 `.app`。
2. 用户没指定项目位置时，用当前空目录或已有的复刻项目；两者都没有时，在当前目录下新建一个项目子目录。
3. 确认操作 A 的工具运行在 A 所在的 Mac 上。在远程或 Linux 环境中只做资料整理、写代码和平台无关的测试，汇报时说明尚未观察 A、尚未完成 macOS 验收。
4. 初始化项目：

   ```bash
   python3 "$SKILL_DIR/scripts/init_project.py" PROJECT_DIR --app-path APP_PATH
   ```

   它在 `replica/` 下建立功能清单、场景、`progress.md` 和 `reference-manifest.json`，并编译 AX 工具 `replica/bin/ax`。不需要 AX 时加 `--skip-ax`；AX 编译失败只影响这一个工具。已有项目会保留原文件，继续工作前先读 `progress.md`、功能清单、场景和 `reference-manifest.json`。
5. 在 `progress.md` 补充 A 需要的权限、能访问到的功能和外部依赖（服务端、硬件等）。用户还没选定 A 时，优先推荐能独立运行、核心状态可控的 App；已选定的 A 依赖服务端或硬件时，逐项调查并登记。

用户只要求准备工具时，按 setup.md 完成安装和连接核对，然后停止。

### 2. 准备工具

先看当前会话已经能用哪些工具，缺少的按 setup.md 安装。每个准备使用的工具都做一次范围明确的真实调用，在 `progress.md` 分三项记录：是否已安装、当前会话能否调用、能否处理 A。调用 MCP 或 CLI 前，先读取它实际的 schema 或当前官方文档。

某个工具用不了时，换一种能验证结果的方法，同时继续不依赖它的工作。

### 3. 清点全部功能

先做一遍覆盖全局的清点，再深入不确定的部分。调查和实现可以穿插进行。

- **静态扫描**：`python3 "$SKILL_DIR/scripts/bundle_scan.py" PROJECT_DIR` 列出包结构、声明的入口、文案、资源、数据模型、Helper、XPC、扩展和依赖，结果写入 `evidence/bundle/`。扫描失败或某类结果为空时，用其他方法继续找。
- **AX 清点**：先启动 A，再运行 `PROJECT_DIR/replica/bin/ax dump BUNDLE_ID`，列出菜单、窗口、设置、快捷键和状态。也可以用 AppleScript 或 A 的公开接口。
- **实际操作**：布局、自绘控件、拖放、动效等 AX 读不到的内容，通过实际画面和交互检查。
- **外部资料**：帮助文档、官网和版本说明里提到的功能，先登记为待验证。

按 ledger.md 的入口类别登记每个入口。菜单之外，还要检查文件关联、URL scheme、系统服务、通知、权限被拒绝时的表现、撤销重做、多窗口、首次启动、退出和重启恢复。系统标准菜单项可以注明“由框架提供”，同时检查它的实际行为；有业务逻辑的入口都登记为功能。

`ledger_check.py` 输出的 `entry_kinds.unchecked` 列出还没处理的入口类别，用来发现漏项。确认 A 没有某类入口时，在 `absent_entry_kinds` 写明依据。

### 4. 调查行为

每次调查在证据里写清：要弄清的行为、几种可能的解释、能区分它们的输入和前置状态、使用的方法、实际输出和结论。先做最能缩小不确定性的实验；低成本的方法没效果就换方法。可选方法见 methods.md。

静态分析、资源和文档提供线索，功能的预期行为以 A 实际运行的结果为准。只有静态线索的功能保持 `hypothesis` 状态。

记录偏好设置和文件变化：

```bash
python3 "$SKILL_DIR/scripts/state_diff.py" snapshot PROJECT_DIR before --path TEST_DIR
# 在 A 上执行要调查的操作
python3 "$SKILL_DIR/scripts/state_diff.py" snapshot PROJECT_DIR after --path TEST_DIR
python3 "$SKILL_DIR/scripts/state_diff.py" diff PROJECT_DIR before after
# 对 B 拍快照时加 --app-path B_APP_PATH
```

每条结论关联到功能 ID 和证据文件。其他工具的输出用 `static` 或 `runtime` 证据类型登记，写明工具、参数、A 的版本和输出，格式见 ledger.md。

### 5. 实现 B

- 架构依据已验证的行为来选。原生界面通常用 SwiftUI + AppKit；复杂编辑器等场景有更合适的技术栈时直接采用。B 的内部结构可以和 A 不同，交互习惯和视觉风格与 A 保持一致。
- 使用 Build macOS Apps 时，读取当前可用的相关 Skills，例如 `build-run-debug`、`swiftpm-macos`、`appkit-interop`、`window-management`。用其他技术栈时，建立同等的构建、启动、日志和测试入口。
- 可以使用系统框架、开源库、CLI 工具等可合法使用的组件，在 `reference-manifest.json` 记录来源、版本、许可和修改。
- B 的核心功能全部由交付源码和声明的依赖实现。B 运行时不调用 A，不嵌入 A 的专有核心二进制，也不用截图回放代替功能。
- B 使用自己的 bundle identifier、配置目录和数据目录。建立可重复的构建和启动命令，每次测试前确认运行的是刚构建的 B。
- 功能实现完成的标准：状态变化、文件读写、错误处理、持久化、撤销和恢复都是真实逻辑；按钮连到真实操作，数据来自真实状态，测试结果由实际运行产生。
- A 依赖服务端时，B 按公开协议对接，或自建一个可控的后端，提供真实的状态、重置方法和测试数据，并记录与 A 的差异。账号、原厂服务、硬件、许可证或 entitlement 确实无法满足时，把对应功能标为 `blocked` 并写明原因。

### 6. 对照验证

1. 给 A 和 B 相同的输入和起始状态，比较界面、快捷键、状态变化、输出文件、错误表现、持久化和重启恢复。场景格式和比较方法见 ledger.md。
2. 发现差异时，先保存能复现的失败场景，修复后重跑这个场景和受影响的场景。用户反馈的差异也登记进同一份清单，并触发回归。
3. 反复调查和修正，直到所有能访问的功能都验证过。
4. 按 reference-app.md 验收 B 的独立运行：从交付源码构建，在没有 A、没有 A 的私有数据、也没有调查工具的干净 macOS 环境中运行，加载测试数据、重置状态并重放场景。
5. 交付前运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR --final`。它检查记录是否完整；B 是否与 A 等价、能否独立运行，以第 1–4 步的实际结果为准。

### 7. 冻结并交付

1. 按 reference-app.md 填完 `reference-manifest.json` 并冻结版本：记下验收通过时的源码修订和 `.app` 的 SHA-256。之后再修改 B，就产生新版本。
2. 交付：可运行的 `.app`、完整源码、构建和启动方法、测试与重置说明、功能覆盖统计、阻塞项和已知差异。有 `blocked` 功能时，明确说明这是带阻塞的交付，并列出阻塞项。
3. 打包、公证和发布在用户要求时执行。
