# 模型路由与 Token 计费

本页合并两个相邻但不同的主题：**用哪个模型**（Router / ModelSelector）与**用了多少、扣多少**（usage / token / 饼干）。两者的共同原则是：模型请求的实际结果以 Provider 返回为准，平台不根据文本长度猜测账单。

> **当前状态**：动态模型路由默认关闭；开启后由 Router 选择目标 Agent 与复杂度，ModelSelector 只在既有执行路径内替换 Provider 配置。Token usage 归一化、会话累计和饼干扣费已落地。

## 动态模型路由

```text
用户请求
  → Router（专家意图 + complexity：low / medium / high）
  → 选择目标 Agent
  → ModelSelector（档位 / 成本 / 健康）
  → Provider 调用
  → model_routing_decisions 审计
```

| 项 | 当前实现 |
| --- | --- |
| 总开关 | `dynamic_model_routing_enabled=False`（默认关闭） |
| 路由范围 | 选 Agent + 难度，不改变工具权限或执行路径 |
| Provider 档位 | 例如 `deepseek-v4-flash`、`qwen3.8-flash`、`qwen3.8-omni-flash`、`qwen3.8-max` |
| 健康监控 | 300 秒窗口、600 秒半衰期、60 秒探测 |
| 级联 | 最多 2 次 |
| 升级 | 最多 1 次 |
| 审计 | `model_routing_decisions`，不记录用户原文 |
| 管理端 | `/admin/ai-providers/routing-decisions`、`/summary` |

边界：模型选择在编排图之外；默认关闭；故障注入与“轻量重超时分支”的完整验证仍缺；审计写库不是异步队列。

## Token usage 数据流

```text
Provider SSE
  → normalize_token_usage()
  → ChatChunk.done.metadata.usage
  → merge_token_usage()（多轮工具循环累计）
  → assistant message.metadata_json.usage
  → chat_sessions.total_tokens
  → CookieService.spend_ai_tokens()
```

归一化字段：

| 字段 | 含义 |
| --- | --- |
| `prompt_tokens` | 输入 token |
| `completion_tokens` | 输出 token |
| `total_tokens` | 总 token |
| `cached_tokens` | 输入缓存命中 token（是输入的子集） |
| `cached_output_tokens` | 输出缓存命中 token（是输出的子集） |

**缓存 token 是子集，不重复相加**；计费公式按输入/输出/缓存的分项价格处理，具体单价以配置为准。

## 三种“金额”概念

| 概念 | 来源 | 用途 |
| --- | --- | --- |
| Provider usage | 模型服务实际返回 | 唯一计费事实 |
| 会话 token 累计 | `chat_sessions.total_tokens` | 展示与统计，不等于费用 |
| 饼干扣费 | 平台内部货币 | 按消息扣减 |
| 前端元估算 | 前端按价格表估算 | **不是账单**，仅参考 |

## 饼干扣费规则

```text
raw_cookie_cost = total_tokens / 1000 * ai_token_cookie_rate
最终扣费 = ROUND_HALF_UP(raw_cookie_cost, 0.01)   # 逐消息舍入
source_type = ai_chat
source_id   = message_id                          # 幂等键
```

- 每个 assistant 消息独立扣费；重试或重复写入同一 `message_id` 不重复扣。
- 扣费后余额不低于 0（封顶）；折扣/价格调整只影响后续消息。
- 平台饼干与供应商元账单是两套账：前者是产品内配额，后者是外部成本。

## 对账流程（8 步）

1. 确认消息对应哪次 Provider 调用（`message_id`、`tool_call_id`、会话）。
2. 检查消息 `metadata_json.usage` 是否存在、字段是否完整。
3. 对比 Provider 控制台/账单的 usage 与会话累计。
4. 检查多轮工具循环是否合并到同一消息。
5. 验证缓存 token 没被重复相加。
6. 重算饼干：`total_tokens/1000*rate`，按消息 ROUND_HALF_UP。
7. 检查 `source_id` 幂等和余额封顶是否导致差异。
8. 区分平台饼干流水与供应商元账单，分别解释差异。

## 修改约束

1. 任何 usage 字段变化 → 更新归一化、合并、消息落库、会话累计和统计 API。
2. 任何价格/折扣变化 → 只影响新消息，不回写历史流水。
3. 改计费公式 → 同步更新前端估算说明；前端估算不得被当作账单。
4. 路由决策记录不得包含用户消息正文或隐私数据。
5. 测试至少覆盖：无 usage 降级、缓存子集、多轮合并、幂等扣费、余额封顶。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| Provider usage | `src/cygnusx/infrastructure/ai_provider/` |
| 归一化/合并 | token usage 工具函数（Provider 适配层） |
| 计费 | `CookieService.spend_ai_tokens()` |
| 路由 | `application/services/` 模型路由服务、`model_routing_decisions` |
| 管理端 | `/admin/ai-providers/*` |

## 关联文档

- 权威基线：[`CygnusX_model_routing_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_model_routing_architecture.md)、[`CygnusX_token_billing_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_token_billing_architecture.md)
- [Agent 运行时](agent-runtime) · [数据库基础设施](database) · [安全模型](security-model)
