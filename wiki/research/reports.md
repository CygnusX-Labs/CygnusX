# 报告体系

CygnusX 有**三类报告产物**，来源与可信边界不同：

| 类型 | 来源 | 用途 | 当前边界 |
| --- | --- | --- | --- |
| 科学报告（BioReport） | 独立 Python/Quarto 报告引擎 | 生信分析的科学解释与图表 | 引擎独立发展；平台适配器与完整 RNAFlow → BioReport 链路未验收 |
| 可复现性报告 | 平台报告 Job（`report_kind=reproducibility`） | 任务证据、环境、缺口与校验 | 已实现，隔离验证；真实 RNA/PG/Celery E2E 未验收 |
| 交付包 | 平台交付导出（`report_kind=delivery`） | ZIP + Manifest + 校验值 | 见[科研交付链](delivery)；真实环境验收 BLOCKED |

不要把“项目汇总报告”当成科学报告，也不要把报告 READY 当成科研结论已验证。

## 报告 Job 架构

```text
Task（必需身份） + 可选 Run
  → ReportSnapshot（REPEATABLE READ 只读事务）
       ├─ 稳定事实 + digest
       ├─ owner_allowlist v2 脱敏
       └─ 缺口显式记录
  → ReportJob 状态机
       queued → collecting → rendering → publishing → ready / failed
  → 原子发布到项目 Run 目录
       projects/<safe>/runs/audit-report-<UTC>/output/index.html
  → ReportService + FileRegistry 同一事务登记
```

| 机制 | 作用 |
| --- | --- |
| 不可变快照 | 报告内容对应冻结事实，不随后续数据变化 |
| `stable_facts` digest | 检测快照一致性 |
| `pg_try_advisory_lock(hash(Task ID))` | 同一 Task 的并发报告串行化 |
| durable outbox + Beat | 投递与中断恢复 |
| 原子归档 | 先写临时目录，再原子发布 |
| 同一事务登记 | 报告记录与文件登记一致 |

## 证据状态

报告中的事实必须标记状态，不能把缺失写成正常：

| 状态 | 含义 |
| --- | --- |
| `verified` | 有当前证据并通过校验 |
| `not_recorded` | 当时未记录 |
| `unavailable` | 当前不可获取 |
| `not_applicable` | 不适用 |
| `verification_failed` | 校验失败 |
| `estimated` | 估算值，非实测 |

自由文本 claim 的 `claim_text_verified` 恒为 false；`cygnusx.claim_provenance.v1` 区分：

- `VERIFIED_VALUE`：有可验证值；
- `SUPPORTED_CLAIM`：有限数值陈述有支持；
- `AI_INTERPRETATION`：AI 解释草稿；
- `NOT_VERIFIED`：未验证/缺失。

没有新增 Claim 表或 Claim 引擎；Claim 引用存在不等于科学事实已验证。

## 交付包与 partial

- 交付 ZIP + Manifest + checksums；缺 PDF 或其他必需项时保持 `partial`。
- 部分语义必须显式展示，不能用“成功”掩盖缺口。
- `reproduction_status=NOT_RUN` 表示未执行复现，不是复现失败。

## RI09.5 原型边界

RI09.5 在 `report_audit_renderer` 中提供了 **14 章静态 HTML 原型**，复用原转义/表格/CSP/CSS；相同合成快照的旧审计 HTML 逐字节相同。

原型做到：

- `GET` 原 ProjectExportJob 的 `summary-preview`：验证当前权限、原导出 flag 与冻结范围；
- 默认只显示已有引用/文件/缺口，未知科学事实明确 `NOT_RECORDED`；
- 前端空 sandbox iframe 预览。

原型**没有**：

- 新建报告 Job、Report、PDF 或 FileRecord；
- 更新旧 ZIP/Manifest；
- 形成正式科学报告。

正式项目报告设计见 `docs/design/cygnusx-project-scientific-summary-report.md`；不能把原型等同正式科学报告。

## 报告与 Run 的关系

- 报告以 Task 为必需身份，Run 可选；没有 Run 的普通 Task 仍可生成可复现性报告。
- 报告不负责下载、重算或补历史环境；缺失环境/输入身份/工具调用/QC 决策显式记录为缺口。
- 报告快照冻结后，冻结序列化和事实摘要用于后续校验。

## 运行边界

| 项 | 状态 |
| --- | --- |
| 报告 Job/快照/HTML/API | 已实现，隔离验证 |
| 真实 RNA Task + PostgreSQL + Celery 报告 E2E | 未验收 |
| 科学 BioReport 完整链路 | 未验收 |
| 非空科研 corpus 导出 | BLOCKED |
| 报告 READY 作为科学结论 | **不允许** |

## 修改门禁

1. 改快照来源 → 保证只读、可重复、缺口显式；不得从当前环境补写历史。
2. 改证据状态 → 同步前端与 Manifest，保持六态语义。
3. 改报告 Job → 验证幂等、advisory lock、outbox 恢复、原子发布与事务登记。
4. 改报告内容 → 区分平台事实、外部来源与 AI 解释，避免把解释写成已验证事实。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 快照协议 | `application/schemas/report_snapshot.py` |
| 快照构建 | `application/services/report_snapshot_builder.py`、`report_snapshot_sources.py` |
| 清单/指纹 | `application/services/report_snapshot_manifest.py` |
| 报告服务 | `ReportService` + `api/v1/reports*` |
| RI09.5 原型 | `report_audit_renderer`、`projectreport01` 迁移 |

## 关联文档

- 权威基线：[`CygnusX_report_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_report_architecture.md)
- [科研交付链](delivery) · [科研计划与科研闭环](plan-and-loop) · [科研能力与证据边界](evidence-boundaries)
- [流程监控面板](../features/workflow-monitor)
