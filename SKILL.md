---
name: replicate-macos-app
description: Rebuild a closed-source macOS app as a complete, independently buildable and runnable app with full source code. Use for macOS App 复刻、全功能复刻、闭源软件重建、参考应用构造 and setup-only requests. Investigates with GUI/AX automation, REA, static or dynamic analysis, state and protocol inspection, custom tools or human evidence. Requires local macOS for original-app exploration and execution.
---

# macOS 闭源参考应用构造

把闭源原版 **A** 尽可能完整地复现为拥有完整源码、可独立构建运行的参考 App **B**。

按实际问题自由组合工具、直接调用 CLI/API、编写分析脚本、使用第三方依赖或拆分子任务；REA、Computer Use 和 Build macOS Apps 是默认能力，按需选用。用户明确指定的当前操作限制仍然有效。

交付范围保持原版的全部正常功能。自主清点、调查、实现、验证和修正；用户提供目标、完成确需人工的授权、体验成品并指出差异。开发可以分步，不把最终目标改成 MVP，不逐项询问是否添加范围内功能。

把本 Skill 的目录记作 `SKILL_DIR`，用绝对路径运行脚本。按需读取：

- [references/setup.md](references/setup.md)：准备或修复本地工具。
- [references/methods.md](references/methods.md)：选择调查、实验和实现方法；现有工具回答不了问题时扩展能力。
- [references/ledger.md](references/ledger.md)：登记入口、行为、证据和回归场景。
- [references/reference-app.md](references/reference-app.md)：参考实现清单、独立运行验收和参考版本冻结。

## 1. 建立目标与工作区

1. 复用用户已经提供的 App、版本和项目位置。目标未知时只询问 App 名称或路径，解析为本机唯一的 `.app`。项目位置未指定时，优先使用当前空目录或已有复刻项目；否则在当前目录下建立独立项目子目录，不覆盖其他工程。
2. 确认操作原版的工具实际运行在原版所在的 Mac。远程或 Linux 环境可以做资料整理、代码编辑和平台无关测试，但不能据此声称已观察原版或完成 macOS 验收。
3. 运行 `python3 "$SKILL_DIR/scripts/init_project.py" PROJECT_DIR --app-path APP_PATH`，创建 `replica/` 中的记录和 `reference-manifest.json`。不使用 AX 时加 `--skip-ax`；AX 编译失败只影响该工具，不阻塞其余调查。旧项目文件保留，继续前先读 `progress.md`、功能清单、场景和参考实现清单。
4. 记录 A 的版本、构建号、系统、权限、可访问功能及依赖。只在用户尚未选定原型时优先筛选独立运行、核心状态可控制的软件；已选目标的服务端或硬件依赖逐项调查，不能默默删除。

用户只要求安装准备时，按 setup.md 完成准备和真实连接核对后停止，不创建参考 App 或开始复刻。

## 2. 按任务准备能力

先检查当前会话已有能力；需要缺失能力时按 setup.md 准备。对选用的工具做一次真实、范围明确的调用，分别记录“已安装”“会话可调用”“能处理目标”。

默认可用工具包括包扫描、`ax`、状态差分、REA、Computer Use 和原生开发 Skills。也可使用其他反编译器、调试器、运行时插桩、网络与文件追踪、图像分析、格式解析器、自写脚本、其他开发栈或子 Agent。读取实际 schema 或当前官方文档，不假设具体 MCP 工具名存在。

只安装当前调查需要的能力。复用已有依赖和配置，记录新安装项；付费购买、账号访问、系统授权、破坏性系统修改及对外发布需要对应授权。工具不可用时尝试可验证的替代方法，并继续不依赖它的工作。

## 3. 建立并持续修订完整功能地图

先形成覆盖全局的入口与依赖清单，再围绕不确定项深入。调查和实现可以交替进行。

- 用 `bundle_scan.py PROJECT_DIR` 或其他适合技术栈的方法，检查包结构、声明入口、文案、资源、数据模型、Helper、XPC、扩展和依赖。扫描失败或无输出不等于没有功能。
- 能读取 AX 时，用 `replica/bin/ax dump BUNDLE_ID` 清点菜单、窗口、设置、快捷键和状态；也可使用 AppleScript、App 的公开接口或其他自动化工具。用实际画面与交互检查布局、自绘控件、拖放、动效和其他结构化接口无法表达的行为。
- 检查帮助文档、官网和版本说明，将声称存在的功能登记为待验证候选。静态资源、代码与文档提供线索；运行中的行为和实验结果决定规格。
- 按 ledger.md 登记各入口类别。菜单之外还检查文件关联、URL scheme、系统服务、通知、权限拒绝、撤销重做、多窗口、首次启动、退出和重启恢复。遇到新入口、新状态和隐藏分支时持续补充。
- 多个入口可指向同一功能，影响行为的每个设置都要登记。标准系统项可以注明由框架提供，但仍检查其实际行为；不能用 `skip` 排除有业务逻辑的正常功能。

