# 安装准备与连接核对

## 运行方式

本 Skill 面向本地 macOS 上的 Codex。首次使用时在本机运行安装脚本，之后检查并复用已有依赖：

```bash
python3 /absolute/path/replicate-macos-app/scripts/bootstrap.py --check
python3 /absolute/path/replicate-macos-app/scripts/bootstrap.py --install
```

`--check` 不写配置，会运行固定版本的 `rea doctor --client codex --skill`，报告 Codex 中已有的 REA 注册命令、版本和 REA Skill 状态；首次运行会把 `rea-agents` 下载到 npm 缓存。

支持 `--skip-rea`、`--skip-build-skills`。仅在当前会话实际验证相应依赖后跳过。`--with-hopper` 只在用户明确选择安装 Hopper 时添加。

## 自动完成的内容

安装脚本限定配置 Codex 的 REA MCP，并安装包内匹配版本的 `reverse-engineer-anything` 工作流。使用官方 setup 保留无关配置和备份，不覆盖整份 `config.toml`。固定 `rea-agents@6.1.0`。执行 setup 前读取 doctor 报告的 Codex 注册：已注册更新版本，或注册命令中无法确定版本（如 `@latest`、本地路径）时，不执行 setup 并保留现有注册；已注册旧版本时更新为 6.1.0。升级时另行读取当前官方说明并核实版本。

使用 `--with-hopper` 时，REA 在 macOS 上装完 Hopper 后固定返回 `needs_human`，要求用户打开一次 Hopper 选择 Demo 模式或激活许可证。脚本以 doctor 结果判断 Codex 注册和 REA Skill 是否就绪，并把 Hopper 这一步列入 `user_actions`。

下载官方 `build-macos-apps` 的固定 Git revision，将完整插件内容及原有许可声明保存在 `~/.local/share/replicate-macos-app`，再在 `~/.agents/skills` 创建指向 11 个 Skill 的链接。这些链接是用户级安装，对所有项目生效。保留原始名称和参考资料。已有官方插件且全部 Skills 可用时跳过。

| Skill | 使用场景 |
| --- | --- |
| `build-run-debug` | 构建、启动、调试 |
| `swiftpm-macos` | SwiftPM 与 App bundle |
| `swiftui-patterns` | SwiftUI 界面 |
| `appkit-interop` | 菜单、响应链、AppKit 桥接 |
| `window-management` | 窗口、恢复与多窗口 |
| `test-triage` | 测试排查 |
| `telemetry` | 运行日志 |
| `signing-entitlements` | 本地签名与权限 |
| `view-refactor` | View 结构调整 |
| `liquid-glass` | 需要时使用现代视觉 API |
| `packaging-notarization` | 按要求打包与公证 |

## 用户需要开启或准备的内容

| 检查项 | 实际缺失时的用户操作 |
| --- | --- |
| 本地 GUI 控制 | 在桌面客户端 Plugins 中安装或启用 Computer Use，开启 server 和 skill 开关 |
| 系统权限 | 按提示在“系统设置 → 隐私与安全性”授予实际组件屏幕录制和辅助功能权限 |
| App 访问 | 客户端出现提示时允许访问本次目标 App |
| Node.js 与 npm | 安装 Node.js 22.x >=22.19、24.x >=24.11，或稳定版 26+，确认 `node`、`npm`、`npx` 可执行；23、25、prerelease 不支持 |
| Python、git、Swift | 准备 Command Line Tools；需要完整 Xcode 的工程再准备 Xcode。可以提示 `xcode-select --install` 并完成系统安装窗口 |
| 新配置尚未加载 | 重连或重启 Codex，再验证实际工具 |
| 原版尚未可用 | 安装并启动原版，按需要自行完成登录或许可证步骤 |

先完成可自动执行的安装，集中列出真正缺失的用户操作。系统权限需用户亲自授权，不用 TCC 数据库或 `tccutil reset` 自动开启。辅助功能权限与读取 Accessibility Tree 是两件事。

## Readiness 与连接验证

```bash
npm exec --yes --package=rea-agents@6.1.0 -- rea doctor --client codex --skill --format json
npm exec --yes --package=rea-agents@6.1.0 -- rea doctor --provider ghidra --format json
```

按任务限定 doctor 范围。缺失 Hopper 不会阻止无须原生反编译的 bundle、资源和 JavaScript 调查。Hopper/Ghidra 仅在功能调查需要时准备；CLI 启动不证明能分析真实目标。

doctor 检查注册和依赖，无法证明当前会话已加载 MCP。连接后读取真实工具列表，调用一个目标无关或针对已指定 App 的只读操作，不硬编码工具名。再获取 App 画面并在授权范围内操作一次，验证 GUI 能力。

若终端可运行 REA 而桌面客户端报 `npx` 或 `node` 找不到，检查该 MCP 的进程 PATH。只修复该 server 启动路径或 env，保留参数、版本和无关 MCP。重连验证，不重装整套依赖。

## 上游资料

调用 REA 时，以已安装版本和当前会话的工具 schema 为准。

- REA 安装：https://github.com/morluto/rea/blob/main/docs/installation.md
- setup 接口：https://github.com/morluto/rea/blob/main/src/cli/setupCommands.ts
- 开发 Skills：https://github.com/openai/plugins/tree/0722921d5542fc593105c27bd52630babd8b8c2a/plugins/build-macos-apps
- Codex Skills：https://developers.openai.com/codex/skills/
