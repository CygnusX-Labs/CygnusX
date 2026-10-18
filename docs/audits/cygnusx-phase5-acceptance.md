# Phase5 验收矩阵

此矩阵区分测试覆盖与完整验收。PASS_ISOLATED 仅指列出的隔离检查，不升级为真实运行或生产通过。PARTIAL/NOT_MET/BLOCKED 均不表示完成。

## T01–T40

| 编号 | 要求 | 状态 | 证据与限制 |
|---|---|---|---|
| T01 | Plan schema 正确序列化/反序列化与版本验证 | PASS_ISOLATED | plan_phase5：roundtrip、digest、五份 schema 精确比对 |
| T02 | DAG 循环/重复/悬空依赖拒绝 | PASS_ISOLATED | plan_phase5：cycle/duplicate/dangling 负例 |
| T03 | 非法 StepKind 与工具白名单拒绝 | PASS_ISOLATED | plan_phase5：白名单、extra forbid、参数校验 |
| T04 | owner/project 可信上下文而非模型字段 | PASS_ISOLATED | storage/gateway_phase5：可信上下文；真实 JWT ASGI 与外 owner 拒绝 |
| T05 | 跨用户 DatasetVersion/Task 引用拒绝 | PASS_ISOLATED | storage_phase5、artifact_phase5：SQLite 中 owner/project 资源拒绝 |
| T06 | 修改 plan 后旧审批失效 | PASS_ISOLATED | storage_phase5：revision/history/review；gateway_phase5：过期审阅 |
| T07 | 一个读步骤无需危险写审批 | PASS_ISOLATED | gateway_phase5：真实协调路径；只读步骤无需业务写审批 |
| T08 | 写步骤无审批/布尔自证拒绝 | PASS_ISOLATED | gateway_phase5：拒绝模型自证；PLAN_ONLY 从不派发写动作 |
| T09 | 参数摘要变化拒绝 | PASS_ISOLATED | storage/gateway_phase5：计划 digest 与调用参数关联校验 |
| T10 | 未满足上游依赖不得调度 | PASS_ISOLATED | plan_phase5：ready_steps 只接受完成依赖 |
| T11 | 同步等待不会阻塞真实异步任务 | PARTIAL | 只读 timeout/reservation 已测；真实长任务及 Worker 断连未测 |
| T12 | 重复调度仅创建一次授权业务 Task | PARTIAL | prepare 幂等已测；本模式不创建业务 Task，不能证明授权 Task 并发唯一 |
| T13 | SUBMITTING 不明状态不自动重投 | PASS_ISOLATED | gateway_phase5：SUBMITTING reconcile-only，不重放 |
| T14 | SSE 中断后只凭真实 ID 恢复 | PARTIAL | 持久 ID 恢复已测；真实 SSE 中断/服务重启未测 |
| T15 | 项目切换时迟到响应被丢弃 | PASS_ISOLATED | ResearchPlanWorkbench 与 ProjectDetailResearchContext：迟到项目/版本响应被丢弃，失败清除旧上下文 |
| T16 | 取消计划不删除已完成资产 | PASS_ISOLATED | storage_phase5：cancel 保留既有资产；不操作任务取消 |
| T17 | 真实 Result Manifest 缺失不能 COMPLETE | PASS_ISOLATED | plan_phase5：实际任务投影缺少 manifest 不完整 |
| T18 | 报告失败不会触发重跑分析 | PARTIAL | 交付状态分离及 reconcile-only 已实现；真实报告失败恢复未测 |
| T19 | FASTQ 与 counts 工作流匹配正确 | PARTIAL | science_phase5 有类型检查；RNA 引用/配对需既有 Flow prepare，真实匹配未测 |
| T20 | TPM/FPKM/Series Matrix 不进入 DESeq2 | PASS_ISOLATED | science_phase5：TPM/FPKM/CPM/log/不支持类型拒绝 |
| T21 | 未核验来源的整数矩阵要求审阅 | PASS_ISOLATED | science_phase5：来源和语义缺口要求审阅 |
| T22 | 元数据/分组/配对不完整阻断 | PASS_ISOLATED | science_phase5：重复/分组/混杂/物种/配对缺口 |
| T23 | Evidence 引用丢失不声称 VERIFIED | PASS_ISOLATED | science/artifact_phase5：缺失引用 UNVERIFIED，有引用仍不等于 VERIFIED |
| T24 | 有冲突证据时标示矛盾 | PARTIAL | 纯领域函数支持显式冲突；尚无独立文献矛盾发现器 |
| T25 | 真实统计数值必须来自 Artifact | PASS_ISOLATED | artifact_phase5：实际临时统计表、SHA、单元格、NA、篡改拒绝 |
| T26 | 外部文献/检索提示注入不得执行写工具 | PASS_ISOLATED | gateway_phase5：外部注入无法发布/创建 Task；非真实 transport |
| T27 | Benchmark case manifest schema 与固定版本 | PASS_ISOLATED | benchmark_phase5：固定版本、12 候选、schema |
| T28 | Benchmark gold evidence 审核记录完整 | NOT_MET | 0 人工审定；字段拒绝伪造缺记录的 HUMAN_REVIEWED，不等于已有审核 |
| T29 | Benchmark 不含明文 token/敏感个人数据 | PARTIAL | 凭证负例扫描通过；仅合成数据，无独立敏感个人信息审计 |
| T30 | Metrics 分母、部分成功、UNKNOWN 处理正确 | PASS_ISOLATED | benchmark_phase5：未知、分母、无效分子、Wilson 区间 |
| T31 | 对重复案例运行不会覆盖原始结果 | PASS_ISOLATED | benchmark_phase5：独占创建目录，重复测量拒绝 |
| T32 | Benchmark Baselines 同权限/预算或显式差异 | PARTIAL | baselines.json 明确同预算与差异；A/B 尚未测量 |
| T33 | Evidence coverage 只计有效来源 | PASS_ISOLATED | benchmark_phase5：有效 numerator 与 required denominator；不是独立科学事实鉴定 |
| T34 | Reproduction score 使用预设比较规则 | PASS_ISOLATED | benchmark_phase5：预设 SHA/数值容差规则；非实际科研重放 |
| T35 | 安全越权负例执行端无副作用 | PASS_ISOLATED | gateway/storage/artifact_phase5：越权负例，无业务 Task 副作用 |
| T36 | 两进程 Redis 确认竞态 | BLOCKED | Redis socket 创建 PermissionError；无两进程 CAS 新证据 |
| T37 | 真 MCP Transport token、初始化、调用 | BLOCKED | 无本轮真 MCP transport 运行成功证据 |
| T38 | 实际 Worker 版本/路径/校验可追溯 | BLOCKED | Docker socket 拒绝；实际 Worker 镜像/路径/校验未回读 |
| T39 | 真实小型 counts/FASTQ 至双报告闭环 | BLOCKED | G0/G15 未解除；未下载或启动两个真实公开科研案例 |
| T40 | 固定 benchmark 可重复出逐例指标、失败清单 | PARTIAL | 合成契约导出及重复结果测试通过；完整 Research Agent 与真实科研指标未测 |

