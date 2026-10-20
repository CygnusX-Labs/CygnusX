# AI 助手与工作台

CygnusX 的 AI 功能以 Agent 为入口：用户可以在普通对话中获取解释和轻量协助，也可以在工作台中
结合工作区文件、平台工具、技能和受控运行环境完成分析任务。Agent 只负责需求解析、计划、调度
和结果解释；流程执行、数据写入与正式交付仍由平台既有服务完成。

## 四种执行形态

| 形态 | 入口 | 特点 |
| --- | --- | --- |
| 普通对话 / Agent | 星尘 AI 对话页 | 流式问答、专家路由、工具调用、人工审批 |
| OmicStudio 工作台 | 工作台会话 | 一会话一容器，可写代码、跑命令、保留工作区文件 |
| AgentTeams 协作室 | 协作 Case | 跨角色交接、人工审批、长期协作闭环 |
| 流程 / Worker | 分析中心提交 | 真实计算由 Snakemake + Worker 执行，AI 不直接运行流程 |

底层运行时以 `execution_path` 标识五条实际发射路径：`chat_langgraph`（默认）、`chat_legacy`（回退）、
`studio_chat_loop`、`agentteams_worker_react`、`agentteams_tool_execution`。早期文档中的
`agentteams_manager_consultation` 未在代码中发射，Manager 会诊事件记录为 `agentteams_worker_react`。
该字段只用于观测和排障，不替代权限判断。

## 一次对话如何执行

```text
用户消息
  → Router 选择目标 Agent（失败回落 general）
  → AgentContextBuilder 装配配置 / 记忆 / 知识 / 技能 / 工具
  → LangGraph ReAct 或 Legacy ReAct 循环
  → 工具调用（平台工具 / MCP / Skill / Flow / Studio）
  → llm_payload 回灌模型，ui_payload 投影前端
  → 统一生命周期事件落库 + SSE 终态
```

- **装配数据驱动**：Agent 声明位于 `data/ai/*.yaml`，启用清单以 `data/CygnusX.yaml` 的
  `agents.enabled` 为准（当前 19 个）。
- **最小权限**：每次请求按 Agent 配置、用户能力覆盖、会话模式和请求开关重新裁剪工具集合。
- **双通道结果**：模型只看到 `llm_payload`；前端展示 `ui_payload`，两者不混用。
- **循环保护**：工具轮数上限、重复调用检测、无进展保护，超限产生明确的终止事件。
- **流式落库**：SSE 增量输出，消息内容按批更新，断线不丢失已产生的记录。

## 当前能力

- **流式对话**：聊天响应通过 SSE 增量返回，工具调用、进度、审批和错误会以结构化事件显示。
- **专家路由**：星尘 AI 会按任务方向转给通用、RNA-seq、ATAC-seq、单细胞、代码等最匹配的
  专家，而不是固定启用全部助手。
- **知识与检索**：平台功能和已审核方法优先使用知识库检索；需要时效性且没有对应平台工具时，
  才补充联网检索，并明确实际执行过的检索来源。
- **工具与技能**：已授权 Agent 可使用工作区文件、平台工具、MCP 和 Skill；工具是否可用取决于
  当前 Agent、会话、权限和部署配置。技能按 L1/L2/L3 渐进披露，单会话最多激活 10 个。
- **工作台**：适合文件驱动、工具执行和需要保留过程产物的任务；没有明确数据时会先澄清，或在
  明确说明前提下使用示例数据演示。
- **过程可追溯**：工具调用按 `tool_call_id` 串联 started / result / context_reinjected 事件；
  会话日志可在管理端按会话时间线排查。

## 主要 Agent

| Agent | 适用任务 |
| --- | --- |
| 星尘 AI / 通用助手 | 日常问答、目标澄清、专家路由 |
| RNA-seq、ATAC-seq、单细胞专家 | 对应组学的设计、分析与结果解读 |
| 数据管理员、质量审计员、交付报告员 | 输入完整性、质量门、交付清单和证据汇总 |
| 代码助手 | 生信脚本编写、调试和受控沙盒执行 |
| MCP 构建师 | 实验性 MCP 工具的规划、生成和测试；发布需审核 |
| 傻妞 | 陪伴式多组学问题梳理和研究思路协助 |

完整角色边界与协作模式见 [AI 多 Agent 协作](ai-collaboration)，装配与运行细节见
[Agent 运行时](../architecture/agent-runtime)。

## 对话与执行边界

1. 简单问答、概念解释和单一小任务通常直接完成，不需要启动复杂协作。
2. 涉及真实数据、工作流执行、写入操作、长耗时任务或正式交付时，助手会先确认关键输入、计划和
   授权范围；确认只能由人类用户完成，模型不能自证确认。
3. 工作区、上传文件和会话上下文彼此隔离；不能将其他会话中的文件默认用于当前任务。
4. Agent 不拥有 shell、流程 YAML 或数据库写权限；代码执行只发生在沙箱内。
5. AI 结论应结合实验设计、数据质量和人工审核，不替代研究者的最终判断。

## 证据边界

- 对话、工具事件和审计记录属于**运行证据**，不代表科研结论已经成立。
- 工具调用成功 ≠ 真实计算完成：Flow 提交仍需人类审批，Worker 执行与运行验收另行判定。
- 具体能力是否可用，以当前部署配置、模块注册和权限为准；本文不承诺所有环境均已开启。
- 当前科研链路的验收状态见 [科研证据边界](../research/evidence-boundaries)。

## 配置与维护

- Agent 声明、工具包和提示词位于 `data/ai/`，属于运行配置，不应直接作为面向普通用户的知识库
  正文。
- 修改内置 Agent YAML 后运行时按配置热重载；提示词须经管理端 API 发布才写入数据库生效。
- 共享提示词片段由 Agent 加载器统一追加，应修改 `data/ai/prompts/shared/*.md` 而非逐 Agent 复制。
- 平台功能说明维护在 `wiki/` 和 `docs/knowledge/platform/`，并由知识库同步脚本建立检索索引。

## 相关页面

- [AI 多 Agent 协作](ai-collaboration)
- [Agent 运行时](../architecture/agent-runtime)
- [沙箱与工作台](../architecture/sandbox)
- [技能体系](../architecture/skills)
- [实验室知识库](knowledge-base)
- [云端沙盒终端](sandbox-terminal)
