# 参考 App 的验收与冻结

## reference-manifest.json

`init_project.py` 为新旧项目补建此文件，不覆盖已有内容。`schema_version` 为 1，与功能清单的版本独立。字段尚未核实时保留 `null` 或空数组。

| 字段 | 填写内容 |
| --- | --- |
| `role` | 固定为 `reference_app_construction` |
| `original` | A 的路径、bundle identifier、名称、版本和构建号 |
| `created_at` | 本地生成记录的 UTC 时间 |
| `reference` | B 的名称、bundle identifier、源码目录与修订、构建产物、构建启动和重置命令、fixtures 与依赖 |
| `construction.methods` | 实际使用的方法、工具版本、目的、证据位置 |
| `construction.components` | 使用的第三方组件或资源、来源、版本、使用依据和修改情况 |
| `verification.fidelity` | A/B 行为差分验收的状态和证据 |
| `verification.independence` | 无 A 与原版私有数据时，B 独立构建运行的状态和证据 |
| `verification.reset` | 重置后可重放场景的状态和证据 |
| `verification.known_differences` | 尚未解决的差异与功能 ID，不隐藏服务端或权限阻塞 |
| `freeze` | 参考版本、冻结时间、源码修订、最终可运行制品的 SHA-256 |

`verification` 下三项的 `status` 使用 `pending / passed / failed / blocked`，`evidence` 使用相对 `replica/` 的文件路径列表。失败或阻塞写入对应 `notes`。`reference.source_dir` 和 `artifact_path` 写相对项目根目录的路径；执行命令的工作目录也必须在交付说明中注明。包含密码或 token 的值不得写入清单。

## 独立性验收

1. 用交付源码和固定依赖在干净环境中构建 B，记录完整构建命令、依赖、目标架构和产物。不能只交付一份无法重建的 `.app`。
2. 在没有 A、原版私有数据库和缓存、构造期插桩以及开发机隐式依赖的 macOS 环境中启动 B。使用独立测试环境，不删除用户日常安装的 A。B 不能间接启动 A、连接构造者机器上的原版服务，或依赖原版核心二进制。
3. 声明 B 正常需要的系统权限、外部库及可控制的服务；测试可重置的本地状态、文件输出、重启恢复和核心用户流程。联网是显式依赖，不必为了验收强行禁网，但不得用原厂私有后端替代自己尚未实现的核心功能。
4. 从相同 fixtures 重置并重放场景。将时间、随机性、语言、系统外观、窗口尺寸和网络数据等影响结果的条件记录清楚；不能随意归一化真实功能差异。

没有执行干净环境测试时，`independence.status` 保持 `pending`，交付时明确。清单校验器不验证 App 实际行为，也不自动检查本清单；人工或自动化验收必须有真实输出。

## 冻结

完成验收后固定 B 的源码修订和可运行制品，填写 `freeze`。对可分发制品（例如只包含 B 的 `.app` 的归档）计算 SHA-256，记录被摘要的确切文件；不要把不同的本地构建混为同一参考版本。修复 B 后更新参考版本并重跑相关验收。
