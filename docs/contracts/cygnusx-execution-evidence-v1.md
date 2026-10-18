# ExecutionDefinition v2 与 ExecutionEvidence v1

状态：RI12 修订及 RI13 最小接线；代码/隔离验证，真实运行未准入。旧 `execution_definition.py` 与 v1 Schema、摘要规则保持；新实现位于 `execution_evidence.py` 和 `execution_evidence_service.py`。

## 摘要与身份

v1 的 Task ID 参与摘要，这是既定兼容行为，不能原地改。v2 不接受 Task ID 字段：`definition_digest` 表示提交定义；`ExecutionTaskBinding` 将真实 Task、owner、定义摘要和生成文件摘要绑定，产生独立 `execution_binding_digest`。相同定义的新 Task 定义摘要相同、绑定摘要不同。冻结时间和运行观察不进入定义摘要。

v2 包含 flow_id、提交时 FlowConfig SHA、规范化参数 SHA、样本/比较设计 SHA、DatasetVersion/Handoff、输入 FileRecord/声明 SHA、可展示的数值参数。批准规格和资源限制不能等同实际使用。Workflow Release 摘要、镜像 digest、参考引用没有可信来源时 null/空；不是从当前目录、镜像标签或当前 catalog 恢复历史。RunPlan.release_id 和 AnalysisLink.flow_version 是版本声明，不是受信发布包。

参数只复制 cores/threads/padj/pvalue/log2fc/alpha 的数值；其余批准参数仅以摘要绑定，服务器路径、凭据和样本标签不复制到新证据。现有 DefinitionParameter 的敏感字段、命令、路径拒绝继续复用。摘要不是签名，不能证明数据库管理员未篡改事实或授予执行权限。

规范化：Python JSON 排序键、紧凑 UTF-8、禁止 NaN/Infinity；引用按 UUID、参数按名排序；数组内部顺序保留；Unicode 不做 NFC 折叠，1 与 1.0 保留原表示。本协议不是 RFC8785/JCS；客户端只消费服务端摘要，跨语言重算须先建立相容测试向量。更改规范必须升级版本。

## 持久化复用与不可变边界

本轮复用 `Task.parameters._execution_evidence` JSON，原 DatasetAnalysisLink/Frozen Handoff/RunPlan/ResultObservation/ReportSnapshot 保留。无新增表、迁移、历史回填或复现执行 API。没有跨任务索引需求驱动的新增数据库模型。

冻结 DTO 全 frozen；生成 config/samples/contrasts 记录相对文件名和真实 SHA，纳入任务绑定，不把含 Task ID 的 YAML 字节纳入任务无关定义。原 TaskRepository 保存整体 JSON；验证时检查定义摘要、绑定摘要、真实 owner/Task。观测追加并保存，最多256条，超过上限拒绝而非丢弃旧观察。数据库 JSON 本身不提供永久 WORM 或防管理员篡改；长期审计与索引需后续独立评审，当前不承诺这一属性。

## 最小接线

1. 原 FlowSubmissionValidator 完成验证后，TaskService 生成原执行文件、冻结实际文件摘要及定义，绑定真实预生成 Task；启用计费时原预扣及内部参数也先保存；保存 QUEUED 和证据后才能入队。用户自传 `_execution_evidence` 不在原流程白名单。
2. 原 Celery Worker 持 Task 行锁读取状态；只允许 QUEUED 被领取，先推进 RUNNING。重复运行中/终态投递不执行。PG 锁的真实并发验收仍待进行，SQLite不提供该证明。
3. Worker 执行前验证 Task 参数、FlowConfig、生成文件、Dataset/Handoff 输入字节；队列 snakefile/work_dir/config/param/cores 必须匹配 Task 与受信配置。失败保存失败证据后不调用执行器。
4. 原执行器返回后、报告生成前再次校验输入和配置。失败/异常保留观察；不清理旧 Task、文件或证据，也不自动重放。执行失败和交付失败仍由原服务分别处理。
5. ResearchProvenance.runtime 投影定义/绑定摘要与观察；其原 ResultObservation payload 因此可保留对应关系。ReportSnapshotBuilder 仅对有新证据的任务追加摘要事实及未观察缺口，旧快照及旧摘要不回写。

## 已观察与缺失

Dataset 输入 VERIFIED 仅表示执行前/后这些时点通过原有权属和字节检查，不是执行期间文件不可变证明。普通非 Dataset 任务没有完整不可变输入引用时保持 NOT_OBSERVED。生成配置被核验不能替代科学输入核验。

当前没有认证的 Workflow Release registry、镜像控制面观察或实际分析 CLI 版本探针，`workflow_release_status/image_status/tools_status/reference_status` 固定 NOT_OBSERVED。没有通过 env/tag/包 metadata 猜测实际子进程版本。UNKNOWN/null 是定义未记录；NOT_OBSERVED 是该次观察未采得事实，二者不能提升为 VERIFIED。

此最小接线能保留将来预检所需的已知事实和阻断缺口，**不能让任务自动具备可复现资格**。真实 release/image/tool/reference 认证采集是后续 RI13 运行接入门禁，未通过前历史复现仍 BLOCKED。

## 回滚

仅按本轮 baseline 逐补丁回退钩子与新增文件，保留已写 JSON、观察、ResultObservation 和 ReportSnapshot。旧消费者可忽略 Task JSON 新键；旧 snapshot 字节不可重写。不要回退 Task 入队时序后声称相同的可见性保证；在环境验收前不部署或开启执行门禁。
