# Research Agent v1 评估协议

状态：**合成契约评测包，待人工审定；不支持论文效益或生产结论**。

首版包含 12 个固定合成候选（发现/证据 4、输入/规划 4、安全恢复 4）。没有权威公共研究数据，也没有虚构 GSE、p 值或人工审核者；`review_status=PENDING_HUMAN_REVIEW`，审定数量为 0，G12 未通过。这些题主要验证证据拒绝与契约，不能代表完整数据发现能力。人工审阅者需确认题目、gold、预算、来源、许可证与争议记录，然后追加真实审核记录；开发者自测不等于独立审定。

## 系统和公平性

- A/manual：研究人员使用现有 UI/CLI，同题/硬件/权限/预算；**NOT_MEASURED**。
- B/existing_assistant：既有助手，无新计划协调，披露模型与提示词、工具权限差异；**NOT_MEASURED**。
- C/contract_candidate：本轮确定性合同与科学检查器，无 LLM；**只测软件契约**。不是已测量的完整 Research Agent，不与 A/B 作提升比较。

完整 Candidate C 的 Agent、人工基线和助手测量仍待真实环境和预算。将来通过 `--measurements` 导入原始逐例 JSONL；不能用计时模拟人工/LLM。原始 trace 必须区分模型建议、人类审阅、真实工具事件。共享机器/模型差异不明时不作因果比较。人工审批也计入干预次数。金额缺少价格证据为 null；本次无模型，不伪造 Token/模型版本/费用。

## 固定边界与防泄漏

runner 只向候选传 `public_input`，gold/case_id 只供外部 scorer；不把题目加入 Agent prompt/RAG。合成安全消融仅离线，不关闭业务门禁。网络/真实执行默认禁止，重试 0；每题 30 秒预算，平台另有计划/工具上限。固定 case/version、代码/输入 SHA 和实际 HEAD，未提交源码由 SHA 标识。随机值仅为测量 ID，不影响科学输入；数据 UUID 已固定在 JSON。无真实科研 Case、无预设公开 accession。

## 指标与统计

`domain/research/benchmark.py` 提供统一分子/分母、Wilson 95% 区间、缺失计数、逐次时间/成本值和失败列表。UNKNOWN/未测为 null，不从分母里冒充成功；required evidence/edges 中缺失项计入分母且不计 numerator。重复题目不是独立样本，不以 CI 推断显著优势；不同层级/目标/系统分别汇总。Task Success 在本次仅指 CONTRACT_VALIDATION 目标，绝不表示完成下载/分析/报告。

真实重放必须提供预先确定的 comparison rule、独立 attempt 和 matched 记录。重复运行合同验证不是科研复现。主要终点预设为真实任务成功率，次要为有效计划、证据、工作流匹配、安全、恢复、人工干预、时间和成本；主要终点当前 NOT_MEASURED。

## 运行和封存

```bash
.venv/bin/python scripts/evaluate_research_benchmark.py --output evidence/phase5/benchmark-contract-01
# 每次必须使用新目录，已存在即拒绝覆盖
.venv/bin/python scripts/evaluate_research_benchmark.py --measurements measured.jsonl --output evidence/phase5/measured-01
```

产物为逐条 JSONL、CSV、summary 和 experiment_manifest。失败不能删除，保留 error code。case 审核和基线缺口不能因合成 12/12 匹配而变为 PASS。至少两个公开 counts/FASTQ 至双报告案例、独立重放、模型比较与资源成本需先通过 G0/G15 和授权，当前 BLOCKED。

## 当前未审定案例缺口

固定 1.0 的 planning_01 缺少稳定样本身份、组织和处理条件，旧 gold 却预期 ELIGIBLE_FOR_PREPARE。更严格检查返回 REVIEW_REQUIRED；最新 -07 导出 11/12 预期匹配。保留此失败，待独立审定后以新版本修订题目或 gold，禁止回改历史结果来获得满分。
