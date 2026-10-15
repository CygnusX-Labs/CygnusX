# 可复现报告 Phase 0 设计与实现边界

本阶段为普通 RNA Task 建立只读、版本化证据快照。架构现状以 `ARCHITECTURE_DESIGN/` 和代码为准；本文的 Phase 1 部分是迁移提案，不代表已部署能力。现有 ReportService、报告 API 和历史 HTML 路径尚未调用新 builder。

## 身份与授权

| 字段 | 当前来源与约束 |
|---|---|
| source_execution_kind | 协议预留 task / agent / case；builder 目前只接受 rna_seq Task |
| task_id、owner_id | TaskModel 主键和 user_id；数据库查询先限定 owner |
| run_id | 仅 RunModel.task_id 明确关联、同 owner/flow、confirmed_at 非空；指定 Run 不一致直接拒绝 |
| project_slug | 仅明确关联 Run 的安全标识字段，不从目录推断 |
| project_id、execution_attempt_id | 当前没有可证实关联，保持空值 |
| source_reference | Task 主键引用 |
| association_status | 有确认 Run 为 verified，否则 not_recorded；没有 Run 仍可构建 |

不按任务名、时间、目录相似度关联；QueueJob 与 manifest.run.run_id 均不是业务 Run。文件记录必须同 owner、personal、明确 task_id；RunEvent 必须属于该 Run，非空 task_id 必须一致。跨 owner/path 返回 AuthorizationError，显式身份冲突返回 ConflictError，无法访问 Task 返回不泄露身份的 NotFoundError。

DatabaseTaskEvidenceSource 只执行 SELECT，并禁止 autoflush；不提交事务。调用者负责采用只读数据库角色及合适的读取事务。Phase 0 没有创建表、迁移、目录或报告记录。

## 协议与证据

`application/schemas/report_snapshot.py` 定义 frozen、extra=forbid、具名 Pydantic 模型；集合采用 tuple，不能用可变 JSON dict 绕过不可变约束。元数据包含 schema/digest/redaction 版本、report_id、immutable_version、生成时间、owner 可见性、来源引用、水位、采集窗口和摘要。内容包含 inputs、environment、steps、tool_calls、quality_gates、artifacts、provenance、reproducibility、coverage、warnings、missing_evidence。

所有证据附 source_type/source_id、安全 source_path、captured_at、observed_at、capture_method、verification_status/details。路径在当前投影中不导出，以免暴露宿主绝对路径、样本名或令牌。六种状态含义：

| 状态 | 含义 |
|---|---|
| verified | 对明确的观察或关联完成核验，范围由 details 描述 |
| not_recorded | 源头没有记录，不能补成失败或通过 |
| unavailable | 已知对象当前不可访问、缺失或不支持读取 |
| not_applicable | 本阶段不执行重跑等不适用事项 |
| verification_failed | 有证据但身份以外的内容校验失败 |
| estimated | 声明、估算或未被执行时证据证明的事实 |

coverage 计数来源观察的状态，不是科学质量评分或可复现概率。QC 文件仅为 artifact；不存在已绑定规则版本和明确执行决策时，quality_gate.decision 为空。历史软件、镜像、参考基因组、工具调用、输入文件身份和步骤完整性采用明确缺口。当前 Settings、Flow release、Agent YAML、未绑定 environment.json 不补写为历史环境。

## RNA 读取与部分证据

`ReportSnapshotBuilder.build(owner_id, task_id, run_id=None)` 读取 TaskEvidenceSource，再在线程读取 RNAResultManifestAdapter，最终冻结快照。源接口可注入，数据库适配器不包含渲染逻辑。

清单限定 ARDP 1.0 / omichub.analysis.result，沿已有 work、相邻 data_deliver、work/data_deliver 位置查找；多个清单拒绝静默择一。清单限 4 MiB、2000 文件，不执行命令、不读取日志正文、不递归目录。清单 identity 字段存在但冲突时拒绝；task_id 和 user_id 双绑定才把产物来源视为显式关联。无绑定时当前字节可 verified，但来源仍 not_recorded。FileRecord 仅按明确关联及精确存储路径匹配，不按文件名猜测。

