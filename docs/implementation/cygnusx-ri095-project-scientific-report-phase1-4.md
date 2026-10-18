# RI095 Project Scientific Report Phase 1–4 实施记录

基线日期：2026-10-17。起点 HEAD 为 51011118535f782f5282f638b4a54649c79bf6d6，分支 feat/research-agent-phase5。已有大量未提交成果；基线、子模块身份和相关文件指纹保存在 evidence/ri095-project-report-phase1-4/。本轮未提交、推送、部署、连接默认业务数据库或启动科研计算。

## 完成／阻断矩阵

| 阶段 | 代码现状 | 隔离验证 | 真实运行 |
|---|---|---|---|
| G0 / D1 | VERIFIED_CODE：ADR 选择 B，最小项目报告 Job，复用原报告／文件／存储服务 | SQLite 追加迁移、旧记录保留、CHECK 与冻结触发器 | PG FK／并发／迁移 BLOCKED |
| P1 | VERIFIED_CODE：独立 ProjectReportJob、请求别名、版本父链、JWT 创建、持久 outbox、Worker 锁与 reconcile | 实际 SQLite 任务、请求去重、门禁／身份／摘要拒绝、ASGI 身份边界 | 真实 Broker／Worker 强杀恢复 BLOCKED |
| P2 | VERIFIED_CODE：M0 范围内 DEG 行列引用，复用 ResearchClaimService 冻结真实值与 provenance | 实际 TSV／SHA、NA、伪造字段、越界、字节漂移、规范摘要 | 真实项目样本授权验收 BLOCKED |
| P3 | VERIFIED_CODE：版本化 14 章静态项目模板，经 BioReportAdapter 静态资源边界、共享发布／登记／下载；PDF 条件路径 | 实际 HTML、回读 SHA、FileRecord／ReportFile、重复投递、PDF 失败仍保留 HTML、篡改与停用拒绝 | 可信渲染镜像／正式 PDF／私有存储 BLOCKED |
| P4 | VERIFIED_CODE：显式 v2 M1、新 Job，引用 M0 digest、项目报告／ReportFile／FileRecord／SHA／size | 实际 ZIP、离线 verifier、授权回读、新旧摘要、M0 ZIP 字节不变、禁止分析／下载／科学渲染钩子 | 真实全栈下载与 Chromium BLOCKED |
| RA / BR | 新入口默认关闭，未开放任何运行准入 | 不能以 SQLite／jsdom／替换 JWT 验证函数冒充运行验收 | PASS_RUNTIME、PASS_E2E 均未授予 |

## G0：来源兼容性决策

见 docs/decisions/cygnusx-project-report-source-adr.md。Task-first reports／report_generation_jobs／report_snapshots 的 task_id 非空约束不变，不制造 Task、不回填历史项目。项目来源与发布状态保存在 project_report_jobs，冻结 source_snapshot 包含 M0 和 Claim 选择。ReportFile 复用原表，仅追加 project_report_job_id，与 report_id 用 XOR CHECK 二选一；旧报告下载仍按 report_id 约束。

追加 projectreport01 迁移代码，未应用到业务库。SQLite 真实迁移保留旧 ReportFile，并验证空来源拒绝、ready 必须有 HTML 身份、冻结来源不可修改。PG 分支包含冻结来源和已发布产物触发器；尚无真实 PG 执行证据，不能宣称 FK、并发和 advisory lock 已认证。

## P1：身份、授权与可靠性

POST scientific-summary/prepare 只读重构来源；POST scientific-summary 必须通过现有 CurrentJwtUserId，不能以 API Key 自证批准。状态、预览、下载重新读取当前 owner／project／模块身份。项目 completed／handed_over 可读，停用与未知状态拒绝。

创建时持久提交 queued 和 request alias，再尝试投递；Broker 异常保留 queued。相同 source digest 复用身份，新的选择创建 parent/version；相同 request_key 不允许绑定其他摘要。Worker 使用独立连接的 PG advisory lock、有限超时／重试和周期对账，失败码复用现有报告任务错误映射。实际 PG／Broker 测试仍 BLOCKED。

## P2：冻结选择

客户端只提交 M0 Job、Task／File／可选 Report、feature 和列；extra=forbid 拒绝 value／SHA／verified 等自报事实。服务端限定为 M0 实际包含的 file_record 文件，检查 Task→DatasetVersion→AnalysisLink、历史 Report 版本／Snapshot／Observation，再复用 RI10 的安全 TSV 读取。创建、Worker 渲染前与发布前重新核对来源摘要，漂移拒绝，绝不替换为最新事实。

