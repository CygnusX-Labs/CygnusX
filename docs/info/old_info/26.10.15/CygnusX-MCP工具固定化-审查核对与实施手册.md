# CygnusX MCP 工具固定化改造 · 审查核对与实施手册

> 本文档是活文档：本轮基于编码 Agent 的《MCP 工具数量调查》报告做核对并落实施计划；后续轮次的调整追加为新 Part，不另起文档。
> 验收权在用户手里：所有"验收通过"以用户按 checklist 手工验证为准，不接受编码 Agent 自报通过。

## Part 0 背景与范围

**要解决的问题**：平台每新增一个 Flow，MCP 工具数量就增长一次。当前三套接入方式并存：

1. Chat 内置 `cygnusx-tools`：由 `flows/*.yaml` 经 FlowToolSchemaCompiler 自动生成 `cygnusx_prepare_<flow_id>_submission`（每 Flow 一个）；
2. 内置 `cygnusx-pipelines` + 外部 MCP pipelines：RNA/ATAC 各配 prepare / submit / status / results 四件套；
3. 外部 MCP 通用工具 `cygnusx_submit_analysis(flow_id, parameters, …)`：已按 flow_id 分发，不随 Flow 增长。

`flows/` 现有 `rna_seq`、`atac_seq`、`counts_deg` 三个定义；`counts_deg` 受默认关闭的配置门控制——**"存在 YAML"≠"已开放运行"**。

**调查报告核心结论（本轮核对对象）**：把 MCP 工具固定为 6 个通用工具，Flow 作为目录数据增长；`AnalysisFlowToolService` 已具备 discover / describe / prepare / confirm_and_submit / get_task_status / get_task_summary，改造集中在 MCP 暴露层；渐进迁移。

**核对范围说明**：仓库代码不在本对话中，以下核对基于报告内部逻辑、MCP 协议常识与平台既有约定；所有文件路径 / 行号 / "方法已存在"的断言列入「施工前复核锚点」（Part 1.3），编码 Agent 开工前必须逐项确认，对不上先报差异，不得带错假设施工。

## Part 1 审查核对意见

### 1.1 确认成立（设计层面）

| # | 结论 | 说明 |
|---|---|---|
| C1 | 核心诊断成立 | 自动生成工具解决的是"手工维护"，不是"工具数量膨胀"；三条路径并存 = 三套暴露口径，统一暴露层是对的靶子。 |
| C2 | "固定动词 + 动态目录"方向正确 | MCP 协议支持结构化参数与 Resources，不要求"一流程一工具"。list + describe + 通用 prepare / submit 是工具数量不随资源数增长的标准形态，从两个 Flow 到几十个 Flow，工具清单不变。 |
| C3 | 最有价值的发现成立 | 若 `AnalysisFlowToolService` 确实已按通用 Flow 能力组织（六个方法齐备），本次改造主要是"暴露层对齐 + 校验对齐"，确认门与 TaskService.submit() 主链复用，工程量与风险都低。[施工前复核方法签名] |
| C4 | "不要把所有 Flow 的 oneOf 塞进通用 Schema"是正确的警告 | 那是把"工具清单膨胀"搬成"工具 Schema 膨胀"，模型上下文照样随流程数增长，且每次调用全量进上下文。固定工具的 inputSchema 必须小而稳定，flow 特定参数收进 arguments 对象。 |
| C5 | 人类确认红线正确 | 提交必须走服务端确认凭证：冻结参数、校验归属、单次消费、防重。绝不允许"模型传布尔值自证已确认"——安全 / 资损红线，统一入口不得削弱它。 |
| C6 | counts_deg 门控提醒必须带入新设计 | `list_flows` 的输出必须与"实际可提交的 Flow 集合"同源同判定，否则模型会看到不可提交的流程，白做一轮。 |

### 1.2 保留意见（报告需修正或补强的点）