测试简称对应 `tests/unit/test_research_*_phase5.py`；计划 schema 测试为 `test_research_plan_phase5.py`。最新相关测试汇总在 `evidence/phase5/related-final.log`。

## G0–G18

| 编号 | 要求 | 状态 | 依据 |
|---|---|---|---|
| G0 | Phase 4 实施证据与前置运行 Gate 真实核验 | BLOCKED | 历史缺口与 socket 实测；见 entry-gates |
| G1 | 工作树基线与全部改动归属清楚 | PARTIAL | baseline.json 与变更清单；发布前仍需最终归属复核 |
| G2 | ResearchPlan Schema/版本/依赖验证稳定 | PASS_ISOLATED | 严格契约、DAG、版本、不可变意图与 schema 比对 |
| G3 | 两种 Agent 使用相同的可信规划/工具契约 | PASS_ISOLATED | 同 Gateway/ToolBridge 的双 Agent 契约测试；无真实 LLM 效果声明 |
| G4 | 身份/Project/Dataset/Task 资源隔离有效 | PASS_ISOLATED | SQLite/ASGI 资源归属负例；非全栈双用户验收 |
| G5 | 人工审批不可模型自证、重放、跨 owner 使用 | PARTIAL | JWT 计划审阅/过期/改版拒绝已测；原写工具真实 CAS 仍阻断 |
| G6 | 编排不绕过已有 TaskService / DownloadService | PASS_ISOLATED | 无新执行器；PLAN_ONLY 不派发写任务 |
| G7 | 异步状态、幂等、恢复/对账不重复副作用 | PARTIAL | 持久 reservation、调用关联与不重放已测；业务 Task 实际并发/重启待测 |
| G8 | 统计/输入类型与研究设计匹配 | PARTIAL | 合成输入及设计校验通过；真实 Flow/参考适用性未验收 |
| G9 | 科学结论绑定真实 Evidence 并保留缺口 | PARTIAL | 实际临时 Artifact cell 与引用缺口；不自动声称科学真实性 VERIFIED |
| G10 | Benchmark task/gold/baseline 版本化且无泄漏 | PARTIAL | 固定 registry/gold/protocol/baselines；人工审定和三组测量不足 |
| G11 | Benchmark 指标、分母、原始 trace 可复算 | PASS_ISOLATED | 13 类指标、明确分母、原始 JSONL/CSV、区间、未知值 |
| G12 | 至少 12 个审定初始基准任务（或如实不足） | NOT_MET | 12 候选；0 人工审定，不能称 12 个审定任务 |
| G13 | 前端计划/审批/任务/证据交互正确 | PARTIAL | 工作台与宿主项目上下文 8 项测试及类型检查通过；独立写审批入口和全栈交互未验收 |
| G14 | 故障和提示注入负例无未经授权副作用 | PASS_ISOLATED | 注入、跨用户、未知提交与伪造运行层级等负例 |
| G15 | Redis/MCP/PG/Worker 的真实运行链有证据 | BLOCKED | PG/Redis/Docker socket 拒绝；MCP/Worker 新运行证据缺失 |
| G16 | 至少两个小型真实公开案例有可复核数据与证据 | BLOCKED | 两个小型公开 counts/FASTQ 案例未启动 |
| G17 | 回归测试、文档、审计、回滚 Runbook 完整 | PARTIAL | 文档/回滚和聚焦回归已补；全仓门禁未绿、PG 演练未通过 |
| G18 | 实施报告明确准入状态与论文结论限制 | PARTIAL | 本报告明确限制；整体任务仍未完成，不能认定发布准入 |
