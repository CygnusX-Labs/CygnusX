# 生命周期稳定化、RI12 修订与 RI13 最小执行证据接线

实施日期：2026-10-16。依据本轮附件，承接 RI01–RI04 实施记录、架构审计和路线图；没有重新实施前轮，也没有新增下载器、Agent Runtime、MCP Server、TaskService、ReportService或数据库体系。

## 1. 本轮交付入口

| 交付 | 文件/实现 |
|---|---|
| 下载运行准入与能力失效评估 | [准入方案](cygnusx-download-runtime-admission.md) |
| 增量质量基线 | `evidence/lifecycle-stabilization-ri13/`：baseline、Ruff、mypy前后诊断、测试、质量比较 |
| RI12契约修订 | [v2定义与v1证据契约](../contracts/cygnusx-execution-evidence-v1.md)，对应两份机器Schema |
| RI13最小实现 | `application/schemas/execution_evidence.py`、`application/services/execution_evidence_service.py`，原TaskService/Worker/Provenance/Snapshot钩子 |
| RI05独立验收准备 | [真实环境计划](cygnusx-ri05-isolated-runtime-acceptance-plan.md) |
| RI06–RI09接口建议 | [项目导出提案](cygnusx-ri06-ri09-project-export-interface-proposal.md) |
| 测试与门禁 | 本文第5节及证据 checks.json |
| 未通过与回滚 | 本文第6、7节 |

## 2. 工作区和范围

本轮开始另存 baseline.json、status.txt 及涉及文件快照，保护已存在大量未提交修改。既有下载安全/脱敏修补可能由其他工作流继续演进，本轮不覆盖其实现。未提交、推送、部署、安装依赖、生产迁移或更改写门禁。原 v1 ExecutionDefinition 及Schema不改摘要规则。

新增源码两份（DTO/证据服务），增量接线在 `task_service.py`、`research_execution_binding.py`（准确标注其实际支持的Task实体类型）、`celery_app/tasks/analysis.py`、`research_provenance_service.py` 和 `report_snapshot_builder.py`。新增三份测试覆盖证据、投影和稳定化。没有改React Island、Node检索内核、FlowFrame、流程catalog或分析引擎。

## 3. RI12决策与RI13行为

v1 Task ID参与摘要的兼容规则保留。v2 definition_digest不包含Task；独立execution_binding_digest包含Task/owner/定义/生成文件摘要，区分“同定义的新执行”和“同一个Task”。Frozen DTO不是DB永久WORM，也不是审批凭证。

每个经过原TaskService的新分析任务在入队前冻结规范化参数与样本设计摘要、FlowConfig声明、可得的DatasetVersion/Handoff/输入声明及原builder生成文件SHA。普通非Dataset任务仍缺完整受管输入时显式NOT_OBSERVED，不能反推目录字节为可信输入。配置生成不接收内部证据键。

Task及证据在队列可见前持久化QUEUED，避免PENDING可见时序；启用计费时，原预扣调用和内部参数也在投递前保存，避免投递后保存旧Task覆盖Worker状态；计费规则未重写。QUEUED表示投递意图，不能证明broker ACK。未知投递必须对账，不自动重放。Worker持Task行锁领取QUEUED并推进RUNNING；终态和已有RUNNING的重复投递不重开执行。PG并发锁语义仍需真实验收。

Worker前后核验参数、FlowConfig、生成执行文件和原Dataset输入；执行器队列参数核对Task和受信Flow配置。失败观察先保留，再按原Task状态机处理。原执行器、报告生成和结果登记继续使用原服务。输入校验是时点观察，不保证执行期间文件被固定挂载。

ResearchProvenance.runtime读取新定义/绑定和观察，原ResultObservation捕获该payload；ReportSnapshotBuilder为新证据追加摘要事实和环境缺口。历史任务不补写、旧快照不重算。科学报告与证据报告的v1/v1.1交付语义继续沿用：缺快照只能新版本partial，不能伪造完整性。

## 4. RI13九项覆盖与缺口

| 项 | 当前证据 | 层级 |
|---|---|---|
| 执行前定义冻结 | 原TaskService入队前保存，幂等重用不改定义 | CODE/ISOLATED |
| 输入/参数绑定 | 参数/样本摘要、Dataset FileRecord/Handoff、生成文件/Task绑定 | CODE/ISOLATED；普通Task输入缺失显式标记 |
| 真实Workflow Release | 当前只保存FlowConfig声明；发布包认证来源尚缺 | NOT_OBSERVED / RUNTIME BLOCKED |
| 实际镜像/工具版本 | 没有受信控制面/实际CLI探针；不以env/tag/包metadata伪装 | NOT_OBSERVED / RUNTIME BLOCKED |
| 参考资源版本/摘要 | 无受信统一引用时null/空，不补当前参考 | NOT_OBSERVED / RUNTIME BLOCKED |
| 输入执行前后完整性 | 原check_inputs真实受管文件/大小/SHA；生成文件同样核对 | CODE/ISOLATED；真实挂载待验收 |
| 结果Manifest/Task关联 | 原Provenance/ResultObservation与ReportSnapshot保留；新摘要随投影 | CODE/ISOLATED |
| 缺失状态 | UNKNOWN/null声明与NOT_OBSERVED观察区分，报告保留缺口 | CODE/ISOLATED |
| 失败和恢复留存 | 本地失败观察/数据库读取恢复/重复投递拒绝；不自动重放 | CODE/ISOLATED；PG/队列崩溃恢复待验收 |

