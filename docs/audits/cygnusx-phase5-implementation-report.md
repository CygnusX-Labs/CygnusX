# Phase5 实施报告：PLAN_ONLY 与合成隔离验证

本报告记录当前未提交工作树，不是完工或发布证书。逐项状态见 [验收矩阵](cygnusx-phase5-acceptance.md)。

## 1. Executive Summary

已实现受限 ResearchPlan 协调、共享规划契约、科研适用性及 Artifact 数值校验、项目工作台和合成 Benchmark 基础设施。当前 PLAN_ONLY；不提交下载、分析或发布业务任务。完整 P5-B、真实科研 Benchmark、两个公开案例和生产验收未完成。不存在 Research Agent 优于人工/助手的测量结论。

## 2. Baseline / Branch / HEAD / Dirty Worktree

分支 `feat/research-agent-phase5`，基线 `51011118535f782f5282f638b4a54649c79bf6d6`。`evidence/phase5/baseline.json` 保存基线状态、子模块及文件 SHA。此前 `.env.example`、五个子模块以及任务目录已有未提交内容；本轮保留。不提交、推送或部署；文件索引见 `cygnusx-phase5-changes.md`。

## 3. Phase4 与历史门禁

Phase4 代码及隔离测试不代表真实双报告链路完成。历史 Worker 来源/实际挂载和真实 MCP/Redis 门禁没有新增闭合证据。当前 socket 探测在创建 Docker/PostgreSQL/Redis socket 时 PermissionError，尚未连接业务服务。见 [准入核验](cygnusx-phase5-entry-gates.md) 和本地 `runtime-probes.json`。G0/G15/G16 阻断，不能以配置默认值代替真实版本核验。

## 4. ADR 与复用

[ADR](../adr/phase5-governed-research-agent-orchestration.md) 比较 RunPlan、FlowAgent、MASPlan/MASRun 和 AgentRuntimeGateway。新表仅表示版本化研究意图和协调状态；真实执行仍归现有服务。两个 Agent 保持各自 Runtime，共享 ToolBridge/AgentToolGateway，不新增 LLM loop、下载器、shell 通路或统计执行器。现状图见 `ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md`。

## 5. DTO、状态机、审阅与工具

[契约](../contracts/cygnusx-research-plan-v1.md) 与五份 JSON Schema 分离模型 draft 和服务器 View。严格 StepKind、DAG、类型 binding、资源归属、预算和参数校验；版本更改不继承审批。JWT 人类审阅绑定 digest，与原工具独立写审批分离。advance 每次最多一个只读/prepare 步骤；先持久化 reservation，再关联实际 Invocation。未知状态只对账；新鲜调用保留期内不被手动对账打断，锁定读刷新 ORM 缓存。计算状态仅 success/completed 可投影成功；写步骤保持等待，未提供完整 live dispatch。ORM/PG trigger 保护意图不可变，真实 PostgreSQL trigger 尚未演练。

## 6. 科研语义与 Claims

服务器 Handoff 按实际 species/metadata.organism 字段读取物种并检查冲突；缺少稳定样本身份、组织或处理条件要求审阅，重复记录不增加生物学重复数。检查 raw counts 与 TPM/FPKM/CPM/log/不支持类型、样本分组、重复、配对、物种和混杂缺口。RNA 引用与成对文件仍需既有 Flow prepare。Claim 引用存在只得到 PARTIAL，不自动等于科学事实 VERIFIED；缺失 UNVERIFIED，显式冲突保留 CONTRADICTORY。统计 cell 必须取自实际注册、owner/project 匹配、SHA 核验的 Artifact；单元格包含实际行、列及来源。临时真实文件测试不等于公开科研结果验证。

## 7. Benchmark 构建与审定

`benchmarks/research_agent/v1/cases` 有 12 个固定合成候选，三类各 4；不是 12 个审定科研任务。人工审定数量 0，G12 NOT_MET。题目主要覆盖 grounding、输入和安全契约，完整数据发现/工作流匹配覆盖不足。无公共研究数据、无数据下载、无真实许可核验。不得虚构审阅者、accession、p 值或研究结论。

## 8. Baselines、配置与成本

`baselines.json` 披露 A/manual、B/existing_assistant 尚未测量；C/contract_candidate 为无 LLM 的确定性检查器，不是已测完整 Research Agent。共享预算 30 秒/题、网络关闭、真实执行关闭、重试 0。模型、prompt、温度、Token 和费用没有实际测量时为 null。金额必须附币种及真实账单/价格记录；字段存在也不能替代独立审计。

## 9. 指标、结果、分母与不确定性

13 类指标及计算规则见评估协议和 `domain/research/benchmark.py`。比例导出 numerator/denominator/not_evaluated 与 Wilson 95% 区间；时间和费用保留原始值，UNKNOWN 不冒充成功，不合并币种。预设 SHA 或固定数值容差用于重放比较；没有真实科研重放记录。

历史 `benchmark-contract-03` 在较弱校验下有 12/12 预期匹配；当前 -07 为 11/12，Wilson 95% 区间约 [0.646, 0.985]。planning_01 的固定 1.0 gold 尚未审定，缺少样本身份、组织和处理条件却预期可准备分析；严格检查返回 REVIEW_REQUIRED。保留题目/gold，并导出 EXPECTED_CONTRACT_OUTCOME_MISMATCH，不为了分数重写历史。这里 success 仍只指契约预期匹配，不是科研任务交付。

