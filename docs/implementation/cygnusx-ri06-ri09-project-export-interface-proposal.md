# RI06–RI09 项目追溯与导出最小接口建议

状态：只读源码核查及设计，本轮没有实现项目导出、启动导出Job或执行归档。没有生产DB盘点，不报告真实孤立记录数量。

## 已有可信关系与缺口

| 链路 | 权威来源 | 限制 |
|---|---|---|
| Project→Dataset | datasets.project_id + user_id | 每次确认owner/模块/项目当前访问权 |
| Dataset→Version | dataset_versions.dataset_id | 不可按目录或“当前版本”替代指定版本 |
| Version→分析Task | dataset_analysis_links.version_id/task_id/flow_id | task_id可空；Handoff是输入冻结，不是实际发布/镜像证明 |
| Task→Report | reports.task_id/user_id | Task自身没有project_id；不能遍历owner全部Task当成项目任务 |
| Report→Snapshot | reports.snapshot_id，snapshot.user_id/task_id/digest | 历史报告可无Snapshot；冻结摘要和内容需校验 |
| Report→ResultObservation | reports.result_observation_id | 与Task/owner/适用版本核验；采集时校验不是执行全过程证明 |
| Run→Task | platform_runs.task_id + user_id/flow_id/confirmed_at | project_slug不是强Project外键；删除/重命名和历史弱关联需明确 |
| 文件→Task | file_records.task_id/user_id/source/checksum | 身份缺失或字节不一致不能自动接管 |

`ProjectOverviewService` 会扫描 runs 目录，这是展示投影，不能单独证明归属。已有 `ResearchProvenanceService.project` 只读聚合 Dataset 链并有20个dataset、5个version等界限，truncated必须保留；不能用这个有界响应直接宣称完整项目导出。

## RI06：只读覆盖清单

优先扩展现有项目research-delivery接口的分页能力，或新增同服务的只读 `GET /projects/{project_id}/evidence-inventory`（提案，未实现）。输入仅project_id、游标和有界page_size；身份来自JWT，不收客户端verified/owner/Task路径。

输出建议：schema_version、project_id、capture_id/watermark、items[]（类型、真实ID、显式association_source、integrity、missing_evidence）、next_cursor、truncated、coverage。分开标识 EXPLICIT_DATASET_LINK、CONFIRMED_RUN_DECLARATION、UNASSOCIATED；后两者不能悄悄升级强关联。状态变化时重新读取；删除/撤权返回拒绝，不泄漏其他项目对象ID。

普通Task无可信项目关联、无报告快照、有目录无Task、失败/取消/进行中Task、重复Run、已删除项目、未知输入/发布/镜像，都保留为缺口或独立待核查项。不得按task_name/work_dir字符串自动补项目关系。

## RI07：冻结项目Manifest

未来只读预览 `GET /projects/{id}/export-preview` 复用盘点，明确 selection（指定DatasetVersion/Task/Report及版本）、预计大小、排除/缺失项、是否truncated。manifest建议包含owner scope、capture watermark、每项ID/关联来源/SHA/大小、单任务交付包引用、协议版本、missing_evidence、privacy/redaction策略；不复制凭据、宿主路径或未审阅聊天全文。

冻结对象集合与发布前实际字节分开：预览不是归档，hash不是权限。字段变化后产生新manifest版本/摘要，不覆盖旧归档。缺关联、缺字节、缺snapshot时 partial；分页未遍历完不能宣布complete。

## RI08：复用单任务交付包的Job边界

未来 `POST /projects/{id}/exports` 输入冻结selection摘要、request_key和人类批准凭证；在原Job/存储/鉴权模式上评审最小协调职责，不创建虚假Task来满足Report.task_id非空，也不把项目包冒充单任务Report。

优先引用/封装原 `ReportService.build_delivery_package` 已校验制品及manifest；原内存builder有上限，项目级必须做有界流式写入、总字节/文件数/并发配额、取消和崩溃恢复，不能拼成无限内存ZIP。当前无ProjectExportJob，是否新增持久模型要以幂等、不可变selection、恢复与保留需求单独评审，不在本轮建表。

拟议读取 `GET /projects/{id}/exports/{export_id}` 返回状态/缺口，下载端点再次验证owner/项目、包SHA/过期状态。每次授权复核，导出下载不能凭猜测UUID或永久公开URL获取。未知投递不自动重复打包，发布前自校验重复成员、未登记内容、路径、SHA/大小、checksums和范围一致性。

## RI09：前端最小接入

在现有项目页自然增加“查看证据/预览导出”，列明范围、大小、缺失、仍在运行/失败/无快照对象；确认后显示原Job状态和受权下载。未实现端点前不显示可执行的“一键导出”按钮。单任务交付包仍可作为独立证据单元，不能声称项目完整。

## 准入及回滚

负例包括跨owner/project、撤权、并发修改、删文件、超限、重复/越界ZIP成员、快照摘要错误、包重试、无Task报告、分页截断。真实PG/存储/Worker验收依赖RI05。只读预览不能触发计算、补下载或报告生成。当前仅文档，可单独撤销；后续若实现Job必须保留旧包/快照并按版本兼容，不能回滚时清除审计事实。