FrozenProjectClaims 独立版本化并按 claim_id 规范排序。没有 Claim 或 NA 不产生伪造结论；有限数值核验不等于机制、因果、QC PASS、科学正确或复现成功。旧 ReportSnapshot／ClaimProvenance schema 不变。

## P3：模板、产物与下载

project_report_renderer 是固定项目模板，不复制 RNA 统计模板，不调用分析。14 章仅组织冻结事实与缺口，未知环境 NOT_OBSERVED，未记录事实 NOT_RECORDED，复现 NOT_RUN；CSP、转义与空 sandbox 预览保持。旧 report_audit_renderer 未修改，其起点 SHA 可直接比较。

项目 HTML 复用 BioReportAdapter 新增的静态文档适配入口及依赖检查，PDF 复用既有 render_audit_pdf 的受控 Pandoc／Typst 转换器，不传用户配置、路径或凭据。该路径未调用 BioReport 科学模块，也未声称 Quarto single 项目模板或生产镜像已认证。renderer_runtime 始终 NOT_OBSERVED。project_report_pdf_enabled 默认 false；请求 html_pdf 时只有显式启用并生成有效 PDF 才登记；渲染不可用／无效 PDF 保留 HTML 与 PDF_NOT_GENERATED。

StoragePathFactory 分配项目 run；publish_archive 原子发布；ReportService.register_project_report_file 复用 FileRegistry、目录链、回读 SHA／大小／配额。ready 只在真实 HTML 文件登记成功后设置。下载验证当前 FileRecord 生命周期、owner、来源、ReportFile、SHA／大小及字节，读完再次验证项目身份。文件 SHA 仅证明完整性。

## P4：非循环 M0 → Report → M1

ExportSelectionV2 显式提供 M0 Job 与已发布 report Job IDs，必须保持 M0 原选择。ProjectDeliveryManifestV2 记录源 M0 digest 和真实报告产物身份，报告 source 不引用 M1。旧 v1 DTO 的字段和摘要定义不变。M1 对历史核验脚本单独冻结当前版本，旧 M0 不改。

ProjectDeliveryService 的 prepare／create／Worker／download 复用原预算、队列、锁、ZIP 和离线 verifier；M1 打包前校验每份报告属于同项目／同 M0，验证登记文件与实际字节。缺 PDF 使用 partial 缺口，不放空文件。实际隔离测试检查新 ZIP 可核验、M0 digest 和旧 ZIP 字节不变，且 TaskService.submit／DownloadService.submit／BioReportAdapter.render 被禁止时仍可完成导出。

## 前端融合

原 ProjectResearchDelivery 布局中增加正式报告卡片；ClaimEvidencePanel 显式选择核验后的引用。选择变化令 prepare 失效，项目切换／卸载中止请求和轮询，晚到响应不得回填。显示实际 Job 状态、PDF 缺失与错误；HTML 在空 sandbox 中预览，下载核对 SHA／大小。正式报告与旧 prototype 入口分别标识。M1 需另行预览与确认，报告状态可从 sessionStorage 保存的 Job 身份恢复。

## 验证证据与局限

本轮相关后端回归 133 passed；前端相关测试 16 passed；14 个源码文件 mypy 无错误；有界 Ruff、迁移链唯一 head、前端 build 通过。日志、退出码和 JUnit 在 evidence/ri095-project-report-phase1-4/。后续新增版本／M1兼容修正另有 final-m1.log。没有运行全仓全部门禁，不能把有界检查等同全仓全绿；未提交故未执行提交门禁。

ASGI 测试使用替换的 JWT 验证函数和真实 SQLite／文件，不是线上 JWT 验收；Worker 锁／强杀恢复尚无真实 Broker／PG 证据。浏览器仅 jsdom，无 1920／768／390 Chromium 证据。PDF 转换器本地回归不代表生产工具链认证。真实准入清单见 docs/audits/cygnusx-ri095-real-runtime-gates.md。

## 保留与回滚

关闭 project_report_write_enabled、project_report_pdf_enabled 和任务投递可停止新增写入；原 research_delivery_read_enabled／project_export_enabled 不自动开放。保留 Report、快照、Job、M0／M1 与文件；不覆盖旧版本、不删除科研证据。迁移 downgrade 拒绝破坏性回退，实际数据清理另行授权。
