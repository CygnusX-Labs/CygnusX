# CygnusX Research Delivery v1

状态：实现中的受保护契约；运行准入 BLOCKED。权威现状入口为 `ARCHITECTURE_DESIGN/CygnusX_research_delivery_architecture.md`。

## 对象与真实性

`DatasetVersion → Frozen Handoff → DatasetAnalysisLink → actual Task → Result Manifest → FileRecord → ReportModel(scientific / reproducibility)`。Run 是可选关联，仅引用同 owner、同 Task、同 Flow 且已确认的实际记录；缺失保留 null。历史 Task 不补造 DatasetVersion、版本、运行环境或来源。

Execution binding 在 prepare 时保存 Flow 配置摘要、声明版本、标准化 TaskSubmitRequest 摘要与 Handoff SHA-256。它是 PREPARE_CAPTURE，不能证明实际镜像、软件版本或 workflow release。TaskService 最终入口和 Worker 启动前重核绑定与文件字节，之后才允许执行。Task/link 在队列可见前提交；投递不明禁止重放分析。

ResultObservation 是现有 Task 的不可变采集记录，不是第二套运行系统。唯一 `(task_id,evidence_digest)`；owner/project/link/task 外键 RESTRICT，ORM 和 PostgreSQL UPDATE/DELETE 拒绝。相同事实复用记录，字节/状态变化追加记录。观察范围为采集时字节，非执行时证明或科学复现认证。

## 读取 API

- GET `/api/v1/projects/{project_id}/research-delivery`：项目内版本与交付链摘要。
- GET `/api/v1/tasks/{task_id}/provenance`：严格 ResearchProvenance DTO。
- GET `/api/v1/reports/{report_id}/provenance`：真实 Report → Task 关联。
- POST `/api/v1/tasks/{task_id}/research-delivery/reconcile`：JWT 人类入口，body `{request_key: UUID, repair_reports: boolean}`；额外要求运行源码门禁与 delivery write flag。只核验既有输出、登记、排独立报告队列，不提交分析。默认关闭。

只读开关 `RESEARCH_DELIVERY_READ_ENABLED=false`。写开关 `RESEARCH_DELIVERY_WRITE_ENABLED=false`；开关不能绕过 `WRITE_RUNTIME_ACCEPTED=False`。新库迁移必须先完成后再启用读取。REST 与共享工具复核 active user、报告模块及 Dataset 项目权限；无 owner/project 由模型注入的入口。

项目读取目前每次最多 20 Dataset × 5 版本，每版本最多 100 analysis links；项目请求累计最多 20 条分析详情。响应标注 truncated；每个 manifest、文件数量、总字节和采集时间另有 Settings 上限。此为小数据受保护入口，非大项目性能承诺。

## 状态与校验

- compute_state：真实 Task 状态。
- input_integrity：Frozen Handoff 与受管输入实物校验。
- result_integrity：实际 manifest 与逐文件存在性、大小、SHA-256（可兼容声明 MD5）的观察。
- evidence_state：证据缺口，运行镜像与 release 未观察时 PARTIAL。
- delivery_state：READY / PARTIAL / BLOCKED / UNKNOWN；分析 success 不等于交付 READY。

manifest 必须包含 platform.task_id/user_id/flow_id；扩展 cygnusx.dataset_version_id/handoff_hash/parameters_sha256/flow_config_sha256/flow_version 与服务器绑定一致。缺失旧字段标 UNKNOWN 缺口，不升级为 VERIFIED。CountsDEGFlow 保留原 R 统计 manifest，新增 `result_manifest.delivery.json` 封装身份和逐文件指纹，不改统计输出。RNAFlow 子模块未修改；旧 manifest 缺输入绑定时保持 PARTIAL。

禁止绝对/父目录/链接/特殊文件路径及跨 owner/project 输出；使用 pinned FD 采集并在前后检查 inode/mtime/size。FileRecord 仍为资产权威；新登记走 FileRegistry 与目录链。未知实际镜像、software/release 始终 null，不借用宿主机或配置值填充。当前代码没有解除运行环境缺口的可信 attestation 路径，所以不会自动宣称全链 READY。

## 双报告与快照兼容

科学 HTML 与执行证据报告是独立 ReportModel；均关联 Task/ResultObservation。既有科学 HTML 通过实物核验后复用登记。Counts 独立 job 使用仓库固定 BioReport 模板，只展示完成的 DEG/QC，不调用 DESeq2。报告失败独立重试，不重新投递 Task。错误消息为常量；科学渲染错误可重试，次数受既有 Settings 上限限制。

`ReportSnapshot v1` 增加可选 research_delivery 投影；无该字段和显式 null 的旧快照保持原 digest 策略。新快照固化 lineage，旧记录不回写；渲染 M7 展示 Dataset/Handoff/产物/交付缺口。缺少或变化的原始产物不得通过报告重试变成已验证。显式新请求可以生成新科学报告版本；旧版本保留。Dataset 证据 HTML 丢失只允许从同一快照重建**完全相同 SHA-256 与大小**的字节；损坏文件与不可重建 PDF 需人工恢复可信备份，不能静默覆盖。

输出 DTO 不暴露服务器路径、原始参数、prompt、token、完整异常。来源 URL 仅保留官方 HTTPS 域与必要检索参数；报告正文按既有脱敏策略和 HTML 转义。

## Agent 与 UI

共享只读能力：research.task_provenance / report_provenance / dataset_provenance / project_delivery。寻宝鼠与 AI 助手通过同一 catalog/gateway；MCP preset 与内置导出同源。参数 extra=forbid；owner、project、_confirmed、integrity 注入拒绝。每次调用重验会话项目和 scope，未关联当前项目的历史 Task 不向 Agent 投影。

项目页展示版本、冻结摘要、真实 Task、逐文件和两类报告状态；切换项目取消旧请求并校验响应 project_id。只读功能失败不保留旧项目数据，不自动提交分析或报告修复。