所有路径解析后必须在 StoragePathFactory 的 owner 根下；清单文件引用必须为交付根内相对路径，拒绝 ..、绝对路径、反斜杠及越界符号链接。owner 根本身不得被符号链接重定向。只支持 local FileRecord；其他后端为 unavailable。缺失/损坏清单仍收集已登记文件；没有 legacy HTML 自动回退。

文件分块计算 SHA-256/MD5，采集前后检查 inode/大小/mtime；清单指纹与大小不一致为 verification_failed。新算指纹 scope=capture_bytes 且 verified_at 为采集时间；不能据此声称 execution_bytes。清单指纹为 manifest_declared，legacy checksum 因算法未知不推断为 MD5。目录仅证明存在，标 estimated，不计算目录完整性指纹。流水线声明版本、mtime 推导耗时为 estimated。

默认投影只保留允许的数值/布尔参数和短标识；不导出任意参数字符串、名称、原始 payload、日志、命令、DSN、签名 URL、凭证、运行计划正文或异常正文。此策略为 owner_allowlist.v1，必须版本化变更。安全模型依赖宿主目录权限：静态越界及普通并发改写已检查；恶意并发替换目录/链接仍需 Phase 1 用目录 FD/openat 加固，不能宣称原子取证。

## 序列化和冻结

canonical_serialization 使用排序键、紧凑 UTF-8 JSON、禁止 NaN，含完整冻结元数据。snapshot_digest 为 stable_facts.v1 SHA-256：排除 report_id、immutable_version、生成/采集窗口、coverage、各源 captured_at 和指纹 verified_at；保留 observed_at、业务身份、源水位、schema/redaction/digest 版本、事实、状态、文件内容指纹和警告。列表顺序由 builder 的固定遍历及数据库排序决定。

因此同一事实重新采集仅时钟变化时摘要稳定，文件内容或证据状态改变则变化。冻结后渲染不得重新读取 Task/磁盘；模型重新验证摘要与 coverage。摘要不是数字签名，不证明源系统未被修改，也不替代审计或可信时间戳。

## Phase 1 迁移提案（未执行）

1. 新增 report_snapshots：id、report_id、owner_id、source_kind、task_id nullable FK、run_id nullable FK、agent_execution_id/case_execution_id 待实际模型契约确定、schema_version、redaction_policy、digest_policy、snapshot_digest、immutable_version、snapshot_json、source_watermarks、captured_at。Task 源要求 task_id 非空；Run 可空；UNIQUE(report_id, immutable_version)。JSON 入库前必须按对应版本模型验证。
2. Task 始终为主身份，不强迫普通 Task 创建 Run。Run.task_id 已有 nullable unique 映射；新增 FK 前只做只读孤儿审计，不能按路径回填或批量更改历史数据。
3. report_jobs 保存生成状态、snapshot_id、owner/source、幂等键及错误码；业务唯一键包含 owner、source identity、事实摘要、schema 和投影策略。可以由现有 Celery 调度，但不能把 QueueJob 当 Run。冻结快照事务完成后再生成 PDF/HTML，每个渲染版本引用固定 snapshot_id。
4. 使用事务/明确水位处理读取期间更新与任务完成竞争；追加不可变版本，不覆盖历史 snapshot_json；失败任务不伪造完整性。验证真正的输入指纹、执行环境、步骤工具事件、QC 规则版本与决策后才提高可复现性结论。
5. API 必须再次验证 owner/source 和报告权限；共享/团队可见性需要独立投影，不能复用 owner 快照。增加异常大小、超时、恶意目录并发替换防护；大文件采集走受控 worker。

## 真实验收条件

需要可连的只读数据库角色和同 owner 授权目录映射，选取一个普通已完成 RNA Task、一个 RunPlanService.confirm 产生且已完成的 RNA Task。按明确主键读取，不扫描他人目录。验证冻结/回读摘要、Run 关联、清单、当前指纹、缺口和凭证投影；不得重跑分析或写生产。当前环境数据库 DNS 不可解析且无只读 DSN，两个真实入口均未验收。