| # | 意见 | 处理 |
|---|---|---|
| R1 | 命名一致性：报告建议的 `analysis_*` 与现有 `cygnusx_*` 命名空间割裂，建议沿用 `cygnusx_` 前缀；最终名以用户拍板为准。 | 施工前定名一次，全文统一。 |
| R2 | 迁移排期漏了路径一：报告"渐进迁移"句只点名旧 RNA/ATAC 四件套，Chat 自动生成的 per-flow prepare 工具（FlowToolSchemaCompiler 产物）也要排入"兼容包装 → 默认清单移除"的下线路径。 | 已补进阶段 3。 |
| R3 | 任务工具口径自相矛盾：报告一边说"日志、取消等继续复用通用任务工具"，一边把 task_status / task_results 列为新增固定工具。 | 阶段 0 必须先回答：现有通用任务工具到底覆盖了哪些能力。能复用则固定工具从 6 个降到 4 个（list / describe / prepare / submit），少即是多。 |
| R4 | 报告没有验收与测试计划。 | 各阶段补 checklist；阶段 2 建"校验对等矩阵"——不接受只跑单测。 |
| R5 | 契约漂移未提：prepare 到 submit 之间 Flow YAML 可能变更。 | 确认记录冻结契约版本 / 哈希，submit 校验，不符即拒绝并要求重新 prepare。 |
| R6 | 幂等未提：submit 网络重试不得产生重复任务。 | confirmation_id 单次消费；重复 submit 同一 confirmation_id 幂等返回既有 task_id，不得新建。 |

### 1.3 施工前复核锚点（编码 Agent 逐项确认，对不上先报差异）

- A1 `src/cygnusx/tools/flow_schema_compiler.py:29` —— 自动生成工具的入口与产物形态；
- A2 `src/cygnusx/application/services/analysis_flow_tool_service.py:53 / :98` —— 六个通用方法的存在性、签名、返回值；discover 是否已应用 counts_deg 门控；
- A3 `src/cygnusx/application/services/flow_service.py:51` —— 参数 Schema `"type": "any"` 的生成点；
- A4 `mcp-server/tools/analysis.py` —— 外部 `cygnusx_preview_analysis` 的现有校验深度；
- A5 `mcp-server/tools/pipelines.py` 与 `src/cygnusx/infrastructure/mcp/pipeline_preset.py` —— 四件套维护点与控制器注册点；
- A6 现有"通用任务工具"清单（日志 / 取消 / 状态 / 结果各自由谁提供）；
- A7 counts_deg 门控的配置项位置与判定函数。

## Part 2 目标形态

### 2.1 固定工具清单（命名按 R1 待拍板，暂用 cygnusx_ 前缀）

| 固定工具 | 作用 | Schema 原则 |
|---|---|---|
| `cygnusx_list_flows` | 可用流程简要目录，支持筛选；**输出 = 门控后的可提交集合** | 无 flow 特定字段 |
| `cygnusx_describe_flow(flow_id)` | 按需返回该流程完整输入契约（参数 Schema、样本表、约束） | 仅 flow_id |
| `cygnusx_prepare(flow_id, arguments)` | 全量校验输入，生成资源预览与待确认记录（含契约版本冻结） | 通用信封，flow 参数走 arguments 对象 |
| `cygnusx_submit(confirmation_id)` | 服务端校验确认凭证（归属 / 未过期 / 单次消费 / 幂等）后提交 | 仅 confirmation_id |
| 任务状态 / 结果 | **优先复用现有通用任务工具**；确无则补 `cygnusx_task_status` / `cygnusx_task_results` | 通用 task_id |

重申 C4：任何 flow 特定参数不进固定工具的字段层，统一收在 `arguments`（object），以 `describe_flow` 契约为校验依据。

### 2.2 目标链路

```
list_flows(带门控) → describe_flow(按需契约) → prepare(全量校验+冻结契约)
→ 人类确认(服务端凭证) → submit(凭证校验+幂等) → 复用通用任务工具查状态/结果/日志/取消
```

### 2.3 扩展的两层承载

- **声明式契约**：参数、样本表、资源、执行映射继续放 `flows/*.yaml`；
- **代码扩展点**：数据预检、特殊结果解析做成后端插件，由流程配置引用（如 FASTQ 预检 RNA/ATAC 共用）；**插件不增加 MCP 工具**。

新增 Flow 仍需部署流程代码 + Worker 验收，但不再新增 MCP 工具。

## Part 3 分阶段实施

> 每阶段独立可验；阶段 0 是止血前置包——不依赖后续架构改动，收益最快、与后续零冲突。所有阶段开工前先完成 Part 1.3 锚点复核。

### 阶段 0 · 止血前置包（半天级，零架构改动）

