# 项目记录

## 目录

- [记录文件](#记录文件)
- [入口清单](#入口清单)
- [功能与证据](#功能与证据)
- [场景](#场景)
- [检查与交付](#检查与交付)

## 记录文件

`init_project.py` 在 `replica/` 下创建以下记录，保留已有文件：

- `feature-ledger.json`：原版与系统信息、入口、功能和证据；保持 `schema_version: 4`。
- `scenarios.json`：原版 A 与参考 B 的对照场景；保持 `schema_version: 4`。
- `reference-manifest.json`：B 的源码、构建、依赖、独立性和隔离验收，使用独立的 `schema_version: 1`，详见 `reference-app.md`。
- `progress.md`：当前阶段、下一步、构建命令、等待用户处理的事项和构造记录。
- `evidence/`：包、AX、状态、静态分析、运行时实验、截图、文件和测试输入。
- `scenarios/`：可重放的测试脚本。
- `bin/ax`：可选 AX 工具，默认尝试编译，可用 `--skip-ax` 跳过。

证据路径相对 `replica/`，源码和构建产物的位置写入参考实现清单。具体 App 的全部记录与材料放在私有项目中，不加入公共 Skill 仓库。`.gitignore` 不是访问隔离措施。

## 入口清单

每个 `inventory` 项是可定位的入口，指向一个功能，或用 `skip` 写明由系统提供等原因，二者选一：

```json
{"kind": "menu", "path": "MenuBar > MenuBarItem[文件] > MenuItem[导出为 PDF…]", "feature": "F-001"}
{"kind": "shortcut", "path": "⌥⌘E", "feature": "F-001"}
{"kind": "menu", "path": "MenuBar > MenuBarItem[App 名] > MenuItem[服务]", "skip": "系统提供的服务子菜单，已验证"}
```

AX 可见入口用实际元素路径；其他入口用能定位它的描述，例如 `Dock 菜单 > 新建窗口`。不要求所有入口都通过 AX 发现。

`kind` 的类别如下：

| 类别 | 含义 |
| --- | --- |
| `menu` / `context_menu` | 菜单栏 / 右键菜单 |
| `toolbar` / `window` | 工具栏、标题栏 / 窗口内控件 |
| `settings` / `shortcut` | 设置选项 / 快捷键 |
| `document_type` / `url_scheme` | 打开、导入导出格式 / URL scheme |
| `service` / `applescript` / `app_intent` | 系统服务 / AppleScript 命令 / 快捷指令动作 |
| `drag_drop` / `dock_menu` / `menu_bar_extra` | 拖放 / Dock 菜单 / 菜单栏图标 |
| `extension` / `notification` / `lifecycle` | 扩展 / 通知 / 启动退出、状态恢复、登录时启动 |

每类至少有一个指向功能的入口，或在 `absent_entry_kinds` 写明不存在的依据。只有 `skip` 项的类别同样需要依据。声明没有某类功能前交叉检查可用证据，不能仅因某次扫描失败就写成不存在。

### AX 元素路径

路径以 ` > ` 连接，段为 `Role[标签]` 或 `Role`，同一父元素下重复时追加 `#序号`。标签取 AXTitle 或 AXDescription。菜单项与其子菜单合并为一层。`ax dump` 输出的路径可以直接用于 `ax perform` 和 `ax dump --root`。

## 功能与证据

一个功能是可以独立验证的操作及其结果。同一操作的菜单、快捷键和按钮指向同一功能 ID；不同前置状态写成 `expected` 分支，影响行为的每个设置单独登记。

```json
{
  "id": "F-001",
  "name": "导出为 PDF",
  "preconditions": ["已打开文档"],
  "expected": ["弹出保存面板，默认文件名为文档名", "无文档时菜单项禁用"],
  "persistence": "记住上次导出目录",
  "evidence": [
    {"kind": "ax", "path": "evidence/ax/no-document.txt", "note": "无文档时菜单项 disabled"},
    {"kind": "runtime", "path": "evidence/analysis/export-trace.json", "note": "工具及版本、原版版本、输入、观察到的写入行为"}
  ],
  "status": "observed",
  "blocker": null
}
```

证据类型只描述来源性质，不限制使用哪个工具：

| `kind` | 记录要求 |
| --- | --- |
| `ax` / `state` / `bundle` | 原有脚本或同类输出；`path` 必填 |
| `static` | 任意静态分析、反编译或代码资源解析；`path` 必填，在 `note` 写明方法、版本和结论 |
| `runtime` | 任意运行时分析、插桩、网络/文件观察或受控实验；`path` 必填，写明目标、操作与实际输出 |
| `gui` / `file` / `log` | 原版运行中的截图、输出文件或日志 |
| `rea` | REA 的调查线索，`note` 写 Evidence ID；实际运行结果另外记录为 `runtime` 等 |
| `doc` | 外部资料，提供 `url` 或 `path` |
| `user` | 用户提供的实际操作信息，明确内容与尚未验证的部分 |

所有证据都需要 `note`；填写了 `path` 就必须指向存在的文件。静态资源中的文件不应伪装成原版运行产生的 `file` 证据。保留能复核结论的最小输出，凭据与个人数据先脱敏。

状态规则：

- `hypothesis`：只有静态分析、包、文案或资料线索，尚未确认运行行为。
- `observed`：已确认原版行为，写明 `expected`，至少有一条 `ax / state / gui / file / log / user / runtime` 证据。
- `implemented`：B 中已经连通真实逻辑，不能是占位或硬编码结果。
- `passed`：所有已知预期分支完成对应验证；校验器至少要求一个通过的关联场景，并拒绝仍有失败场景的功能。校验器不自动证明分支穷尽。
- `blocked`：保留功能和未实现分支，`blocker` 填对象 `{"kind": "server", "detail": "具体依赖与已尝试方法"}`。

`blocker.kind` 保留 `account / server / hardware / license / entitlement / user`。缺少某个分析工具先尝试其他方法或在进度中记录待处理，不把工具列表当作不可跨越的边界。非阻塞功能的 `blocker` 为 `null`。

## 场景

```json
{
  "id": "S-001",
  "features": ["F-001"],
  "kind": "script",
  "script": "scenarios/S-001.sh",
  "fixtures": ["evidence/fixtures/sample.md"],
  "start_state": "打开 sample.md，导出目录为空",
  "steps": ["选择 文件 > 导出为 PDF…", "保存到导出目录"],
  "checks": ["菜单项的启用状态", "输出页数与页边距"],
  "original": {"result": null, "evidence": []},
  "replica": {"result": null, "evidence": []},
  "differences": [],
  "status": "pending",
  "blocker": null
}
```

`kind` 为 `script / gui / automated`，状态为 `pending / passed / failed / blocked`。

**script**：可重放脚本，不绑定 AX。脚本路径相对 `replica/`，必须存在且可执行；沿用 `scenarios/S-001.sh BUNDLE_ID OUT_DIR` 接口，分别对 A 和 B 执行。脚本可以使用 AX、AppleScript、CLI、协议或其他适合的方式，但必须真正驱动目标行为。

**gui**：用实际画面和输入验证布局、焦点、拖放、动效等。两边都保存截图，统一语言、外观、缩放和窗口条件。Computer Use 是默认能力，也可采用能提供等价证据的方法；不能因为 AX 结构一致就声称视觉一致。

**automated**：检查 B 的算法、格式、持久化与边界输入。预期结果必须有原版证据或明确的行为规格依据，不能用 B 自己生成的输出证明 B 正确。

### 比较与回归

相同 fixtures 分别复制到 A 和 B 的隔离目录，先恢复起始状态，再比较输出内容、命名、顺序、窗口、提示、保存和恢复。对不可直接二进制比较的文件，解析内容并注明允许的非语义差异。

`ax perform` 后等待界面达到可观察的稳定状态，再导出证据；原有简单场景可短暂等待，但不能把固定延时当成操作成功的证明。`state_diff.py` 可记录两次操作间的偏好和文件变化，复杂格式可另写解析器。

通过场景要求两边都有 `result`、`differences` 为空；`script` 与 `gui` 两边各有至少一个存在的证据文件。失败时记录差异并保留复现，修复后重跑此场景及受影响场景。已知未解决差异不能通过归一化或删除检查隐藏。

## 检查与交付

开发中运行 `python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR` 检查结构与关联。`entry_kinds.unchecked` 表示既未覆盖也无不存在依据的类别。

交付前加 `--final`：功能和场景均非空，每项为 `passed` 或 `blocked`，`unchecked` 为空。报告总数、通过数和阻塞数，不将阻塞算成已复现。程序检查不证明已发现所有功能，也不检查真实 App 执行或 `reference-manifest.json` 的独立性声明。

另按 `reference-app.md` 完成 B 的独立构建运行、重置、冻结和隔离记录；尚未实际验证的项目保持待验证。用户体验反馈加入原有功能与场景，保留稳定 ID，不另起一套无法回归的记录。