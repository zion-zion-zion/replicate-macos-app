# 功能证据、场景与复刻验收

## 功能盘点

给功能稳定 ID。记录入口、目标、输入、前置状态、结果、状态变化、持久化、副作用、异常分支与证据。设置名称、快捷键、拖拽和弹窗也是规格。

```json
{
  "id": "F-001",
  "name": "功能名称",
  "entry": "菜单或窗口入口",
  "input": {},
  "preconditions": [],
  "expected": [],
  "persistence": "unknown",
  "evidence": [{"kind": "gui", "path": "evidence/F-001.png", "note": "实际观察"}],
  "investigation_status": "hypothesis",
  "implementation_status": "pending",
  "validation_status": "pending",
  "blocker": null
}
```

调查状态用 `hypothesis / observed / verified / blocked`，实现状态用 `pending / implemented / blocked`，验证状态用 `pending / passed / failed / blocked`。静态推断保持 `hypothesis`，实际验证后调整；保留旧 ID 和证据。

扫描全部可见入口，把 REA 新发现追加进去。报告已发现、验证和阻塞的数量，以清单界定覆盖，不默默删除未完成分支。

## 场景与差异检查

记录关联功能、测试文件、起始状态、步骤、观测点、预期输出、清理方式、原版结果、复刻版结果及差异。相同输入分别放入隔离目录，比较内容、命名、顺序、窗口、提示、保存与恢复行为。

修复前保留复现。修改后重跑对应场景及直接受影响的行为。精确文件与算法用程序断言，用户可见行为用 GUI 实测；编译通过不等于行为通过。

## REA 调查

先提出有功能意义的问题，如“冲突文件如何处理”。查对应资源、字符串、符号、事件或格式，保留位置和来源，用自己的代码实现已验证行为。出现系统框架与第三方库时收窄范围。GUI 与资源无法解释时追加深度分析；新发现形成可验证场景。

## 交付条件

正常可访问功能完成实现和验证；启动本次构建的 `.app`；数据与原版隔离；源码可重复构建；错误和边界已检查；阻塞或差异明确记录；用户无需逐项追加范围内功能。

`replica/progress.md` 保留准备、探索、调查、实现、验证结果与继续入口。原版截图和测试输入只存入项目证据目录，不混入可分发 Skill。