**目标**：立刻停止工具数量增长；外部 MCP 立刻获得固定目录能力。

**三件事**：

1. **冻结政策（零代码）**：开发约定写入"新增 Flow 不得新增 MCP 工具，只能注册流程契约"（新流程一律走既有 `cygnusx_submit_analysis`，阶段 1 后改走统一入口）。
2. **目录工具上线（只差一次登记）**：外部 MCP 新增 2 个只读工具 `cygnusx_list_flows` / `cygnusx_describe_flow`，底层直调 `AnalysisFlowToolService.discover / describe`（方法已存在——若 A2 复核发现不存在，停下报差异）。`list_flows` 必须应用 counts_deg 同款门控，输出只含简要字段（id、名称、一句话描述、类别标签）。
3. **软弃用标注（仅改 description，不动行为）**：旧四件套与自动生成的 per-flow prepare 工具，描述首行加 `[DEPRECATED] 将由统一固定工具替代，新集成请勿使用`。

**提示词（粘贴给编码 Agent）**：

```text
只做阶段 0，不改任何行为逻辑：
1. 先复核（只读）：确认 AnalysisFlowToolService 存在 discover()/describe(flow_id) 方法（src/cygnusx/application/services/analysis_flow_tool_service.py），记录签名与返回值结构；确认 counts_deg 的门控配置项与判定函数（默认关闭）。以上锚点对不上就停下报告差异，不要施工。
2. 在 mcp-server 注册两个只读工具 cygnusx_list_flows（filter 可选）与 cygnusx_describe_flow(flow_id)，底层直调上述服务方法；list_flows 只返回门控后"可提交"的流程（id、名称、一句话描述、类别标签），describe 返回该流程的完整输入契约。两个工具只读，无副作用，不触碰提交链路。
3. 软弃用标注：给内置 pipelines 四件套与自动生成的 cygnusx_prepare_<flow_id>_submission 工具的 description 首行追加 "[DEPRECATED] 新集成请使用 cygnusx_list_flows / cygnusx_describe_flow / 统一提交入口"，不改动任何行为。
4. 禁止：不得重构 FlowToolSchemaCompiler、不得动 prepare/submit 逻辑、不得修改 flows/*.yaml。
```

**验收 checklist**：

| 操作 | 期望现象 | 不通过处理 |
|---|---|---|
| 外部 MCP 客户端调用 list_flows | 返回门控后的流程目录（默认不含 counts_deg） | 门控未接入，回退修复 |
| 调 describe_flow("rna_seq") | 返回完整参数契约（类型、必填、样本表要求） | 对照 FlowToolSchemaCompiler 产物核对 |
| 调 describe_flow("counts_deg") | 返回"不存在/未开放"类错误 | 门控泄露，回退 |
| Chat 内跑一次 rna_seq 原流程 | 行为与标注前完全一致 | description 改动误伤行为，回退 |
| 新增一个假 flow YAML（测试后删） | 工具清单数量不变，目录多一项 | 自动生成仍在扩张，查注册链 |

### 阶段 1 · 统一 prepare/submit 入口

**目标**：固定工具接管提交主链；内外 MCP 共用同一服务，消灭口径漂移。

**要点**：

- `cygnusx_prepare(flow_id, arguments)` 底层调 `AnalysisFlowToolService.prepare()`，**全量接入 FlowSubmissionValidator**（补齐外部 preview 浅校验的差距，C5 前置）；
- 确认记录服务端冻结：参数快照 + 契约版本/哈希 + 归属 + 过期时间（建议 15–30 分钟，可配置）；
- `cygnusx_submit(confirmation_id)`：校验归属/未过期/单次消费（原子操作防并发重放）；同一 confirmation_id 重试幂等返回既有 task_id；**绝不接受模型布尔自证已确认**；
- Chat 内置与外部 MCP 注册完全相同的工具定义，底层同一服务实现。

**提示词（粘贴）**：