`ledger_check.py PROJECT_DIR` 的入口类别统计用于发现漏项。不存在的类别必须写依据，不能为通过检查而批量填入无依据的说明。

## 4. 围绕行为问题选择方法、执行实验

每次调查写清：当前未知行为、候选解释、要区分它们的输入或前置状态、采用的方法、实际输出和结论。优先做能减少关键不确定性的实验；低成本方法无效就更换方法，不机械重复 GUI 或全量反编译。

按 methods.md 组合静态分析、动态调用观察、断点、文件与数据库差分、网络协议分析、批量输入测试和人工证据。必要时编写新工具；对会改变目标行为的插桩、重签名或补丁，明确记录修改，并在未修改原版上复核外部行为。

使用测试账号、合成文件和隔离目录。修改原版设置前保存原值或快照，测试后恢复。不要把分析中读到的凭据、个人数据或专有资源自动加入交付物。

对已有脚本的常见调用：

```bash
python3 "$SKILL_DIR/scripts/bundle_scan.py" PROJECT_DIR
python3 "$SKILL_DIR/scripts/state_diff.py" snapshot PROJECT_DIR before --path TEST_DIR
# 在原版执行待调查操作
python3 "$SKILL_DIR/scripts/state_diff.py" snapshot PROJECT_DIR after --path TEST_DIR
python3 "$SKILL_DIR/scripts/state_diff.py" diff PROJECT_DIR before after
```

把每条有效结论关联到功能 ID 和证据。其他工具的结果用 `static` 或 `runtime` 等证据类型记录工具、参数、目标版本和输出。只有静态推断时保持 `hypothesis`。

## 5. 实现完整、独立的 B

依据已验证行为选择最适合的架构。原生界面通常可用 SwiftUI + AppKit；复杂编辑器、跨平台原型或已有可靠实现有其他合适技术栈时直接采用。内部结构可以与 A 不同。

使用 Build macOS Apps 时，读取当前可用的 `build-run-debug`、`swiftpm-macos`、`appkit-interop`、`window-management` 等相关 Skills。采用其他技术栈时建立等价的工程、构建、启动、日志和测试入口。保留原版的交互习惯和视觉风格。

允许使用系统框架、开源库、CLI 工具和其他可合法使用的组件，记录来源、版本、许可及修改；从原版提取的资源默认仅作分析证据，纳入可分发 B 前确认使用依据。B 的核心行为必须由交付源码及声明依赖实现，不能调用 A、嵌入 A 的专有核心二进制或通过截图回放代替真实功能。

使用独立 bundle identifier、配置与数据目录。建立可重复构建和启动命令，确认每次运行的是本次构建的 B。实现真实状态转换、文件读写、错误处理、持久化、撤销和恢复；按钮未连通、固定假数据或针对测试输出硬编码都不能算完成。

服务端依赖可以通过公开协议或可控制的自建后端实现，但必须提供真实状态与行为并记录 A/B 差异。确实无法实现的账号、原厂服务、硬件、许可证或 entitlement 保留为阻塞，不隐藏、不改写为成功。

## 6. 对照、回归与独立性验收

对 A 和 B 使用同一组输入与起始状态，比较界面、快捷键、状态转换、输出文件、错误行为、持久化和重启恢复。可结合脚本、GUI 和自动化测试；实现过程中反复调查和修正，直到可访问功能完成验证。细节见 ledger.md。

先保留失败复现，再修复并重跑受影响场景。对子 Agent 的产出执行同样验收。用户反馈进入同一清单并触发回归。

按 reference-app.md 另外验证 B：从交付源码构建；在没有 A、原版私有数据和构造工具的干净 macOS 环境中运行；能加载测试数据、重置初始状态并重放场景。不要为此删除用户正在使用的 A，可使用独立测试机、虚拟机或受控测试环境。未执行的检查保持待验证。

交付前运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR --final`。通过只说明清单约束满足，不证明实际全功能等价或独立运行；有阻塞项就明确报告为带阻塞交付，不能声称全部功能完成。

## 7. 冻结参考实现并交付

在 `reference-manifest.json` 记录 B 的源码位置与版本、构建启动和重置命令、依赖、测试输入、构造方法、A/B 保真度与独立性证据、剩余差异。验收后固定参考版本并记录源码修订和二进制摘要；后续修改产生新参考版本。

交付可运行的 `.app`、完整源码、构建启动方法、测试与重置说明、功能覆盖统计、真实阻塞与差异。源码对 B 是真实实现，对 A 是行为替代实现；不声称恢复了 A 的原始源码。

不自动上传或发布 A 的资源、分析材料和 B 的源码；打包、公证和发布按用户要求执行。
