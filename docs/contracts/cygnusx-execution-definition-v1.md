# CygnusX ExecutionDefinition v1 — RI12 Design

状态：设计契约 + Python DTO/Schema 隔离验证；**没有持久化、历史回填、Worker接线或复现执行能力**。本契约不是执行授权。源码 `src/cygnusx/application/schemas/execution_definition.py`，机器视图 `cygnusx-execution-definition-v1.schema.json`。

## 1. 职责及复用评审

| 对象 | 已有来源 | 边界 |
|---|---|---|
| ResearchPlan | research_plans.draft/digest/steps | 科研意图与编排计划，PLAN_ONLY；不是已执行定义或批准凭证 |
| RunPlan | platform_runs.plan_json/plan_digest/release_id | 部分入口的提交意图；release_id为声明版本，缺历史发布包与实际镜像证据 |
| DatasetAnalysisLink | normalized_request/execution_binding/handoff_hash | Dataset提交绑定，可复用输入、参数及配置摘要；不覆盖所有普通Task |
| Task | parameters、flow_id、实际主键 | 原任务记录；不能由当前FlowConfig恢复历史实际代码 |
| ExecutionDefinition（本设计） | 上述可信字段的显式、版本化投影 | 运行前批准的条件，不能混入当前机器的“历史”观察 |
| ExecutionObservation（后续） | 未来Worker preflight/启动探针 | 实际镜像、挂载、工具/参考/输入观察；本轮未新增模型 |
| ResultObservation | 已有result_manifest_observations | 某次真实结果采集与文件校验，继续独立追加 |
| ReportSnapshot | 已有report_snapshots | 报告生成时冻结的事实与缺口，旧digest保持 |

**本轮不新增表。** DTO先验证语义边界。未来RI12/13按入口覆盖评审：Dataset路径可先引用现有AnalysisLink；普通Task需明确不可变定义引用。仅当跨入口检索、保留、FK和不可变要求无法由既有结构满足时，才提出追加表/迁移，不能把ResearchPlan变为执行事实。发布/镜像registry和ExecutionObservation另行评审，不在本设计自动创建。

## 2. 字段来源、信任与缺失覆盖

字段填写必须附在可信服务器工作流中；DTO能验证结构与摘要，不能证明调用者的科学事实或授权。DECLARED为运行前声明；UNKNOWN为未记录。VERIFIED_BINARY/PASS_RUNTIME/Observed状态不能由本DTO自证。

| 字段 | 类型/现有候选来源 | 信任范围与缺失语义 |
|---|---|---|
| schema_version | 固定cygnusx.execution_definition.v1 | 不识别版本拒绝，不猜兼容 |
| digest_policy | canonical_definition.v1 | 内容规范化策略固定 |
| task_id | UUID或null；真实Task服务端主键 | 预分配/创建后的可信身份；未知为null，不从目录猜 |
| dataset_version_id | UUID或null；AnalysisLink.version_id | 不强制旧普通Task伪造Dataset |
| handoff_digest | SHA-256或null；冻结Handoff | 引用摘要，不代表运行时实际挂载已验收 |
| workflow_id | 安全标识；Task.flow_id/RunPlan | 必须显式，不读当前catalog填历史版本 |
| workflow_release_id | 安全版本标识或null；RunPlan.release_id | 声明版本，不替代可执行发布包 |
| workflow_release_digest | SHA-256或null | 现有binding通常null；未来受信发布获取，不取当前子仓commit冒充 |
| container_image_digest | sha256:64hex或null | 当前缺可信Worker观察；定义只可表达批准的期望镜像 |
| input_refs | 不可变tuple[ExecutionFileRef] | 每项file_record_id、role、sha256可空、status；对应输入SHA而非另存重复input_sha256表 |
| reference_refs | 同上 | 参考FileRecord/角色/摘要；相当于reference_checksums；不能由Genome_Version名称推造内容 |
| normalized_parameters | tuple[DefinitionParameter] | name + canonical value_json，允许嵌套JSON但以不可变字符串封装；不是任意命令或主机路径 |
| sample_design_digest | SHA-256或null | 已审阅样本/组/比较/设计的规范化摘要；无现存统一值时null |
| resource_specification | 冻结ExecutionResources | cores/memory_bytes/time_seconds均可空；是批准规格，不是实测资源使用 |
| comparison_policy | 已登记政策版本ID或null | 本轮不创建比较器Job，不以ID宣称容差合理 |
| provenance_status | UNKNOWN或DECLARED | 不允许填OBSERVED/VERIFIED来提升执行级别 |

样本设计未来规范应包括sample引用、group、batch、contrast、design及人工决策身份；当前Task参数不一定覆盖全部字段，必须标缺口。数值参数不能含NaN/Infinity；原输入服务器路径应转换为受管引用而非写入本DTO。

## 3. 不可变与 Canonical Digest

所有模型frozen/extra=forbid；文件、参数集合采用tuple；规范化参数JSON为字符串，不能通过嵌套dict绕过frozen。拒绝重复参数名、重复文件ID、JSON重复键、凭据/命令/目录字段、Bearer/签名参数和明显宿主路径。此白名单是设计边界，不是所有科研参数已经得到语义验证。

`content_digest()`：model_dump(mode=json)；input_refs/reference_refs按file_record_id排序；参数按name排序；value_json自身排序键、紧凑UTF-8、禁止非有限值；随后对全部字段排序键/紧凑JSON/UTF-8计算SHA-256。列表内容顺序（参数值内部）保留语义。null与缺失默认经DTO归一，schema/digest版本也参与摘要。

DTO不存自身digest，避免递归；由引用方保存返回摘要。task_id也参与内容摘要；预执行task_id=null后改绑实际Task不是原地更新，应采用显式绑定关系或生成新定义及摘要，具体写入协议待RI12正式实施。摘要不是签名、不证明执行事实、不授予审批。

## 4. 兼容策略

- 既有RunPlan/ResearchPlan/AnalysisLink/Task/ReportSnapshot保持原模型、摘要和缺失语义。
- 不提供自动from_current_environment迁移器，不读取当前容器/文件补历史。
- 新DTO尚不写入现有JSON列；旧消费者无新增必填字段，也没有数据库迁移。
- 未来新增必填/摘要语义变化升级schema/digest版本；不得原地改变canonical_definition.v1。
- 本轮6组RI12测试覆盖嵌套不可变、排序稳定、未知字段、版本往返、敏感值和既有模型兼容；不表示历史Task已经具备可复现条件。

## 5. 未来接入位置（未实施）

1. AnalysisFlowToolService/RunPlanService prepare：只投影真实参数、已冻结输入及受信发布引用，形成定义预览；绑定原ToolConfirmationService的规范化批准。
2. TaskService最终提交：当前owner/project/模块、定义摘要、输入与批准再次核验；不允许Agent指定二进制/路径。
3. Worker preflight：实际输入字节、参考/挂载、受信发布包和容器digest观察，写独立ExecutionObservation；与定义不符则拒绝运行。
4. ResultObservation：沿实际Task关联结果，继续原清单/字节校验。
5. ReportSnapshot：引用定义/观察身份及真实缺口，不覆盖旧报告。

接口草案仅为未来内部 `prepare_execution_definition(trusted_context, frozen_inputs, validated_request)`，无REST/MCP执行端点；本轮没有reproduction.execute或项目级导出实现。真实接线依赖RI05/RI12/RI13独立运行授权及安全验收。