```text
实现阶段 1（先完成 Part 1.3 锚点复核，对不上先报差异）：
1. 新增固定工具 cygnusx_prepare(flow_id, arguments: object) 与 cygnusx_submit(confirmation_id)。
2. prepare 底层完整复用 AnalysisFlowToolService.prepare() 与 FlowSubmissionValidator（不允许只做浅必填校验）；确认记录必须冻结：arguments 快照、describe_flow 契约的版本/哈希、创建者与所属工作区、过期时间（默认 30 分钟，可配置）。
3. submit 服务端校验：凭证存在、归属匹配、未过期、未消费；消费为原子操作（防并发重复提交）；同一 confirmation_id 重试返回既有 task_id 与状态，不新建任务。
4. Chat 内置 cygnusx-tools 与外部 MCP 注册完全相同的工具定义与底层服务调用；不得保留两份实现。
5. 禁止改动 RNA/ATAC 旧四件套行为（阶段 3 才动）；禁止让 arguments 的校验依赖模型自报；禁止用布尔参数代替确认凭证。
```

**验收 checklist**：

| 操作 | 期望现象 | 不通过处理 |
|---|---|---|
| 缺必填参数 prepare | 被拒绝并列出缺失项（与旧 Chat 路径一致） | 校验未全量接入，回退 |
| 合法 prepare → 确认 → submit | 任务创建成功，参数与预览一致 | 查冻结快照 |
| 同一 confirmation_id 连续 submit 两次 | 第二次返回既有 task_id，任务列表仅一条 | 幂等失效，查消费原子性 |
| 篡改 confirmation 对应 arguments 后 submit | 拒绝（快照哈希不符） | 冻结失效，回退 |
| 凭证过期后 submit | 拒绝并提示重新 prepare | 过期机制缺失 |
| Chat 与外部 MCP 各跑一次同参数提交 | 校验结果、任务产物一致 | 双口径残留 |
| 旧四件套回归测试 | 全部通过、行为不变 | 误伤旧路径，回退 |

### 阶段 2 · 校验对齐与契约严格化

**目标**：新入口校验强度 ≥ 旧 pipelines 路径；参数 Schema 成为严格契约。

**要点**：

- 把 pipelines 控制器里的工作区数据检查、样本-FASTQ 匹配检查抽成**可复用校验插件**，统一 prepare 按流程配置调用（旧路径行为不变）；
- 修复 `flow_service.py` 参数 Schema `"type": "any"`（A3 复核定位生成点）：复用 FlowToolSchemaCompiler 的编译产物，让 describe_flow 返回严格类型契约；
- 建**校验对等测试矩阵**：对每类非法输入（缺参/类型错/样本表缺列/FASTQ 不匹配/工作区无数据/超资源配额），旧路径拒绝的，新路径必须同样拒绝；只有单测通过不算完，Chat 与外部 MCP 两条链路都要 e2e；
- 补契约漂移处理（R5）：prepare 冻结契约版本/哈希，submit 校验。

**提示词（粘贴）**：

```text
实现阶段 2：
1. 抽取校验插件：将 pipelines 控制器中的"工作区数据检查"与"样本-FASTQ 匹配检查"抽为可复用校验插件，由流程 YAML 配置引用；统一 prepare 按配置调用。旧路径行为不得变。
2. 修复参数 Schema：定位 flow_service.py 生成 "type": "any" 的位置，改为复用 FlowToolSchemaCompiler 的编译产物，使 describe_flow 输出严格类型契约。
3. 写校验对等测试矩阵：覆盖 缺必填 / 类型错误 / 样本表缺列 / FASTQ 不匹配 / 工作区无数据 / 超资源配额 六类，逐类断言旧路径与新路径的拒绝行为一致。e2e 跑通 Chat 与外部 MCP 两条链路后才算完成。
4. prepare 确认记录冻结契约版本/哈希；submit 校验，不符即拒绝并要求重新 prepare。
```

**验收 checklist**：

| 操作 | 期望现象 | 不通过处理 |
|---|---|---|
| 跑校验对等矩阵（6 类非法输入 × 2 路径） | 新旧路径拒绝行为一致 | 列差异清单逐条修，不进入阶段 3 |
| describe_flow 返回契约 | 无 "type": "any"，类型/必填/枚举齐全 | 编译产物未接上 |
| 改 YAML 参数后 submit 旧 confirmation | 拒绝并要求重新 prepare | 漂移防线缺失 |
| 旧四件套回归 | 行为不变 | 抽插件时误伤 |

### 阶段 3 · 切换与旧工具下线

**目标**：旧工具全部转为兼容包装，默认发现清单只剩固定工具。

**要点**：

