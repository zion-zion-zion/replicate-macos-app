# 功能清单、证据与场景

## 目录

- [记录文件](#记录文件)
- [入口清单](#入口清单)
- [静态线索](#静态线索)
- [功能](#功能)
- [证据](#证据)
- [场景](#场景)
- [检查](#检查)

## 记录文件

`init_project.py` 在 `replica/` 下创建以下内容，已存在的文件保持原样：

| 路径 | 内容 |
| --- | --- |
| `feature-ledger.json` | 功能清单：A 和系统的版本信息、入口、静态线索、功能和证据，`schema_version` 为 5 |
| `scenarios.json` | A 与 B 的对照场景，`schema_version` 为 5 |
| `reference-manifest.json` | B 的源码、构建、依赖、验收和冻结记录，`schema_version` 为 2，见 reference-app.md |
| `progress.md` | 当前阶段、下一步、构建命令、等待用户处理的事项和工作记录 |
| `evidence/` | 证据文件：`bundle/` 是包扫描结果，`ax/original/` 是 A 的 AX 导出，`runs/` 是场景运行记录；状态快照、分析输出、截图、测试输入等按需建子目录 |
| `scenarios/` | 可重放的场景脚本 |
| `bin/ax` | AX 工具，`--skip-ax` 时不编译 |

证据和脚本的路径都相对 `replica/` 填写。

旧项目升级到当前版本：两个记录文件的 `schema_version` 改为 5，功能清单加 `"clues": []`；`reference-manifest.json` 的 `schema_version` 改为 2，`freeze` 加 `"artifact": null`；旧的 AX 导出没有头部行，用重新编译的 `bin/ax` 重新导出。

## 入口清单

`inventory` 中每一项是一个能找到的入口，例如一个菜单项、一个快捷键或一个按钮。每项在下面两个字段中选一个填写：

- `feature`：这个入口触发的功能 ID。
- `skip`：不登记为功能的原因，例如“系统提供的服务子菜单，已检查行为”。

```json
{"kind": "menu", "path": "MenuBar > MenuBarItem[文件] > MenuItem[导出为 PDF…]", "feature": "F-001"}
{"kind": "shortcut", "path": "⌥⌘E", "feature": "F-001"}
{"kind": "menu", "path": "MenuBar > MenuBarItem[App 名] > MenuItem[服务]", "skip": "系统提供的服务子菜单，已检查行为"}
```

`path` 的写法：AX 能读到的入口，从 A 的 `ax dump` 输出中原样复制元素路径；其他入口写一段能定位它的描述，例如 `Dock 菜单 > 新建窗口`。以 `MenuBar`、`Window`、`Menu`、`Sheet` 开头的 `path` 按 AX 路径校验，必须出现在 A 的 AX 导出中。

`kind` 的取值：

| 类别 | 含义 |
| --- | --- |
| `menu` / `context_menu` | 菜单栏 / 右键菜单 |
| `toolbar` / `window` | 工具栏、标题栏 / 窗口内控件 |
| `settings` / `shortcut` | 设置选项 / 快捷键 |
| `document_type` / `url_scheme` | 打开、导入、导出的文件格式 / URL scheme |
| `service` / `applescript` / `app_intent` | 系统服务 / AppleScript 命令 / 快捷指令动作 |
| `drag_drop` / `dock_menu` / `menu_bar_extra` | 拖放 / Dock 菜单 / 菜单栏图标 |
| `extension` / `notification` / `lifecycle` | 扩展 / 通知 / 启动、退出、状态恢复、登录时启动 |

每个类别满足以下一种情况：

- 至少有一个入口指向功能；
- 在 `absent_entry_kinds` 中写明 A 没有这类入口的依据。

只有 `skip` 项的类别也需要写依据。依据来自交叉核对过的多种证据，单次扫描为空不足以作为依据。

### AX 元素路径

- 路径由 ` > ` 连接的段组成，每段写作 `Role[标签]`，没有标签时只写 `Role`。
- 标签取元素的 AXTitle，没有时取 AXDescription。
- 同一父元素下出现相同的段时，按顺序追加 `#1`、`#2`。
- 菜单项和它展开的子菜单合并成一段。
- `ax dump` 输出的路径可以原样传给 `ax perform` 和 `ax dump --root`。

### AX 覆盖

`ledger_check.py` 在 `evidence/` 下查找第一行为 `# ax-dump {...}`、且 bundle identifier 属于 A 的文件，作为 A 的 AX 导出。头部 JSON 记录 bundle identifier、版本、构建号、进程号、`--root` 和导出时间；自己解析导出时跳过这一行。

- 导出的版本或构建号与功能清单的 `app` 不一致时报错。A 升级后重新导出。
- A 的导出中每个可操作元素（菜单项、按钮、复选框、单选按钮、弹出按钮、输入框、滑块、链接等）都要在 inventory 中有同路径的入口。不计入的元素：Apple 菜单、没有标签的菜单项（分隔线）、窗口的关闭/最小化/缩放/全屏按钮、表格/列表/大纲等数据容器内随数据生成的元素。
- `skip` 入口连同它下面的子元素一起算作已登记，例如系统提供的「服务」子菜单只登记一条 `skip`。
- 输出的 `ax` 给出导出文件、可操作元素总数、已登记数和未登记数；`uncovered_entries` 列出前 20 个未登记元素和建议的 `kind`，加 `--uncovered` 列出全部。
- AX 确实读不到 A（例如整个界面自绘）时，在功能清单顶层写 `"ax_unavailable": "原因和已尝试的方法"`，并用 GUI 清点补齐入口。

## 静态线索

`clues` 记录 `bundle.json` 中可能对应功能的组件，让只在包里出现、界面上一时没找到的功能也进入清单。每项填 `source` 和 `name`，再在 `feature` 和 `skip` 中选一个：

```json
{"source": "nib", "name": "Contents/Resources/HexEditor.storyboardc", "feature": "F-021"}
{"source": "framework", "name": "Sparkle.framework", "skip": "A 的自动更新，B 不实现"}
```

| `source` | `bundle.json` 中的字段 | `name` |
| --- | --- | --- |
| `nib` | `resources.nibs` | 原样复制路径 |
| `framework` | `stack.embedded_frameworks` | 原样复制 |
| `xpc` / `extension` | `entries.xpc_services` / `entries.extensions` | 各项的 `name` |
| `helper` / `plugin` | `entries.helpers` / `entries.other_plugins` | 原样复制 |
| `library` | `entries.library` | `文件夹/名称` |
| `app_intent` | `entries.app_intents` | 各项的 `id` |
| `database` / `data_model` | `resources.sqlite_databases` 的键 / `resources.core_data_models` | 原样复制路径 |

找到线索对应的界面后，把入口也登记进 inventory。`ledger_check.py` 输出的 `clues.unmapped` 列出 `bundle.json` 里还没登记的线索；`clues` 中有 `bundle.json` 里不存在的项时报错。

## 功能

一个功能是一次可以单独验证的操作及其结果。

- 同一操作的菜单项、快捷键和按钮指向同一个功能 ID。
- 不同前置状态下的结果，写成 `expected` 里的不同条目。
- 每个影响行为的设置单独登记为功能。
- 名称里用「、」「和」「与」连接几个操作时，拆成几个功能；同一窗口或面板里彼此独立的工具也分别登记。
- 功能和场景的 ID 分配后保持不变；用户反馈的问题加进原有的功能和场景。

```json
{
  "id": "F-001",
  "name": "导出为 PDF",
  "preconditions": ["已打开文档"],
  "expected": ["弹出保存面板，默认文件名为文档名", "无文档时菜单项禁用"],
  "persistence": "记住上次导出目录",
  "evidence": [
    {"kind": "ax", "path": "evidence/ax/original/no-document.txt", "note": "无文档时菜单项 disabled"},
    {"kind": "runtime", "path": "evidence/analysis/export-trace.json", "note": "工具及版本、A 的版本、输入、观察到的写入行为"}
  ],
  "status": "observed",
  "blocker": null
}
```

### 状态

| `status` | 什么时候用 | 校验器的要求 |
| --- | --- | --- |
| `hypothesis` | 只有静态分析、包内容、文案或资料线索，还没确认运行行为 | 无 |
| `observed` | 已在 A 上确认行为 | 写明 `expected`；至少一条运行时证据（`ax / state / run / gui / file / log / user / runtime`） |
| `implemented` | B 中已连上真实逻辑 | 同 `observed` |
| `passed` | 所有已知的 `expected` 条目都验证过 | 至少一个关联场景为 `passed`，且没有 `failed` 的关联场景 |
| `blocked` | 受外部条件阻塞，暂时无法实现或验证 | `blocker` 填 `{"kind": "server", "detail": "具体依赖和已尝试的方法"}` |

- `blocker.kind` 取值 `account / server / hardware / license / entitlement / user`。其他状态的 `blocker` 为 `null`。
- 缺少某个分析工具时，换一种方法，或在 `progress.md` 记为待处理，功能状态保持不变。
- 校验器只检查上表的条件；`expected` 是否已经涵盖所有分支，由你核对。

## 证据

`kind` 说明证据的来源：

| `kind` | 内容与要求 |
| --- | --- |
| `ax` | `ax dump` 的逐行输出，第一行是 `# ax-dump` 头部；`path` 必填 |
| `state` | `state_diff.py` 的快照或差分 JSON；`path` 必填 |
| `run` | `scenario_run.py` 生成的 `run.json`；`path` 必填 |
| `bundle` | `bundle_scan.py` 的输出；`path` 必填 |
| `static` | 任意静态分析、反编译或代码资源解析；`path` 必填，`note` 写明方法、工具版本和结论 |
| `runtime` | 任意运行时分析、插桩、网络或文件观察、受控实验，以及其他工具的 AX 或状态输出；`path` 必填，`note` 写明目标、操作和实际输出 |
| `gui` / `file` / `log` | A 运行时的截图、输出文件或日志 |
| `rea` | REA 给出的调查线索，`note` 写 Evidence ID；在 A 上实际运行的结果另外登记为 `runtime` 等 |
| `doc` | 外部资料，提供 `url` 或 `path` |
| `user` | 用户提供的实际操作信息，写明内容和尚未验证的部分 |

- 每条证据都要有 `note`；填了 `path` 就必须指向存在的文件。
- 证据文件保存工具的原始输出，对输出的解读和结论写在 `note` 里。
- A 包内的静态资源登记为 `bundle` 或 `static`；`file` 只用于 A 运行时产生的文件。
- `ax`、`state`、`run` 证据带有 App 身份，校验器据此核对来源：功能的证据和场景的 `original` 来自 A；场景的 `replica` 来自 B，`reference-manifest.json` 填了 `reference.bundle_id` 时按它核对。`run` 证据还核对所属的一侧和场景 ID。

## 场景

场景是在 A 和 B 上执行同一组操作并比较结果的测试。

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

`original` 记录 A 的结果，`replica` 记录 B 的结果。`status` 取值 `pending / passed / failed / blocked`。`fixtures` 中的路径相对 `replica/`，必须存在。`kind` 有三种：

- **`script`**：可重放的脚本。脚本路径相对 `replica/`，文件必须存在且可执行。脚本按 `BUNDLE_ID` 和 `APP_PATH` 驱动被测 App（AX、AppleScript、`open -a`、CLI、协议等），把观察到的结果写进 `OUT_DIR`；`OUT_DIR` 里的结果来自被测 App 的实际行为。用法见下文「运行 script 场景」。
- **`gui`**：用实际画面和输入验证布局、焦点、拖放、动效等。两边都保存截图，并统一语言、外观、缩放和窗口条件。默认用 Computer Use，也可以用能给出同等证据的方法。视觉是否一致以截图对比为准。
- **`automated`**：检查 B 的算法、格式、持久化和边界输入。预期结果来自 A 的证据或明确的行为规格。

### 比较方法

- 把相同的 fixtures 分别复制到 A 和 B 的隔离目录，先恢复起始状态，再比较输出内容、命名、顺序、窗口、提示、保存和恢复。
- 不能直接按字节比较的文件，解析内容后再比较，并注明允许的非语义差异。
- App 名称出现的位置（App 菜单标题、关于窗口、窗口标题等）两边各显示自己的名称，这是预期结果，比较时把 A 的名称和 B 的名称视为相同。场景脚本里含 App 名称的 AX 路径（如 `MenuBarItem[App 名]`）按被测 App 的名称填写。
- `ax perform` 之后，等界面进入可观察的稳定状态再导出证据。操作是否成功以导出的状态为准。
- `state_diff.py` 可以记录两次操作之间偏好设置和文件的变化；复杂格式可以另写解析器。

### 运行 script 场景

```bash
python3 "$SKILL_DIR/scripts/scenario_run.py" PROJECT_DIR S-001                    # 依次运行 A 和 B
python3 "$SKILL_DIR/scripts/scenario_run.py" PROJECT_DIR S-001 --side original    # 只运行一侧
```

- 运行前核对 A 的 `.app` 与功能清单 `app` 的 bundle identifier、版本和构建号一致，B 的 `.app`（`reference-manifest.json` 的 `reference.artifact_path`）与 `reference.bundle_id` 一致。
- 脚本的调用方式为 `scenarios/S-001.sh BUNDLE_ID APP_PATH OUT_DIR`，工作目录是 `replica/`，环境变量 `REPLICA_SIDE` 为 `original` 或 `replica`。
- 每一侧的输出放在 `evidence/runs/S-001/<side>-<UTC 时间>/`：`run.json`（App 身份、脚本 SHA-256、参数、起止时间、退出码、是否超时、输出文件列表）、`stdout.txt`、`stderr.txt`，以及脚本写进 `OUT_DIR` 的文件。
- 两侧都运行时，输出的 `compare` 列出内容相同、不同和只在一侧出现的文件；`runs.<side>.evidence` 可以直接填进场景对应一侧的 `evidence`，再补上 `note`。
- 任一侧退出码非 0 或超时（`--timeout`，默认 600 秒）时以 1 退出。

### 场景状态的要求

- `passed`：两边都有 `result`，`differences` 为空；`original` 至少有一条运行时证据（`ax / state / run / gui / file / log / user / runtime`）；`script` 和 `gui` 场景两边各至少有一个存在的证据文件；`script` 场景两边各有一条退出码为 0 的 `run` 证据，且记录的脚本 SHA-256 与当前脚本一致，脚本修改后重新运行。
- `failed`：在 `differences` 写明差异，并保留能复现的输入。
- 已知的差异一直留在 `differences` 中，直到 B 真正修复；`checks` 和归一化规则只在 A 的行为证据表明需要时修改。

## 检查

开发中运行：

```bash
python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR
python3 "$SKILL_DIR/scripts/ledger_check.py" PROJECT_DIR --uncovered   # 列出全部未登记的 AX 元素
```

它读取 `feature-ledger.json`、`scenarios.json`、`evidence/` 下 A 的 AX 导出和 `evidence/bundle/bundle.json`，`reference-manifest.json` 存在时也读取。输出包括：

- `inventory`：入口总数、指向功能的数量和 `skip` 数量；
- `ax`：A 的 AX 覆盖情况，见「AX 覆盖」；
- `clues`：`bundle.json` 中的线索数、已登记数和 `unmapped`；
- `features`、`scenarios`：按状态计数；
- `entry_kinds.unchecked`：既没有入口指向功能、也没写不存在依据的类别；
- `reference`：B 的名称、bundle identifier、三项验收状态和是否已冻结；
- `errors`：全部错误，有错误时以 1 退出。

交付前加 `--final`，额外要求：

- 功能和场景都不为空，每个功能和场景都是 `passed` 或 `blocked`；
- `entry_kinds.unchecked` 为空；
- 有 A 的 AX 导出（或写明 `ax_unavailable`），且 `ax.uncovered` 为 0；
- 有 `bundle.json`，且 `clues.unmapped` 为空；
- `reference-manifest.json` 满足 reference-app.md 的交付要求。

汇报时分别给出总数、通过数和阻塞数，以及 AX 覆盖和静态线索的统计。

校验器检查记录的结构、关联和证据来源。功能有没有找全、B 的实际表现如何，由调查和对照验证确认。