有效计划为 0/2（两份非法计划）；发现、匹配、真实科研复现及主要科研终点未评。逐例 JSONL/CSV、summary、manifest 和源码快照保存在 `evidence/phase5/benchmark-contract-07`；逐例摘要和失败分析见 `benchmarks/research_agent/v1/contract_results_analysis.md`。A/B 未测，不排序。

## 10. 测试与环境层级

- 最新 `.venv/bin/pytest` 六个 Phase5 测试文件及共享 Phase2/Phase4：158 passed，3 warnings；`related-science-final.log`。较早 `related-final.log` 的 143 passed 为历史记录。
- 最新恢复专项：计划/存储/协调 52 passed（包含未知计算状态、保留期、停止状态和 ORM 缓存刷新）；`recovery-final.log`。
- bridge 隔离回归：190 passed、2 skipped、7 warnings；`bridge-final.log`。
- 发布 schema 与运行 DTO：五份精确比对；计划测试文件共 27 passed。
- 最新工作台与项目宿主上下文测试共 8 passed；前端 type-check 退出 0。覆盖指定持久版本恢复、同项目版本竞态、项目总览切换与错误隔离；原工作台 4 项结果为历史记录。最新构建命令退出 0（frontend-context-build.log/.exit），`frontend/dist/index.html` 在本次构建刷新；构建日志只有启动行，因此同时保留命令退出记录与产物信息。
- 新代码聚焦 mypy 检查 11 文件通过；最新结果见 `focused-types-final.log`。曾发现 list 方法遮蔽类型，现已修正。
- 迁移链直接 Python 检查通过；uv 命令因只读 cache 退出 2，未运行检查。未安装或更新依赖。
- 全仓 Ruff 295 项、mypy 1044 项错误；未逐项完成归属分析，不能全部称为基线问题。最新前端全量 530 passed、7 failed（frontend-full-context.log）；历史为 525 passed、7 failed；后端全量 180 秒 timeout（124），途中已有失败，不算全绿。单独复现 Agent 配置检查为 1 failed/9 passed：傻妞 prompt 缺少标准章节，未修改该 prompt。
- PG/Redis/MCP/Worker/公开案例均 BLOCKED 或 NOT TESTED。历史运行不自动当成本轮通过。

原始证据保存在本地 `evidence/phase5`，按仓库运行证据规则不入提交；验收前需由维护者归档保存并核验哈希。

## 11. 工作包状态与修改索引

P5-0 已完成本地准入审计，运行缺口未解除。P5-A 核心隔离实现，真实双 Agent 交互待测。P5-B 只读协调/持久恢复部分实现，授权业务任务编排和真实异步恢复未完成。P5-C 隔离实现，科学真实性仍需要实际来源与人工审查。P5-D 有候选与 registry，审定不足。P5-E 指标与导出实现，无完整三组实验。P5-F 工作台已补指定版本持久链接与宿主项目响应隔离；全栈连续性和写审批入口仍待验。P5-G 仅隔离验证，live 阻断。文件级索引见配套 changes 文档。

## 12. G0–G18 与 T01–T40

[逐项矩阵](cygnusx-phase5-acceptance.md) 覆盖全部 59 项，明确隔离 PASS 与 PARTIAL/NOT_MET/BLOCKED。G0/G15/G16 尚未通过；G12 审定不足；G17 全仓回归未绿。不得宣称 RELEASE_READY 或 CONTROLLED_LIVE_VALIDATED。

## 13. 风险、泄漏与越权

隔离负例涵盖模型身份/批准/路径注入、外部文本发布指令、跨 owner/project、审阅过期、改版、未知投递、凭证、非法分母和合成案例冒充 live。未观察到业务 Task 副作用。仍缺真实 Redis 两进程竞态、MCP transport 与多进程 PG 验证。凭证字段拒绝并不是对任意个人信息的完整 DLP 证明。

## 14. 两个真实科研案例

公开 raw counts→CountsDEGFlow→双报告：NOT STARTED。公开小 FASTQ→RNAFlow→双报告：NOT STARTED。原因是前置运行门禁未解除，资源与数据授权亦未具备。没有伪造数据集、输入指纹、运行版本或完整报告。将来需先核验真实来源/许可/规模/预算、Worker 与参考，再保留 Task、Manifest、Artifact、两类报告和重放证据。

## 15. 可复现包与论文边界

合成包可固定输入重复执行并导出原始记录，输出目录独占创建，源码 SHA 与快照保留。可陈述：这些特定契约负例得到预期处理、统计计算器使用明确分母。不可陈述：自主科研、发现准确率、真实科研复现率、相对人工/助手提升、显著性、成本节省、生产可靠性。所有图表必须带 SYNTHETIC_CONTRACT / CONTRACT_VALIDATION 标签。

## 16. 回滚与 Phase6

[回滚 Runbook](../runbooks/cygnusx-phase5-rollback.md) 说明默认关闭、保留不确定调用对账、代码 revert 和数据库备份/依赖检查。未部署不执行实际 downgrade。Phase6 不准入：首先补齐历史真实门禁、隔离 PG 迁移、完整安全编排与全栈验证、人工审定和三组真实测量。当前目标保持未完成，等待后续缺口处理与人工验收，不以本报告替代完成证明。