- Chat 自动生成的 `cygnusx_prepare_<flow_id>_submission` 停止生成（FlowToolSchemaCompiler 改为只产出目录数据），Chat 提交链路改走统一固定工具；
- 旧 RNA/ATAC 四件套改为**兼容包装**：内部转调统一服务，对外行为与错误信息不变；
- 从默认工具发现清单移除旧工具（代码保留 + 配置开关可回退）；提供 `LEGACY_PIPELINE_TOOLS=true` 供存量外部客户端过渡；
- 灰度：测试环境全量回归（Chat 链路 + 外部 MCP 链路 + 旧客户端包装）通过一周后，再切默认清单。

**提示词（粘贴）**：

```text
实现阶段 3：
1. 改造 FlowToolSchemaCompiler：停止向 Chat 注册 per-flow prepare 工具，改为只产出目录数据（供 list_flows 使用）；Chat 提交链路改走 cygnusx_prepare / cygnusx_submit 固定工具。保留编译器对 flows/*.yaml 的契约编译职责。
2. 将内置 pipelines 四件套与外部 MCP pipelines 工具改为兼容包装，内部转调统一服务，对外行为与错误信息保持不变。
3. 从默认工具发现清单移除旧工具；新增配置项 LEGACY_PIPELINE_TOOLS=true 可临时恢复（默认 false）。代码与测试保留一个版本周期。
4. 灰度：先在测试环境全量回归（Chat 链路 + 外部 MCP 链路 + 旧客户端兼容包装），通过后再切默认清单。
```

**验收 checklist**：

| 操作 | 期望现象 | 不通过处理 |
|---|---|---|
| 工具发现清单 | 只剩固定工具 + 通用任务工具 | 有漏网旧工具 |
| Chat 跑 rna_seq / atac_seq 各一次 | 走固定工具，产物与旧版一致 | 比对产物清单 |
| 旧客户端调四件套（LEGACY=true） | 行为不变（包装层） | 包装层行为漂移 |
| 新增 flow YAML | 工具清单数量不变，目录多一项 | 自动生成复活 |
| 关闭 LEGACY 后调旧工具 | 客户端收到明确"已迁移"提示 | 错误信息不友好 |

### 阶段 4 · 扩展契约定型与文档

**目标**：新增 Flow 的标准接入路径成文，插件机制定型。

**内容**：

- 后端插件机制落地（预检/结果解析插件接口 + 流程 YAML 引用方式）；
- 《新增 Flow 接入指南》：只写 flows/*.yaml + 可选插件 + Worker 验收，**不新增 MCP 工具**；
- 以一个真实新 Flow 走一遍完整流程（目录 → describe → prepare → 确认 → submit → 结果）作为验收。

## Part 4 验收总表

| # | 验收项 | 谁验 | 阶段 |
|---|---|---|---|
| 1 | 工具清单固定：新增 Flow 后工具数不变 | 用户手测（客户端工具列表） | 0 / 3 |
| 2 | list_flows 输出与门控后可提交集合一致 | 用户手测 | 0 |
| 3 | prepare 全量校验与旧路径一致（对等矩阵） | 编码 Agent 跑测试 + 用户抽测 | 2 |
| 4 | 确认凭证：冻结 / 归属 / 过期 / 单次 / 幂等 | 用户手测（阶段 1 checklist 前 5 行） | 1 |
| 5 | Chat 与外部 MCP 双链路各 e2e 一次 | 用户手测 | 1 / 3 |
| 6 | 旧客户端兼容包装行为不变 | 编码 Agent 回归 + 用户抽测 | 3 |

## Part 5 风险与回退

| 风险 | 缓解 |
|---|---|
| 锚点复核发现服务方法与报告不符 | 各阶段前置：对不上即停工报差异，不带错假设施工 |
| 统一入口校验弱于旧路径（验收项 3 挂） | 阶段 2 对等矩阵兜底；不通过不进入阶段 3 |
| 旧外部客户端被打断 | 兼容包装 + LEGACY 开关 + 明确迁移提示 |
| 确认凭证被绕过（资损 / 重复任务红线） | C5 红线：submit 只认服务端凭证；任何"布尔自证"在代码评审直接打回 |
| 目录随流程数膨胀（list 输出过长） | list_flows 只给简要字段 + 支持筛选 / 分页；细节永远走 describe_flow |
