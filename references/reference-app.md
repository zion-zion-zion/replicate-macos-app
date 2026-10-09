# B 的构建记录、独立运行验收与冻结

## reference-manifest.json

这个文件记录 B 怎样构建、用了哪些组件、验收到什么程度。`init_project.py` 创建它，已有内容保持不变。`schema_version` 为 1，和功能清单的版本号各自独立。尚未核实的字段保留 `null` 或空数组。

这个文件由你按实际验收结果维护，`ledger_check.py` 不读取它。

| 字段 | 内容 |
| --- | --- |
| `role` | 固定为 `reference_app_construction` |
| `original` | A 的路径、bundle identifier、名称、版本和构建号 |
| `created_at` | 文件生成时间（UTC） |
| `reference` | B 的名称、bundle identifier、源码目录与修订、构建产物、构建/启动/重置命令、fixtures 和依赖 |
| `construction.methods` | 实际使用的方法、工具版本、用途和证据位置 |
| `construction.components` | 使用的第三方组件或资源：来源、版本、使用依据和修改情况 |
| `verification.fidelity` | B 与 A 行为对照的验收状态和证据 |
| `verification.independence` | 在没有 A 和 A 私有数据的环境中，B 独立构建运行的验收状态和证据 |
| `verification.reset` | 重置状态后重放场景的验收状态和证据 |
| `verification.known_differences` | 尚未解决的差异及对应功能 ID，包括服务端和权限造成的阻塞 |
| `freeze` | 冻结的版本号、冻结时间、源码修订、最终制品的 SHA-256 |

填写规则：

- `fidelity`、`independence`、`reset` 三项的 `status` 取 `pending / passed / failed / blocked`；`evidence` 是相对 `replica/` 的文件路径列表；失败或阻塞的原因写进 `notes`。
- `reference.source_dir` 和 `reference.artifact_path` 填相对项目根目录的路径；交付说明里写清执行各条命令时所在的目录。

## 独立运行验收

目的：证明拿到交付源码的人，在一台没有 A 的 Mac 上也能构建并使用 B。

1. **构建**：在干净环境中，用交付源码和固定版本的依赖构建 B。记录完整的构建命令、依赖、目标架构和产物位置。交付物必须能从源码重新构建。
2. **运行环境**：准备一台没有 A、没有 A 的私有数据库和缓存、没有调查期插桩、也没有开发机隐式依赖的 macOS，例如独立测试机或虚拟机。用户日常使用的 A 保持原样。
3. **独立性检查**：确认 B 运行时不会启动 A，不连接开发机上的 A 服务，也不加载 A 的核心二进制。
4. **功能检查**：声明 B 需要的系统权限、外部库和服务；测试可重置的本地状态、文件输出、重启恢复和核心用户流程。验收时可以联网。
5. **重置与重放**：从相同的 fixtures 重置状态并重放场景。记录会影响结果的条件，例如时间、随机数、语言、系统外观、窗口尺寸和网络数据。真实的功能差异如实记入 `known_differences`。

没有做干净环境测试时，`independence.status` 保持 `pending`，交付时向用户说明。

## 冻结

冻结就是把验收通过的 B 固定成一个版本：

1. 记录源码修订，例如 git commit。
2. 对可分发的制品（例如只包含 B 的 `.app` 的归档）计算 SHA-256，并写明计算的是哪个文件。
3. 填写 `freeze` 中的版本号和冻结时间。

每个版本对应一次具体的构建。修复 B 之后产生新版本，并重跑相关验收。
