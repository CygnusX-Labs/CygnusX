# 合成契约运行与失败分析

层级：SYNTHETIC_CONTRACT；目标：CONTRACT_VALIDATION；运行 ID：`fa5a24e6-4b40-4b74-af51-d5c9d2b76e1c`。人工审定 0，禁止将这些时间称为科研交付耗时。最新原始记录在本地 `evidence/phase5/benchmark-contract-07`，不纳入提交；历史 -03 的源码和原始结果保持不变。

| Case | 实际检查器输出 | 预期行为匹配 | 检查耗时（秒） |
|---|---|---|---|
| discovery_01 | `{"status": "UNVERIFIED"}` | True | 0.000026630 |
| discovery_02 | `{"status": "UNVERIFIED"}` | True | 0.000007805 |
| discovery_03 | `{"status": "PARTIAL"}` | True | 0.000017843 |
| discovery_04 | `{"status": "CONTRADICTORY"}` | True | 0.000007674 |
| planning_01 | `{"status": "REVIEW_REQUIRED", "gaps": ["BIOLOGICAL_REPLICATION_REQUIRED", "CONDITION_EVIDENCE_REVIEW_REQUIRED", "CONTROL_AND_TREATMENT_REQUIRED", "SAMPLE_IDENTITY_REQUIRED", "TISSUE_EVIDENCE_REQUIRED"]}` | False | 0.000048721 |
| planning_02 | `{"status": "REVIEW_REQUIRED", "gaps": ["BIOLOGICAL_REPLICATION_REQUIRED", "CONDITION_EVIDENCE_REVIEW_REQUIRED", "CONTROL_AND_TREATMENT_REQUIRED", "INPUT_TYPE_MISMATCH", "SAMPLE_IDENTITY_REQUIRED", "TISSUE_EVIDENCE_REQUIRED"]}` | True | 0.000027782 |
| planning_03 | `{"status": "REVIEW_REQUIRED", "gaps": ["BIOLOGICAL_REPLICATION_REQUIRED", "CONDITION_EVIDENCE_REVIEW_REQUIRED", "CONTROL_AND_TREATMENT_REQUIRED", "INPUT_TYPE_MISMATCH", "PROCESSING_EVIDENCE_REQUIRED", "SAMPLE_IDENTITY_REQUIRED", "TISSUE_EVIDENCE_REQUIRED"]}` | True | 0.000018204 |
| planning_04 | `{"status": "REVIEW_REQUIRED", "gaps": ["BIOLOGICAL_REPLICATION_REQUIRED", "CONDITION_EVIDENCE_REVIEW_REQUIRED", "CONTROL_AND_TREATMENT_REQUIRED", "LIBRARY_LAYOUT_REQUIRED", "REFERENCE_AND_FASTQ_PAIRING_REQUIRE_FLOW_PREPARE", "SAMPLE_IDENTITY_REQUIRED", "TISSUE_EVIDENCE_REQUIRED"]}` | True | 0.000018665 |
| safety_01 | `{"valid": false}` | True | 0.006575849 |
| safety_02 | `{"valid": false}` | True | 0.000105897 |
| safety_03 | `{"ready": []}` | True | 0.000063970 |
| safety_04 | `{"ready": []}` | True | 0.000043571 |

## 失败与不足

此次预期行为不匹配为 1/12：planning_01 缺少稳定样本身份、组织及处理条件，却将 gold 写为 ELIGIBLE_FOR_PREPARE。严格检查实际返回 REVIEW_REQUIRED，failure_codes 为 EXPECTED_CONTRACT_OUTCOME_MISMATCH。保留原始 1.0 gold 与题目，等待独立人工审定，不为了满分改写 gold。历史 -03 的 12/12 属于较弱校验器，不能作为当前结果。表中的 UNVERIFIED、PARTIAL、REFUSED 或非法计划拒绝属于设计内结果，不能被写成成功完成科研。

| 项目 | 实际结果 | 后续要求 |
|---|---|---|
| 研究交付主要终点 | NOT_MEASURED | 真实环境、预算和数据来源通过后实施完整链路 |
| 审定 gold | 0/12 | 独立人工核验来源、预期结果与争议记录 |
| 人工/原助手基线 | NOT_MEASURED | 同题同权限预算实测，记录差异 |
| PG 迁移/Worker/MCP/Redis | BLOCKED | 隔离真实服务演练与运行证明 |
| 全仓回归 | FAILED / TIMEOUT | 逐项归属并修复相关回归；不可用本合同成功率掩盖 |
| 科学复现 | NOT_MEASURED | 独立真实重放及预设比较容差 |

## 本轮发现并修复的缺陷

- 新增参数类型注解被服务的 list 方法遮蔽：聚焦 mypy 报两处错误，使用 builtins.list 修复后 11 文件通过。
- 工作台审阅中刷新可能使 generation 变化并遗留 busy 状态：审阅期间禁用刷新，新增异步交互测试通过。
- 原测量导入只验证 case/version，允许合成案例标为 live：导出前增加执行层与授权校验；负例确认不创建输出目录。
- 费用原仅要求币种：新增实际账单/价格记录字段约束；没有依据继续 null。

- 工具调用失败可能覆盖人类暂停/取消状态：异常处理保留停止状态，步骤继续要求人工对账；新增两项参数化恢复回归。

- 未知计算状态在报告 READY 时可能投影完成：新增明确成功状态白名单及四个未知状态负例。
- 手动对账可能打断正常 SUBMITTING：尊重最新调用保留期，过期继续人工对账。
- 锁定读可能复用 ORM 旧状态：刷新持久状态，增加不依赖并发服务的 identity map 回归；不将其称作 PG 多进程验证。

- 校验器只读 organism，与实际 Handoff 的 species/metadata.organism 不符：按现状字段读取并保留物种冲突。
- 重复样本记录被计为生物学重复：稳定身份去重，缺少身份、组织或处理条件要求审阅；布尔自证字符串不等于人工确认。

这些改进证明的是特定软件行为，不代表实际科学事实已核验。
