# 科研交付链

科研交付链把项目中的 Task、报告、文件、证据与导出包组织成可授权、可冻结、可校验的交付物。它的核心不是“打个 ZIP”，而是**冻结选择、记录缺口、授权下载、保留审计**。

> **当前状态**：ProjectDetail 只读聚合、版本化 Manifest、独立 `ProjectExportJob`、ExportSelectionV2 与 JWT 授权下载已接入代码并有隔离验证；功能默认关闭。真实 PostgreSQL/Celery/S3/浏览器验收 **BLOCKED**，未做生产迁移或部署。

## 交付物层级

```text
Project
 ├─ Run                    一次执行上下文（可选）
 ├─ Case / Artifact        协作与产物
 ├─ Report / ReportSnapshot 报告版本与不可变证据快照
 ├─ Evidence / Manifest    证据项、缺口与校验
 └─ ProjectExportJob       冻结导出包（ZIP + Manifest）
       ├─ ExportSelectionV2 显式选择
       └─ 下载授权（JWT）
```

| 概念 | 回答的问题 |
| --- | --- |
| Project | 这批成果属于哪个项目、谁拥有 |
| Run | 哪次执行产生了这些结果 |
| Case/Artifact | 协作过程中的产物与关联 |
| ReportSnapshot | 报告在某一时点的不可变内容 |
| Evidence/Manifest | 哪些事实已验证、哪些缺失、校验值是什么 |
| Export Job | 导出了哪些文件、大小/SHA、何时可下载 |

## ProjectDetail 只读聚合

- 原科研链保留，新增 `ProjectResearchDelivery` 卡片；
- 通过 `research_delivery` 路由获取只读 inventory；
- 按 Task/Report 版本选择和 prepare 预览；
- 默认导出**证据包**；结果包只加入核验过的小型已登记结果；复现材料包只保存已有证据和输入引用；
- Task 归属只来自 `DatasetVersion` / `AnalysisLink` 的明确关联；**不从目录、时间或名称补项目**；
- `truncated` 范围拒绝作为完整导出；必须缩小选择。

## 独立导出 Job

```text
用户选择（ExportSelectionV2）
  → prepare 预览（范围、文件、缺口、预算）
  → ProjectExportJob（冻结 Manifest）
  → queued → collecting → publishing → ready / failed
  → 授权下载（JWT）
```

实现要点：

- 迁移 `projectdelivery01`：`project_export_jobs` 持久冻结 Manifest/状态/发布指纹；`project_export_requests` 保留同一内容共享 Job 的全部 `request_key` 绑定。
- Project 行锁 + 唯一键去重；Worker 独占连接 advisory lock 跨阶段 commit。
- queued outbox + Beat 处理投递与中断恢复。
- 报告、快照、Observation 仍由原体系维护；导出**不重新渲染、不下载、不计算、不补历史环境**。
- 原报告 Job 要求 Task 非空，不用虚构 Task 承载项目 ZIP。

## Manifest 与校验

`ProjectDeliveryManifest` v1 记录：

- 实际文件；
- 引用；
- 缺失；
- 未验证；
- 排除内容。

每个实际字节都有大小与 SHA。报告 ID/version/parent/snapshot/observation 关联冻结并重检。旧 ReportSnapshot 和 ResearchProvenance DTO 默认值不改。

`ExportSelectionV2` / `ProjectDeliveryManifestV2` 进一步：

- 显式绑定 M0 Job / digest 与已发布项目报告的 ReportFile / FileRecord / SHA / size；
- M1 使用独立新 Job、ZIP、摘要；
- 缺 PDF 时保持 `partial`；
- 前端在原项目成果卡片中增加冻结选择、实际状态、sandbox 预览、SHA 下载和 M1 单独确认。

**重要**：项目清单不证明科学复现；Manifest 中 `reproduction_status=NOT_RUN` 必须保留。

## 授权与生命周期

- `ProjectDeliveryService` 在 authorize 时刷新 User/Project 状态；停用/未知项目拒绝读取；`completed` / `handed_over` 保持可读。
- ready 下载会复核冻结摘要、当前 Task→Version→Link 与 Report 关联；后续关系变化**不会悄悄替换旧包**。
- 启用时，有保留 Job 的项目普通删除返回明确 Conflict；关闭独立 flag 可停止新导出，但保留 Job/请求/文件/快照。
- **不得用 drop 表清理交付审计事实**。

## 当前证据与缺口

| 证据 | 状态 |
| --- | --- |
| 隔离验证：Job 状态机、Manifest 冻结、幂等、授权下载 | 已实现/已隔离测试 |
| RI09.5 历史运行：项目汇总 HTML/PDF → M1 ZIP → 完整性校验 → JWT 下载 | 历史 PASS（指定 Run/版本） |
| 真实 PG/Celery/S3/Chromium 全链路 | BLOCKED |
| 非空科研成果（真实 corpus）ZIP | 受 corpus 门禁 BLOCKED |
| 34/34 浏览器断言、FI01–FI06 故障注入 | 未完成（RC04） |
| 独立证据/安全评审 | 未完成 |

不得把“历史项目汇总报告交付”写成“科学分析交付已验收”。

## 修改门禁

1. 改导出范围/选择语义 → 更新 Manifest 与契约测试，验证冻结与重检。
2. 改 Job 状态机 → 验证幂等、advisory lock、outbox 恢复和失败保持原状态。
3. 改下载授权 → 验证 JWT、owner/project、冻结摘要与文件生命周期。
4. 改报告关联 → 保证旧 v1 字段/摘要不变；新语义走 V2。
5. 不得重新渲染历史报告或从当前环境补写历史事实。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 交付服务 | `ProjectDeliveryService` |
| 导出 Job | `ProjectExportJob` / `project_export_jobs` |
| 契约 | `docs/contracts/cygnusx-project-delivery-v1.md` |
| 实施/验收 | `docs/implementation/cygnusx-project-delivery-ri06-ri09-implementation.md`、`docs/audits/cygnusx-project-delivery-runtime-acceptance.md` |
| 报告快照 | `report_snapshot_builder.py`、`report_snapshot_manifest.py` |

## 关联文档

- 权威基线：[`CygnusX_research_delivery_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_research_delivery_architecture.md)
- [报告体系](reports) · [科研计划与科研闭环](plan-and-loop) · [科研能力与证据边界](evidence-boundaries) · [安全模型](../architecture/security-model)
