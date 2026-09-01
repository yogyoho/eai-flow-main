# 架构图总览（L1 → L2 → L3 下钻）

由 archify 生成，全部通过 showcase 质量门 + 4 视口浏览器验证。

| 层次 | 图 | 内容 |
|---|---|---|
| L1 | [l1-system-architecture](l1-system-architecture.html) | eai-flow 系统功能分层（接入/前端/应用/框架/能力/数据） |
| L2 | [l2-harness-architecture](l2-harness-architecture.html) | eaiflow harness（Lead Agent + 分组中间件链 + 子系统） |
| L3 总览 | [geo-report-architecture](geo-report-architecture.html) | geological-report 技能架构（两道门主链） |
| L3 子流程 | [l3a 数据收集→门1](l3a-data-collection-gate1.html) | KF 三件套 → 表单/CSV → ingest → 门1 |
| L3 子流程 | [l3b 冻结→门2](l3b-freeze-calc-gate2.html) | planner + formula_runner → 异常确认 → 冻结 |
| L3 子流程 | [l3c 派发协议](l3c-dispatch-protocol.html) | wave1 全扇出 + wave2 结论 + Iron Law |
| L3 子流程 | [l3d 恢复+终验+修改回路](l3d-recover-finalize-loop.html) | snapshot 验证 → build → consistency → 交付 |

下钻关系：L1 框架层 → L2；L2 Skills/子代理原语 → L3 总览；L3 总览各管线节点 → 对应 l3a–l3d 子流程。

各图 `.spec.json` 为 archify 规格（重渲染/改图用）。