这是一条能保存已知事实和缺口的最小链，尚无足以认证历史复现的完整执行环境证据；不宣称RI13真实运行验收完成。

## 5. 测试与门禁矩阵

当前命令、范围、最终通过数与退出状态以 `evidence/lifecycle-stabilization-ri13/checks.json`、`commands.md`、对应日志及 JUnit 为准。增量质量必须比较同一选择范围的原快照/当前诊断，不能把前轮全仓289/1023错误数量当成本轮净基线。

| 门禁 | 通过标准 |
|---|---|
| 稳定化 | REST/Gateway同服务端能力；人工/Agent/Worker仍Fail Closed；manifest版本/partial语义明确 |
| RI12 | v1不变、v2无Task、绑定区分Task/owner、摘要稳定、无敏感参数复制、Schema一致 |
| RI13 | 原提交→真实SQLite Task持久化→队列替身；真实Worker函数/执行器替身；前后输入变化拒绝；失败/重复投递/重启读取；新报告投影 |
| 回归 | 原Dataset/审批/报告/Flow校验相关选择范围通过；不能推断全仓PASS |
| 静态 | 本轮Ruff范围通过；新增源mypy通过；继承文件诊断增量不增加 |
| 运行 | 原门禁不变；无真实环境不得报告PASS_RUNTIME |

测试中SQLite无法证明PostgreSQL行锁、Redis CAS、真实队列/CLI/挂载与BioReport运行。工具退出时出现的既有OTel异步导出/关闭流警告单独记录，不等于科研任务运行。

### 最终选择范围结果

- 针对性10个测试文件：151 passed；相关回归22个文件：341 passed。存在既有警告，范围有重叠，不能相加宣称独立覆盖数。
- 原快照8个Python源文件Ruff为0诊断，当前涉及的7个源文件及3个测试文件Ruff通过。
- 新证据代码与绑定边界3个源文件mypy通过；完整选择范围原快照9条、当前8条，比较文件/诊断内容/数量后新增0条。当前原始mypy仍FAIL，未宣布全仓PASS。
- v1源码摘要及Schema不变；v2定义、证据Schema与DTO一致。真实运行和环境认证均未执行。

## 6. 未通过项目

实际Worker镜像/发布包/工具/参考认证采集、普通Task完整输入身份、执行期间不可变挂载、真实PG并发/故障恢复、Redis CAS、真实传输硬预算、完整跨栈科研案例均未验收。独立环境尚未授权，pasilla固定版本/SHA/实际大小尚缺，计划明确在此停止；本轮未启动真实下载分析。

共享脏工作区仍有既有mypy错误；使用增量比较而非无关重构。当前JSON持久化不提供永久WORM/跨任务高效索引；仅在长期保留/不可变存储/索引需求成立后评审模型，不提前迁移。

RI06–RI09仅接口建议；没有新增项目导出任务、下载端点或历史复现执行入口。

## 7. 回滚

不整文件checkout、不reset/stash；对照本轮baseline仅撤销明确补丁，新DTO/服务/钩子成组回退。保留已存在或新生成的Task JSON、ResultObservation、ReportSnapshot和所有文件，不能删审计事实。旧消费者可忽略新增内部JSON键。

冻结/Worker核验和入队时序有关，不能仅撤掉一半后声称同等保证；若回退运行钩子，必须重新评审其对新证据任务的处理。源码写门禁始终关闭；本轮未部署，无需操作线上回滚或生产DB。

## 8. 续轮当前状态复核

2026-10-16 重新读取附件、前轮报告、审计、路线图及当前源码后，确认既有工作区已经包含上述八项交付；本次未重复实施或改写业务源码。14个关键源码SHA与原final-verification一致，三份v1/v2/证据Schema与当前DTO一致，下载及Gateway源码运行门禁仍关闭。

本次独立复跑：针对性151项、相关回归341项、下载页面两个文件5项全部通过，无失败或跳过；两组Python范围有重叠，不相加计算覆盖率。选定10文件Ruff、3源文件mypy及git diff --check通过。日志、JUnit、复核时间和源码摘要见 `evidence/lifecycle-stabilization-ri13/revalidation/`。全仓门禁未复跑，原始选择范围mypy的继承诊断仍按第5节记录，不能宣布全仓通过。

RI05交付的是独立验收准备方案；实际环境、案例固定版本/输入实测大小/SHA及运行许可尚未具备，必须在计划规定的停止点保持未通过。RI13交付的是最小执行证据接线及隔离验证，运行环境认证仍未完成；RI06–RI09仅交付接口设计。没有提交、推送、部署、生产迁移、真实下载/分析或解除门禁。
