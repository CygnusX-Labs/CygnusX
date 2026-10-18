# RI05 独立真实环境验收计划

状态 PREPARED / NOT EXECUTED。当前没有指定并授权的独立运行环境；没有启动下载、分析、迁移或部署。本方案不授权解除源码门禁。

## 可重复环境

由运维提供隔离 Compose project/独立网络、专用非生产 PostgreSQL 数据库及账户、Redis前缀和队列、MinIO bucket/受管本地卷、测试用户/项目。复用原 PostgreSQL/Redis/Celery/Download Worker/原 Download CLI/FlowFrame/BioReport/FileRegistry/ReportService；版本固定到git SHA和镜像 digest，禁止 latest。环境清单记录 OS/架构/挂载uid与只读边界/工具版本/网络出口/预算。密钥只由环境注入，日志不回显。

阶段A验证schema迁移、Redis CAS、原一次性确认哈希及owner/project权限；阶段B只做能力探针与不安全来源负例，仍不执行科研任务；阶段C在受信构建和源码准入评审后由人类批准小案例。不可在未知环境自动建DB、跑生产迁移或打开flags。

## 小型公开案例

选择 **Bioconductor pasilla 包的基因计数矩阵与样本注释**，后续用于 counts_deg 小规模差异分析及双报告链。官方说明其来自 Brooks 等人的果蝇 Pasilla RNAi 研究，并明确包许可 LGPL；原始来源GEO样本见官方手册。来源依据：[Bioconductor包页](https://bioconductor.org/packages/release/data/experiment/html/pasilla.html)、[官方手册](https://bioconductor.org/packages/release/data/experiment/manuals/pasilla/man/pasilla.pdf)。

拟用 `inst/extdata/pasilla_gene_counts.tsv` 和 `pasilla_sample_annotation.csv`；实际固定版本/归档SHA必须在准备环境记录。网页 release 会移动，不能将其当不可变下载URL。保留包许可和引用；不得推断镜像或第三方副本享有相同许可。注释/计数的样本名、文库类型和分组须人工核对，不能自动把批次当处理效应。

**输入实际字节数和SHA尚未获取**，本轮未下载科研文件；这是一项明确的准入未通过项，不把估算写成测量值。准入前用受信元数据并在获准取得文件后记录每个文件实际大小/SHA；计数+注释合计上限20MiB，包归档获取上限100MiB，超限停止而非自动扩大预算。counts_deg 是否覆盖所需样本/设计必须先用现有validator核验，不支持时保留BLOCKED，不改写科学流程迁就示例。

该计数案例不证明 SRA/FTP/云全方法可用。下载 Worker 单独验证获准的HTTPS包获取与实际FileRecord登记；如归档不被Dataset直接接受，由人类在许可范围内提取两项并经原上传/FileRegistry导入，记录派生关系，不能伪称ZIP直接reconcile成功。SRA/aws/ftp及云模式继续独立BLOCKED，后续另选有合法元数据的最小原始测序用例。

## 预算及确认

建议待审批预算：CPU 2核、内存4GiB、分析30分钟、报告10分钟、测试总磁盘2GiB、并发1、实际传输100MiB、总运行60分钟。它们是拟议上限，不是已有执行器硬限制；cgroup/超时/硬传输预算要先证实。超限终止并保留部分证据。

测试负责人用真实JWT，在原 ToolConfirmationService确认端点审阅冻结输入/参数、许可、预算和定义摘要；确认一次性、绑参数哈希与有效期。下载、分析及报告生成分别检查对应门禁；聊天中的“已确认”和测试替身不作为人工凭证。

## 验收顺序与产物

| 阶段 | 真实检查 | 应保留 |
|---|---|---|
| PostgreSQL | 迁移链/唯一键、事务回滚、锁、并发登记 | schema版本、SQL断言、真实Task/FileRecord |
| Redis CAS | 同批准并发消费只有一次；过期/撤权/重放拒绝；Redis故障fail closed | 脱敏确认摘要/消费结果 |
| Celery/Worker | 重复投递/重启/未知投递不擅自再执行 | Task状态与故障点、不可自动重放证据 |
| 下载CLI/FileRegistry | 获准源小文件真实传输、SHA/size/owner/Task/配额 | Download Task、FileRecord，失败与部分输出 |
| Dataset/Handoff | 原导入/样本核验/人工审阅，生成不可变版本 | DatasetVersion、Frozen Handoff与哈希 |
| FlowFrame | 原prepare/确认/Task/Worker，输入前后核验 | 新analysis Task、定义/绑定/观察、真实结果Manifest |
| 发布/运行观察 | 发布包、镜像、工具、参考的受信来源核验 | 当前未接通者明确NOT_OBSERVED，复现门禁保持BLOCKED |
| ReportService/BioReport | 科学报告与证据报告独立Job、快照、交付校验 | ResultObservation、ReportSnapshot、Reports、ZIP/checksums |

每项同时做成功、撤权、漂移、超限、存储失败和进程崩溃负例。科学正确性不以Task success或包校验成功证明；不预设显著基因数，使用固定软件/设计下的独立对照和明确数值容差。

## 保留、清理与停止

计划保留脱敏验收清单、真实对象ID、许可、SHA、审批审计和失败证据90天（须由测试负责人确认）；原始公开输入在专用存储保留到验收复查结束。失败不删除输入或覆盖旧报告。完成后按测试namespace列出待清理对象，负责人批准后调用原服务清理测试制品/队列/Redis前缀；不得清空共享Redis、删除非测试用户文件或清理生产Task。未确定许可、字节数、环境版本、预算执行机制和人工确认前停止在准备阶段。
