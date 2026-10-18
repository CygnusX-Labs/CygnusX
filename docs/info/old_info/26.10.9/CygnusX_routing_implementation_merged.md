# CygnusX 动态模型路由实施文档集（V1 → V2）

> 版本：v1.0
> 日期：2026-10-09
> 范围：V1（规则调度 + 故障转移）到 V2（难度分类 + 步进调度 + 级联）的全部实施工作。
> V3（多供应商链路最优选）不在本路线实施，仅在路线图 §6 保留接口预留说明。
> 设计依据：`CygnusX_dynamic_model_routing_design.md`

## 目录

1. 实施路线图（V1 → V2）
2. 配置迁移实施文档（M0 + M1）
3. Router 分类器改造实施文档（M2）
4. ModelHealthMonitor 实施文档（M3）
5. ModelSelector 与决策日志实施文档（M4）
6. 测试计划与验收文档（M5）

---

## 实施路线图（V1 → V2）

> 版本：v1.0
> 日期：2026-10-09
> 范围：本文档集覆盖 V1（规则调度 + 故障转移）到 V2（难度分类 + 步进调度 + 级联）的全部实施工作。
> V3（多供应商链路最优选）不在本路线内实施，仅在 §6 保留演进接口说明。
> 设计依据：`CygnusX_dynamic_model_routing_design.md`（下称"设计文档"）。

---

### 1. 阶段划分

```
M0 配置清理        ── 移除失效 Provider，为一切后续工作打底
M1 配置扩展        ── tier / is_default / 价格 / 延迟预算，Agent 改 model_tier
M2 Router 分类器   ── 固定 deepseek-v4-flash + complexity 输出 + 失败降级
M3 健康度监控      ── ModelHealthMonitor（被动聚合 + 主动探测）
M4 选型与级联      ── ModelSelector + 级联 + 决策日志
M5 验收            ── 对照实验 + 验收标准核验
```

里程碑依赖关系：

```text
M0 ──→ M1 ──┬──→ M2 ──→ M4 ──→ M5
            └──→ M3 ──→ M4
```

M2 与 M3 可并行；M4 依赖两者；M5 依赖 M4。

### 2. 里程碑定义

#### M0 配置清理（1 人日）

- 移除 `qdoubao-seed-evolving` 及其在所有 Agent YAML 中的引用。
- 同步后确认 DB 中该 Provider 停用、受影响 Agent 绑定经 `_reconcile_model_bindings()` 修复到默认 Provider。
- **交付物**：干净的 `data/ai/*.yaml`；绑定一致性测试全绿。
- **验收**：`tests/unit/test_agent_router.py`、`test_agent_router_dispatch.py` 全绿（含修复 `test_site_yaml_enabled_agents_have_config_files` 的固定启用列表，补入 `explorer`）。

#### M1 配置扩展（2 人日）

- Provider YAML 增加 `tier` / `is_default` / `cost_per_1m_in|out` / `latency_budget_ms`。
- `AIProviderYamlLoader`：校验 `is_default` 唯一；合并旧的"加载器自选兜底"逻辑为显式 `is_default`。
- Agent YAML 增加 `model_tier: light | heavy | auto`；旧 `model` 字段保留兼容一个版本。
- **交付物**：配置 schema 变更 + 加载器改动 + 单测。
- **验收**：启动同步无告警；单测覆盖唯一性校验与新旧字段兼容装配。

#### M2 Router 分类器改造（3 人日）

- 分类调用与显式 `model_id` 覆盖解耦，固定使用 deepseek-v4-flash。
- 路由决策 JSON 增加 `complexity`；`normalize_decision()` 校验，缺失默认 `medium`。
- 分类失败显式降级：默认模型 + 通用 Agent 上下文直接处理，留痕 `degrade_reason`。
- **交付物**：`chat_service.py` / `unified_intent_router.py` / `request_preparation.py` 改动 + 单测。
- **验收**：分类准确率评测（`scripts/evaluate_router_20.py` 思路扩展）不回退；显式选模型场景分类调用日志确认模型固定。

#### M3 健康度监控（3 人日）

- `ModelHealthMonitor`：被动聚合 OTel / `ai_call_metrics` + 每 60 秒主动探测无流量 Provider。
- 健康快照缓存（5 分钟滚动窗口 + 指数衰减，半衰期 10 分钟）。
- 分类模型（deepseek-v4-flash）单独熔断，供 M2 降级路径消费。
- **交付物**：新模块 + 缓存 + 告警接入 `AiMetricsService` + 单测。
- **验收**：人为熔断某 Provider，快照、选型剔除、告警三者行为正确。

#### M4 选型与级联（4 人日）

- `ModelSelector.select()`：按难度 + 档位 + 健康度 + 价格选主模型与级联候选。
- 执行循环（LangGraph）内每次模型调用前过 `ModelSelector`；级联 / 升级 / 降级按设计文档 4.2.3。
- 决策日志表 `model_routing_decisions` 落库与查询。
- **交付物**：ModelSelector 模块 + 执行循环接入 + 迁移脚本 + 集成测试。
- **验收**：集成测试覆盖四种级联触发；抽样请求可完整还原选型链。

#### M5 验收（3 人日 + 评测周期）

- 固定任务集（≥50 条真实历史请求）"静态绑定 vs 动态调度"对照实验。
- 按设计文档第 8 节 6 条验收标准逐条核验，产出验收报告。

### 3. 人日估算与排期建议

| 里程碑 | 估算 | 说明 |
| --- | --- | --- |
| M0 | 1 人日 | 含测试修复 |
| M1 | 2 人日 | 含兼容期字段双写 |
| M2 | 3 人日 | 含分类提示词调优一轮 |
| M3 | 3 人日 | 可与 M2 并行 |
| M4 | 4 人日 | 含执行循环接入回归 |
| M5 | 3 人日 + 评测周期 | 评测可先用 20 条冒烟再扩到 50 条 |
| **合计（关键路径）** | **约 13 人日** | M2∥M3 并行可省 3 人日 |

建议节奏：M0+M1 一周内完成并单独发布（行为对存量无影响），M2 单独发布（修复分类模型被覆盖的缺陷本身就有价值），M3+M4 合并发布（单独发布 M3 无用户可见价值），M5 随 M4 发布后启动。

### 4. 回滚策略

| 里程碑 | 回滚方式 |
| --- | --- |
| M0 / M1 | YAML 回退 + 重启同步；`model_tier` 兼容期保证旧字段仍可用 |
| M2 | 功能开关：复杂难度字段解析失败时回退"无 complexity"旧路径（默认 medium + 静态绑定行为） |
| M3 | 健康缓存缺失时选型退化为"忽略健康维度"（现状行为），组件可整体关闭 |
| M4 | 全局逃生舱：Settings 增加 `dynamic_model_routing_enabled`，关闭后走静态绑定路径；决策日志表保留 |

**要求：M2、M4 的每一处行为变更都必须有独立开关，禁止不可分割的大爆炸发布。**

### 5. 并行工作安排

- M2 与 M3 由两人并行；两者交接面是 `HealthSnapshot` 数据结构与"分类模型熔断 → M2 降级路径"这一个消费点，提前在接口上对齐（见 `03_model_health_monitor.md` §5 与 `02_router_classifier.md` §4）。
- M1 完成后 M2/M3 才能开工；M0 是所有工作的前置。

### 6. V3 接口预留（不实施）

V3（多供应商链路最优选）不在本路线实施，但 M1–M4 的设计须为其留好接口，避免返工：

1. `HealthSnapshot` 预留 `vendor` 字段（M3 实现时加字段、不参与逻辑，V3 启用厂商级熔断）。
2. Provider YAML schema 预留 `vendor` / `weight` 字段（M1 的加载器忽略未知字段或透传存储，V3 启用）。
3. `ModelSelector` 的决策第 4 步封装为独立函数 `rank_candidates()`，V3 将"价格升序"替换为"四维评分"时只换这一个函数。
4. 决策日志 `candidates_considered` 从 M4 起就记录候选排序依据，V3 增加维度时历史数据可回填。

详见设计文档第 11 节。

---

## 01 配置迁移实施文档（M0 + M1）

> 对应里程碑：M0 配置清理、M1 配置扩展
> 设计依据：设计文档 §4.4（Provider 配置扩展）、§7 迁移步骤 1–3

---

### 1. M0：移除 `qdoubao-seed-evolving`

#### 1.1 现状问题

现状调查（§6.2）确认：Provider YAML 中不存在 `qdoubao-seed-evolving`，但多个 Agent YAML 仍声明绑定它。按 `AIProviderYamlLoader.load_and_sync()` 的规则，未在 YAML 声明的 Provider 会在同步时被停用，相关 Agent 的失效绑定由 `_reconcile_model_bindings()` 修复到默认 / 兜底 Provider——**结果是原本推理档的专家集体回落到同一模型，静态分档静默失效**。必须先清理，让配置与加载器行为自洽。

#### 1.2 操作步骤

1. **全仓搜索引用**：
   ```bash
   rg -l 'qdoubao-seed-evolving' data/ src/ tests/ scripts/
   ```
2. **删除 / 改写所有引用**：
   - Agent YAML（`general`、`agentteams_manager`、`rnaseq`、`atacseq`、`scrna` 系列、`code`、`viz`、`qc`、`cloud_ops`、`mcp_builder`、`orchestrator` 等）中的 `model: qdoubao-seed-evolving` 统一改写为 `model_tier: heavy`（M1 的新字段；在 M1 未上线前临时写为 `model: qwen3.8-max`，M1 时再统一改）。
   - `data/ai/router.yaml` 注释、历史分档记录（`data/ai/update/README.md`）中同步更正，避免文档漂移（现状调查 §6.2 已点名该问题）。
3. **数据库核验**（需要部署环境只读账号）：
   ```sql
   SELECT name, active, is_default FROM ai_providers WHERE name = 'qdoubao-seed-evolving';
   SELECT agent_id, model_id FROM agent_templates WHERE model_id IN (
     SELECT id FROM ai_provider_configs WHERE provider_id = (SELECT id FROM ai_providers WHERE name='qdoubao-seed-evolving')
   );
   ```
   预期：同步后该 Provider `active=false`；上述 Agent 的绑定已被修复到默认 Provider。若发现绑定未被修复，手工执行 `AgentService._reconcile_model_bindings()` 对应逻辑或修数据。
4. **修复测试固定列表**：`test_site_yaml_enabled_agents_have_config_files` 失败是因为固定启用列表未含新增的 `explorer`——把 `explorer` 补入该列表（这是测试维护，不是掩盖问题）。

#### 1.3 验收

- `rg 'qdoubao-seed-evolving' data/ src/ tests/` 仅剩历史 changelog 类文件中的提及（如有）。
- `uv run pytest tests/unit/test_agent_router.py tests/unit/test_agent_router_dispatch.py -q -m 'not quarantine'` 全绿。
- DB 核验通过（上述 SQL）。

---

### 2. M1：Provider YAML 扩展

#### 2.1 目标 schema

```yaml
providers:
  - name: deepseek-v4-flash
    model: deepseek-v4-flash
    endpoint: https://api.deepseek.com
    active: true
    is_default: true            # 新增：全文件唯一，平台兜底模型
    tier: light                 # 新增：light | heavy
    cost_per_1m_in: 0.2         # 新增：可选，元/百万 token
    cost_per_1m_out: 0.8        # 新增：可选
    latency_budget_ms: 3000     # 新增：可选
    vendor: deepseek            # 新增（V3 预留，M1 只透传存储不参与逻辑）
    weight: 100                 # 新增（V3 预留，同上）

  - name: qwen3.8-flash
    model: qwen3.8-flash
    endpoint: <dashscope 兼容端点>
    active: true
    is_default: false
    tier: light
    cost_per_1m_out: 1.0
    latency_budget_ms: 3000

  - name: qwen3.8-omni-flash
    model: qwen3.8-omni-flash
    endpoint: <dashscope 兼容端点>
    active: true
    is_default: false
    tier: light                  # 多模态场景再细分，先归 light
    latency_budget_ms: 3000

  - name: qwen3.8-max
    model: qwen3.8-max
    endpoint: <dashscope 兼容端点>
    active: true
    is_default: false
    tier: heavy
    cost_per_1m_out: 12.0
    latency_budget_ms: 15000
```

字段语义与约束：

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| `is_default` | 是 | 全文件恰好一个 `true`。多个 → 取第一个 + WARN；零个 → 加载失败（不再静默自选兜底） |
| `tier` | 是 | 枚举 `light` / `heavy`；缺失 → WARN 并按 `light` 处理，同时记入待清理清单 |
| `cost_per_1m_in/out` | 否 | 缺失 → 价格维度对该 Provider 失效（选型退化为忽略价格），前端估算维持现状 |
| `latency_budget_ms` | 否 | 缺失 → 健康判定只用错误率 / 限流率 |
| `vendor` / `weight` | 否 | V3 预留，M1 起透传存库，不参与任何逻辑 |

#### 2.2 数据库字段

`ai_providers` 表新增列（迁移脚本）：

```sql
ALTER TABLE ai_providers
  ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN tier VARCHAR(16) NOT NULL DEFAULT 'light',
  ADD COLUMN cost_per_1m_in DOUBLE PRECISION,
  ADD COLUMN cost_per_1m_out DOUBLE PRECISION,
  ADD COLUMN latency_budget_ms INTEGER,
  ADD COLUMN vendor VARCHAR(64),
  ADD COLUMN weight INTEGER NOT NULL DEFAULT 100;

-- is_default 唯一（部分唯一索引，只约束 true）
CREATE UNIQUE INDEX uq_ai_providers_default ON ai_providers (is_default) WHERE is_default = TRUE;
```

价格字段与既有 `ai_provider_configs` 单价的关系：以 `ai_provider_configs` 为运行时权威来源，`ai_providers` 新列为 YAML 声明的同步镜像；两者冲突时以 DB 管理端配置为准并 WARN（沿用现状"YAML 是声明、DB 是运行时"的分工，不打破）。

#### 2.3 加载器改动（`ai_provider_yaml_loader.py`）

1. **唯一性校验**：`load_and_sync()` 解析阶段检查 `is_default` 计数；违反则 WARN + 取第一个（向后容错），零个则 raise（快速失败，避免无兜底上线）。
2. **兜底逻辑合并**：删除"无声明默认时自选一个 active Provider 兜底"的旧逻辑（现状调查 §5.3），统一以 `is_default` 为准。保留旧行为一个版本：若 DB 中已有历史默认项而 YAML 未声明，同步时保留并 WARN，给迁移窗口。
3. **新字段同步**：`tier` / `cost_*` / `latency_budget_ms` / `vendor` / `weight` 按名称 upsert 到 `ai_providers`。
4. **兼容期**：YAML 未写新字段的旧行按 §2.1 的默认值处理，不阻断同步。

#### 2.4 Agent YAML：`model_tier`

```yaml
## 旧
model: qwen3.8-max
## 新（二选一，兼容期两者并存，model_tier 优先）
model_tier: heavy
```

- `model_tier: light | heavy | auto`。`auto` 表示由 Router 输出的 complexity 决定档位（V2 生效；V1 阶段 `auto` 等价 `light` 优先）。
- 兼容期规则（`AgentService` 装配解析）：
  ```
  model_tier 存在 → 走档位解析（V2 起交给 ModelSelector）
  仅 model 存在  → 维持现状静态绑定解析
  两者都不存在  → WARN + 回落到默认 Provider
  ```
- 迁移完成后（一个版本）下线旧 `model` 字段，届时 `_reconcile_model_bindings()` 的失效绑定修复目标从"默认 Provider"改为"同 tier 内的健康候选"。

#### 2.5 `ensure_builtin_agents()` 调整

现状（调查 §5.3）：已有 Agent 的有效绑定保留，仅失效绑定修复。新增：内置 Agent 创建时优先写 `model_tier`；修复失效绑定时若 Agent 有 `model_tier` 声明，不再绑到单一 Provider，而是记录"待 ModelSelector 运行时解析"的标记（DB 中 `model_id` 可空 + `model_tier` 列于 `agent_templates`）。

`agent_templates` 新增列：

```sql
ALTER TABLE agent_templates ADD COLUMN model_tier VARCHAR(16);
```

#### 2.6 实施检查清单

- [ ] `rg 'qdoubao-seed-evolving'` 清理完成，测试全绿
- [ ] Provider YAML 四个 Provider 全部补齐新字段，`is_default` 唯一
- [ ] 迁移脚本 + 回滚脚本（`DROP COLUMN` / `DROP INDEX`）就位
- [ ] 加载器唯一性校验单测：多个 default / 零个 default / 旧 DB 有默认 YAML 未声明 三种场景
- [ ] 价格字段与 `ai_provider_configs` 冲突时 WARN 的行为验证
- [ ] Agent YAML 新旧字段双写装配测试
- [ ] 管理端 `ai_provider_yaml_writer.py` 回写 YAML 时包含新字段（否则管理端一改配置就丢字段）

#### 2.7 验收标准

1. 启动同步无 ERROR；`is_default` 违例时 WARN 文案可读且出现在日志。
2. 单测覆盖率：加载器新增分支 ≥90%。
3. 存量 Agent（未改 YAML）行为不变：装配出的模型与迁移前一致。

---

## 02 Router 分类器改造实施文档（M2）

> 对应里程碑：M2 Router 分类器
> 设计依据：设计文档 §4.1（Router 分类器改造）
> 涉及代码：`src/cygnusx/application/services/chat_service.py`、`unified_intent_router.py`、`chat/request_preparation.py`、`agentteams_capability_registry.py`

---

### 1. 改造目标

1. 分类调用**固定使用 deepseek-v4-flash**（按 `is_default` + `tier: light` 解析），用户显式 `model_id` 不再作用于分类调用。
2. 路由决策 JSON 新增 `complexity: low | medium | high`，同一调用顺带输出，不新增模型调用。
3. 分类失败走**显式降级**：平台默认模型 + 通用 Agent 上下文直接处理，留痕 `degrade_reason`。

---

### 2. 现状行为与问题定位

现状调查的关键事实：

- `prepare_agent_request()`（`request_preparation.py`）在请求准备阶段先对 Router 上下文的 `model_config` 应用显式 `model_id` 覆盖；分类调用使用这个上下文（`config=router_ctx.model_config`）。
- 后果（调查 §4.3）：用户显式选择模型时，Router 分类也跑在用户选的模型上——分类成本不可控，且用户选了重档模型时分类延迟显著上升。
- 分类调用参数：temperature=0、max_tokens=ROUTER_MAX_TOKENS(10000)、tools=None、deep_thinking=False。
- 失败处理（调查 §4.2）：最外层异常捕获后返回无路由结果，按原上下文继续——路径模糊，且"继续"用的是目标 Agent 静态绑定模型。

### 3. 改动点一：分类调用与显式覆盖解耦

#### 3.1 改法

在 `ChatService._route_to_agent()` 内构建**独立的分类用 model_config**，不复用 `router_ctx.model_config`：

```python
## chat_service.py 新增常量与解析
ROUTER_CLASSIFIER_PROVIDER_NAME = "deepseek-v4-flash"  # 见 §3.3 关于可配置化的说明

def _build_classifier_config(self) -> ModelConfig:
    """分类调用专用配置：固定轻量档，不受请求显式覆盖影响。"""
    provider = self._provider_repo.get_active_by_name(ROUTER_CLASSIFIER_PROVIDER_NAME)
    if provider is None:
        # 配置缺失：WARN + 回退 is_default Provider；两者都缺失才抛错
        provider = self._provider_repo.get_default()
    if provider is None:
        raise ModelRoutingMisconfigured("no classifier provider and no default provider")
    return ModelConfig.from_provider(provider)
```

`_route_to_agent()` 内分类调用改为 `config=self._build_classifier_config()`。

`prepare_agent_request()` 中"对 Router 上下文应用显式覆盖"的逻辑保留（路由后的目标装配仍需要），但确认它不再影响分类调用——即覆盖只作用于"Router Agent 作为目标被装配"的场景，不作用于"Router Agent 作为分类器运行"的场景。两处要用不同的上下文对象，避免再被耦合。

#### 3.2 行为矩阵

| 场景 | 分类调用模型 | 目标回答模型 |
| --- | --- | --- |
| 用户不选模型 | deepseek-v4-flash | Agent 档位解析结果 |
| 用户显式选轻量模型 | deepseek-v4-flash（不变） | 用户所选 |
| 用户显式选重档模型 | deepseek-v4-flash（**变化点**） | 用户所选 |
| deepseek-v4-flash 停用 | 回退 is_default（缺省报错） | 不受影响 |

#### 3.3 可配置化边界

`ROUTER_CLASSIFIER_PROVIDER_NAME` 不进用户可见配置（防止被改成重档模型又走回老路）；允许放在 Settings 的运维级配置里，修改需重启并打 WARN 日志。V3 接入第二家轻量厂商后，这里扩展为"分类器候选链"（主 + 备用轻量候选）。

### 4. 改动点二：`complexity` 字段

#### 4.1 决策 JSON 扩展

分类提示词输出 schema 增加：

```json
{
  "agent_id": "code",
  "complexity": "medium",
  "complexity_reason": "涉及多文件重构，需要多步工具调用",
  "...": "既有字段不变"
}
```

枚举定义与判定指引（写进提示词，信号全部来自现有路由输入）：

| 档位 | 判定指引 |
| --- | --- |
| `low` | 单轮问答、摘要、格式转换；无附件或单个小附件；短会话 |
| `medium` | 需要 1–3 步工具调用；多附件中等分析；较长会话历史 |
| `high` | 多步推理 / 复杂规划；长上下文；触发会诊、fan-out、overdrive；深层代码或数据分析 |

**提示词工程要求**：在 `agentteams_capability_registry` 派生的能力目录摘要旁，附各候选 Agent 的工具数量作为难度先验（工具多的 Agent 整体偏 medium+）。不要新增任何采集逻辑。

#### 4.2 归一化与容错（`unified_intent_router.py`）

`normalize_decision()` 增加：

```python
COMPLEXITY_LEVELS = ("low", "medium", "high")
DEFAULT_COMPLEXITY = "medium"   # 保守居中：宁可多花钱不可降质量

def _normalize_complexity(raw) -> str:
    if isinstance(raw, str) and raw.lower() in COMPLEXITY_LEVELS:
        return raw.lower()
    return DEFAULT_COMPLEXITY   # 缺失 / 非法 → medium，不算分类失败
```

**关键语义**：`complexity` 缺失或非法 ≠ 分类失败。只有 JSON 整体解析失败、目标 Agent 非法、或模型调用异常，才进入 §5 的失败降级。这是为了避免"字段小问题导致整请求降级"的过度反应。

#### 4.3 评测门禁

上线前用标注了难度真值的任务集（从 `scripts/evaluate_router_20.py` 的任务集扩充，每条补人工难度标注）评测分类准确率：

- complexity 判准率（exact match）目标 ≥70%；
- low 判成 high 的比率 ≤10%（多花钱可接受）；
- **high 判成 low 的比率 ≤5%（质量风险，硬门槛）**。

不达标则调提示词，不允许带着高误判率上线——这是成本控制与质量保护的共同前提。

### 5. 改动点三：分类失败显式降级

#### 5.1 降级路径

`_route_to_agent()` 现状是"最外层异常捕获 → 返回无路由结果 → 调用链按原上下文继续"。改为显式语义：

```python
class RoutingOutcome:
    decision: RouterDecision | None
    degraded: bool
    degrade_reason: str | None   # router_classification_failed / classifier_unhealthy / ...
```

触发条件（满足其一即降级）：

1. 分类调用抛异常（网络 / 5xx / 超时）。
2. JSON 解析失败且容错提取也失败。
3. `normalize_decision()` 校验后目标 Agent 仍非法（无有效候选可回退）。
4. （M3 就绪后）HealthMonitor 判定分类模型 unhealthy——直接降级，不发必失败的调用。

#### 5.2 降级后的执行

```text
跳过意图路由与难度判断
→ 目标 Agent = 通用 Agent（现有通用候选回退机制）
→ 模型 = is_default Provider（当前即 deepseek-v4-flash）
→ 按通用上下文直接处理请求
→ 决策日志 degrade_reason 留痕
→ 同时上报一次健康度事件（分类器故障，M3 消费）
```

注意语义（设计文档 §4.1.4）：降级目标是**默认模型**而不是"分类模型"——当前两者恰好相同，将来默认模型换绑时行为仍然正确。

#### 5.3 与 M3 的交接面

M3 的 `ModelHealthMonitor` 提供：

```python
class ModelHealthMonitor:
    def is_healthy(self, provider_name: str) -> bool: ...
    def report_event(self, provider_name: str, event: HealthEvent) -> None: ...
```

M2 降级路径在 `ROUTER_CLASSIFIER_PROVIDER_NAME` 上调用 `is_healthy()`；M3 未上线时注入 `NullHealthMonitor`（恒 healthy、report 为空操作），保证 M2 可独立发布。

### 6. 测试用例（新增）

| 用例 | 前置条件 | 预期 |
| --- | --- | --- |
| 显式重档模型不影响分类 | 请求带 model_id=qwen3.8-max | 分类调用的 config 为 deepseek-v4-flash |
| complexity 正常输出 | 模拟 Router 返回 `"complexity": "low"` | 决策对象 complexity=low |
| complexity 缺失 | Router 返回无该字段 | complexity=medium，不降级 |
| complexity 非法值 | Router 返回 `"complexity": "extreme"` | complexity=medium，不降级 |
| 分类调用异常 | Provider 抛超时 | degraded=true，reason=router_classification_failed，走默认模型 |
| JSON 完全不可解析 | 返回非 JSON 垃圾 | 同上 |
| 目标 Agent 非法且无回退 | 决策指向不存在 Agent | 同上 |
| 分类模型停用 | YAML 中 active=false | 回退 is_default；两者都缺 → 抛 ModelRoutingMisconfigured |
| 降级仍受权限约束 | 降级请求含需审批工具 | 审批闸照常触发（红线回归） |

### 7. 实施检查清单

- [ ] `_build_classifier_config()` 落地，分类调用不再消费 `router_ctx.model_config`
- [ ] 提示词 schema 扩展 + 能力目录附工具数量先验
- [ ] `normalize_decision()` complexity 校验与 medium 默认
- [ ] `RoutingOutcome` 语义落地，调用链两处消费点（正常路由 / 降级）都有测试
- [ ] 难度判准率评测通过 §4.3 门禁
- [ ] 决策日志留痕字段（降级路径先行，M4 补全表结构）
- [ ] NullHealthMonitor 占位，M3 可无缝替换

### 8. 验收标准

1. 审计日志：任意请求的 Router 分类调用模型 100% 为 deepseek-v4-flash。
2. 分类准确率评测：专家路由准确率不回退（对比 M2 前的基线），complexity 判准达 §4.3 门槛。
3. 故障注入：杀掉分类模型端点模拟 5xx，请求走降级路径成功返回，留痕正确。
4. 回归：`test_agent_router.py` / `test_agent_router_dispatch.py` / `test_request_preparation.py` 全绿。

---

## 03 ModelHealthMonitor 实施文档（M3）

> 对应里程碑：M3 健康度监控
> 设计依据：设计文档 §4.3（健康度检测组件）
> 新建模块建议位置：`src/cygnusx/application/services/model_health_monitor.py`（与 `ai_metrics_service.py` 同级，便于复用其聚合逻辑）

---

### 1. 组件职责

持续回答一个问题："每个 Provider 现在能不能用、用起来什么水平？" 结论以 `HealthSnapshot` 形式缓存在内存中，供两类消费方读取：

- **Router 分类器**（M2，见 `02_router_classifier.md` §5.3）：分类模型 unhealthy 时直接走降级，不发必失败的调用。
- **ModelSelector**（M4，见 `04_model_selector.md`）：候选过滤与级联决策。

数据来源两条，互补：

| 来源 | 成本 | 覆盖盲区 | 定位 |
| --- | --- | --- | --- |
| 被动：聚合真实调用的 OTel / `ai_call_metrics` | 零 | 无流量 Provider 没有数据 | 主来源 |
| 主动：后台定时探测 | 极低（max_tokens=1） | 无 | 兜底冷启动盲区 |

### 2. 数据结构

```python
@dataclass(frozen=True)
class HealthSnapshot:
    provider_name: str
    healthy: bool                          # 硬结论
    error_rate: float                      # 近窗口，指数衰减加权，0~1
    p95_ms: float | None
    throttle_rate: float                   # 429 占比
    consecutive_failures: int              # ≥3 直接判 unhealthy
    last_event_at: datetime | None
    last_probe_at: datetime | None
    source: Literal["passive", "active", "unknown"]
    # --- V3 预留（M3 只存不算）---
    vendor: str | None = None

class HealthEventKind(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    THROTTLED = "throttled"
    CLIENT_ERROR = "client_error"
```

健康判定规则（快照构建时计算）：

```text
healthy = consecutive_failures < 3
      and error_rate <= 0.2            # 5xx+超时占比 20% 以内
      and throttle_rate <= 0.3
      and (p95_ms is None or p95_ms <= latency_budget_ms)   # 预算来自 Provider 配置
```

阈值全部进 Settings（运维可调），上述为默认值。

### 3. 被动聚合

#### 3.1 事件入口

不重造数据管道。Provider 调用完成时已有 OTel span 与结构化日志（现状调查 §8.1），M3 增加一个轻量事件钩子：

```python
class ModelHealthMonitor:
    def record(self, provider_name: str, kind: HealthEventKind,
               duration_ms: float | None = None) -> None:
        """由 ProviderManager 调用完成后同步调用；只做 O(1) 内存更新，不得阻塞请求。"""
```

接入点：`ProviderManager.chat_stream()` 的成功 / 异常出口（`infrastructure/ai_provider/openai_compatible.py` 的重试逻辑已有错误分类，把终局结果映射为 `HealthEventKind` 即可，不重分类）。

#### 3.2 窗口与衰减

- 滚动窗口 5 分钟；指标用指数衰减加权（半衰期 10 分钟），事件权重 `w = 0.5 ** (age_minutes / 10)`。
- 每个 Provider 维护计数器环形缓冲：`[(timestamp, kind, duration)]`，定时裁剪窗口外事件。
- `p95_ms` 对窗口内 success 事件的有权分位数做近似（简单分段即可，不引入复杂 sketch；调用量级下精确计算足够）。

### 4. 主动探测

#### 4.1 触发条件

后台协程每 60 秒扫一遍 Provider 表：近 10 分钟**无被动事件**的 Provider 进入探测列表。有流量的 Provider 靠被动数据即可，不浪费请求。

#### 4.2 探测请求

最小化调用：`max_tokens=1` 的 Chat Completions 请求；若供应商提供 models/health 端点则优先用端点探测（探测成本为零）。结果映射为 `HealthEventKind` 走同一条 `record()` 通道，`source="active"`。

#### 4.3 自我保护

- 探测并发上限 4；单 Provider 探测超时 5 秒，失败不重试（下一次周期再来）。
- 探测流量在决策日志中标记 `is_probe=true`，**不计入用户成本口径**，也不参与计费归一化。
- 全量 Provider 连续探测失败 ≥3 轮 → 降级探测频率到 5 分钟一次并告警（可能是平台自身网络问题，别打爆供应商）。

### 5. 对外接口（M2 / M4 的交接面）

```python
class ModelHealthMonitor:
    def snapshot(self, provider_name: str) -> HealthSnapshot | None: ...
    def is_healthy(self, provider_name: str) -> bool:
        s = self.snapshot(provider_name)
        return True if s is None else s.healthy   # 未知 → 视为健康（宽松准入）
    def record(self, provider_name: str, kind: HealthEventKind,
               duration_ms: float | None = None) -> None: ...

class NullHealthMonitor(ModelHealthMonitor):
    """M2 先行发布时的占位实现：恒健康、record 为空操作。"""
```

设计要点：

- **未知视为健康**：新注册 / 冷启动 Provider 没有数据时不应被排除在候选外（宽松准入），靠连续失败计数快速纠错。
- 进程内内存缓存，多 worker 各自独立计算（各自消费本 worker 的调用流）。V1 接受不一致；如需全局熔断换 Redis，接口不变。
- 快照读路径无锁（copy-on-write 替换），`record` 路径用每 Provider 一把小锁，避免请求线程竞争。

### 6. 分类器专用熔断

Router 分类模型（`ROUTER_CLASSIFIER_PROVIDER_NAME`）单独一条消费逻辑（M2 需要）：

```python
def classifier_healthy(self, provider_name: str) -> bool:
    s = self.snapshot(provider_name)
    if s is None:
        return True
    # 分类模型要求更严：任何连续失败即熔断（分类调用失败本就要降级）
    return s.consecutive_failures < 1 and s.error_rate <= 0.5
```

M2 降级路径在调用分类器前查 `classifier_healthy()`；False 则跳过分类直接降级，同时 `record()` 一条分类器跳过事件供观测。

### 7. 告警接入

复用 `AiMetricsService` 现有告警通道，触发条件：

| 告警 | 条件 |
| --- | --- |
| Provider 持续不健康 | healthy=false 持续 ≥5 分钟 |
| 分类器熔断 | `classifier_healthy=false` 任一时刻 |
| 探测全面失败 | §4.3 的全量失败降级 |
| 延迟恶化 | p95_ms 连续 3 个窗口超 `latency_budget_ms` |

### 8. 测试用例

| 用例 | 方法 | 预期 |
| --- | --- | --- |
| 被动成功聚合 | 注入 success 事件流 | p95 收敛、healthy=true |
| 连续失败熔断 | 注入 3 次 timeout | consecutive_failures=3 → healthy=false |
| 衰减生效 | 旧窗口事件权重低于新事件 | error_rate 随时间下降 |
| 未知 Provider | 查询无数据 Provider | snapshot=None；is_healthy=True |
| 主动探测补盲 | 构造 10 分钟无流量 Provider | 进入探测列表并发出探测请求 |
| 探测失败退避 | 连续 3 轮全量探测失败 | 频率降至 5 分钟 + 告警 |
| 分类器专用熔断 | 分类模型 1 次失败 | classifier_healthy=false |
| 无锁读 | 并发 record + snapshot | 无数据竞争（压力测试） |

### 9. 实施检查清单

- [ ] `record()` 接入 `ProviderManager` 调用出口，错误分类复用现有重试逻辑
- [ ] 指数衰减窗口与 p95 近似实现 + 阈值 Settings 化
- [ ] 主动探测协程（60 秒周期、并发上限、超时、退避）
- [ ] `snapshot / is_healthy / classifier_healthy` 三接口 + NullHealthMonitor
- [ ] 探测流量标记 `is_probe` 且不计费
- [ ] 告警四条件接入 `AiMetricsService`
- [ ] HealthSnapshot 预留 `vendor` 字段（V3）

### 10. 验收标准

1. 人为熔断某 Provider（拦截其流量返回 5xx）：5 分钟内快照 unhealthy → ModelSelector 候选剔除生效 → 告警送达。
2. 冷启动 Provider（无流量）：一个探测周期后获得快照。
3. `record()` 在请求热路径上的额外耗时 <1 ms（压测验证）。
4. M2 联调：分类模型熔断时，请求直接走降级路径，日志无分类调用记录。

---

## 04 ModelSelector 与决策日志实施文档（M4）

> 对应里程碑：M4 选型与级联
> 设计依据：设计文档 §4.2（选型决策层）、§4.5（权限红线）、§6（数据与留痕）
> 新建模块建议位置：`src/cygnusx/application/services/model_selector.py`

---

### 1. 组件职责与接入位置

`ModelSelector` 位于"上下文装配之后、Provider 调用之前"。**执行循环（LangGraph）内每次模型调用前**都经过它——工具循环第 1 步可能很简单、第 5 步很难，按单次调用调度才能吃到降本收益。

接入点：`ChatService._stream_agent_chat_inner()` 的执行循环里，组装好当步的 model_config 之后、`ProviderManager.chat_stream()` 之前。

```python
class ModelSelector:
    def select(self, inp: SelectionInput) -> SelectionDecision: ...
    def on_step_result(self, request_id: str, step_index: int,
                       result: StepResult) -> SelectionDecision | None:
        """级联消费点：上一步调用失败/截断/超时后，返回下一步重试决策；None 表示无级联可用。"""
```

### 2. 决策输入 / 输出

```python
@dataclass
class SelectionInput:
    request_id: str
    step_index: int                       # 执行循环内第几步
    agent_id: str
    complexity: str                       # low | medium | high（M2 Router 输出或降级默认 medium）
    model_tier: str                       # Agent 声明：light | heavy | auto
    explicit_model_id: str | None         # 用户显式选择
    estimated_output_tokens: int          # 预估输出长度（complexity 档位历史均值，成本估算用）

@dataclass
class SelectionDecision:
    primary: str                          # Provider 名
    cascade: list[str]                    # 级联候选，按优先级排序，最多 2 个
    decision_reason: str                  # 规则化原因码
    candidates_considered: list[CandidateEval]  # 供决策日志落库
```

### 3. 决策流程（`select()`）

```text
1. 显式模型
   explicit_model_id 存在 → 健康检查通过则直接选用，cascade=空，
   decision_reason=explicit_choice；不健康 → cascade 加同档候选保可用性

2. 档位确定
   model_tier=light → 候选池=轻量档
   model_tier=heavy → 候选池=推理档
   model_tier=auto  → complexity=low → 轻量档
                       complexity=medium → 轻量档优先（与升级通道配合）
                       complexity=high → 推理档

3. 健康过滤（硬约束）
   HealthMonitor.is_healthy=false → 剔除
   候选池为空 → 全档放开重选一次；仍为空 → 回退 is_default Provider，
   decision_reason=no_healthy_candidate

4. 档内排序
   有价格数据 → 按预估成本升序（成本 = in 价×输入 + out 价×预估输出）
   无价格数据 → 按历史 P50 升序
   平局 → weight（V3 预留字段，默认全 100 → 稳定排序即可）

5. 输出
   primary = 排序第一；cascade = 排序第 2、3（同档内）
```

**V3 预留**：第 4 步封装为独立函数 `rank_candidates(candidates, signals) -> list[CandidateEval]`，V3 把"价格升序"替换为"质量/成本/延迟/健康四维评分"时只换这一个函数（见 `00_roadmap_V1_V2.md` §6）。

### 4. 级联与升级（`on_step_result()`）

触发条件与动作（设计文档 §4.2.3）：

| 触发 | 判定 | 动作 | 约束 |
| --- | --- | --- | --- |
| 限流 / 5xx / 超时 | Provider 终局错误 | 切 cascade 下一候选 | 每步最多级联 2 次 |
| 输出截断 | finish_reason=length 且 complexity ≥ medium | 该步升级推理档重跑 | 单请求最多升级 1 次 |
| 推理档超时 | 超时且当前在 heavy | 降级轻量档重跑 | 响应标注"可能质量受损"；可全局关闭 |

级联状态挂在请求级上下文（`request_id + step_index`），执行循环每次调用前查状态机：

```text
step 正常完成 ───────────────────────────→ 下一步重新 select()
     │失败
     ▼
级联次数 < 2 且有候选 ──→ 用 cascade 下一候选重跑当前步
     │否则
     ▼
升级次数 < 1 且满足升级条件 ──→ 升档重跑当前步
     │否则
     ▼
按原异常上报（同现状失败语义）
```

注意：级联 / 升级重跑的是**当前这一步**，不是整轮；消息历史、工具状态不回滚，重跑只是换一个 model_config 再发一次同样的调用。上下文组装完全复用，因此工具 / MCP / Skill / 审批边界天然不变（红线见 §7）。

### 5. 决策日志

#### 5.1 表结构（新表 `model_routing_decisions`）

```sql
CREATE TABLE model_routing_decisions (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    step_index INTEGER NOT NULL,
    agent_id VARCHAR(64) NOT NULL,
    complexity VARCHAR(16),
    explicit_model_id VARCHAR(64),
    model_tier VARCHAR(16),
    chosen_provider VARCHAR(64) NOT NULL,
    cascade_providers JSONB,
    candidates_considered JSONB,          -- [{provider, cost_est, p50, healthy, rank_score}...]
    decision_reason VARCHAR(64) NOT NULL, -- tier_match | price_asc | explicit_choice |
                                          -- cascade_throttle | cascade_timeout |
                                          -- upgrade_truncated | degrade_quality |
                                          -- degrade_classification_failed | no_healthy_candidate
    cascade_events JSONB,                 -- [{event, from_provider, to_provider, trigger}]
    degraded BOOLEAN NOT NULL DEFAULT FALSE,
    degrade_reason VARCHAR(64),
    usage_id BIGINT,                      -- 关联本次调用的 usage 记录
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_mrd_request ON model_routing_decisions(request_id, step_index);
CREATE INDEX idx_mrd_created ON model_routing_decisions(created_at);
```

#### 5.2 写入策略

- 每次 `select()` / `on_step_result()` 产生最终决策时**异步批量**落库（复用 `core.ai_metrics` 的缓冲模式：缓冲满或写库失败可丢弃，但 WARN——决策日志丢了不阻断请求，只损失可观测性）。
- M2 的降级路径先行写入 `degraded/degrade_reason`（表结构在 M2 就建好，M4 补全写入方）。

#### 5.3 查询入口

管理端 / 运维查询最小集：

- 按 request_id 还原完整选型链（含级联事件）。
- 按天聚合：`decision_reason` 分布、各 Provider 被选占比、级联率、升级率、降级率。
- 与 `ai_call_metrics` 按 `usage_id` 关联，算"动态调度节省 vs 静态基线"的归因口径。

### 6. 功能开关与逃生舱

Settings 增加：

```python
dynamic_model_routing_enabled: bool = False   # 默认关，灰度开启
dynamic_routing_max_cascades: int = 2
dynamic_routing_max_upgrades: int = 1
dynamic_routing_quality_degrade_enabled: bool = True   # 超时降级轻量档的总开关
```

开关关闭时：`ModelSelector.select()` 直接返回静态绑定结果（现状行为），级联、升级、决策日志写入全部旁路。这是 M4 的发布与回滚保险。

### 7. 权限红线（评审硬性检查项）

1. ModelSelector 只接收 §2 的 `SelectionInput`，**不接触、不许修改**工具列表、MCP 配置、Skill、Studio capability、确认闸、数据权限。
2. 模型切换只替换 `model_config`；执行上下文原样传递，下游（工具循环、审批、数据访问）无感知。
3. 级联 / 升级重跑**不得绕过确认闸**：走重档重跑仍要重新过工具审批，不许因"同一请求的第二次尝试"豁免。
4. 决策日志不落用户消息内容，只落选型与成本信息。
5. 发布前跑权限回归：构造"需审批工具 + 触发级联"的请求，验证审批闸触发次数与静态路径一致。

### 8. 测试用例

| 用例 | 预期 |
| --- | --- |
| auto + low → 轻量档最低成本 | primary=轻量档价格最低者 |
| auto + high → 推理档 | primary=推理档 |
| 显式选择 + 健康 | primary=显式模型，reason=explicit_choice |
| 显式选择 + 不健康 | cascade 含同档候选 |
| 档内全不健康 | 放开全档重选；仍空回退 is_default，reason=no_healthy_candidate |
| 级联触发 | 注入限流 → 切 cascade 下一候选，cascade_events 留痕 |
| 升级触发 | 注入 finish_reason=length + medium → 升档重跑，单请求第二次拒绝 |
| 超时降级 | heavy 超时 → 降 light 重跑 + 质量受损标注；总开关关闭时禁用 |
| 开关关闭 | 全链路行为 = 静态绑定（回归基线） |
| 权限回归 | 级联重跑仍触发审批闸 |
| 决策日志 | 抽样请求可还原完整选型链；缓冲写库失败不阻断请求 |

### 9. 实施检查清单

- [ ] `SelectionInput / SelectionDecision / CandidateEval` 定义
- [ ] `select()` 五步决策 + `rank_candidates()` 独立封装（V3 替换点）
- [ ] `on_step_result()` 级联状态机（请求级上下文挂载）
- [ ] 执行循环接入：每步调用前 select()、失败后 on_step_result()
- [ ] `model_routing_decisions` 迁移脚本 + 异步缓冲写入
- [ ] 决策日志聚合查询（按天 / 按 reason / 按 Provider）
- [ ] Settings 开关与逃生舱
- [ ] 权限红线回归测试

### 10. 验收标准

1. 四种级联触发条件集成测试全过；每步级联 ≤2 次、升级 ≤1 次的上限生效。
2. 开关关闭时行为与 M3 前基线逐字节一致（回归测试对比）。
3. 抽样 100 个真实请求，100% 可还原选型链；级联 / 升级 / 降级事件全部留痕。
4. 权限回归通过：级联与升级不穿越任何审批闸。
5. 决策写入对请求 P95 的影响 <5%（缓冲异步化验证）。

---

## 05 测试计划与验收文档（M5）

> 对应里程碑：M5 验收
> 设计依据：设计文档 §8（验收标准）、§6.2（成本口径）
> 前置：M0–M4 全部完成，各里程碑自身的单测 / 集成测试已通过

---

### 1. 测试分层总览

| 层 | 内容 | 工具 | 通过门槛 |
| --- | --- | --- | --- |
| L1 单元 | 各组件单测（随 M0–M4 交付） | pytest | 新增分支覆盖率 ≥85%（加载器 ≥90%） |
| L2 集成 | 组件间交互（路由→选型→级联→日志） | pytest + 模拟 Provider | §3 用例全过 |
| L3 故障演练 | 人为熔断 / 超时 / 截断注入 | 故障注入开关 | §4 全过 |
| L4 对照实验 | 静态绑定 vs 动态调度（固定任务集） | 评测脚本 | §5 验收标准 |
| L5 权限回归 | 审批闸 / 数据权限边界 | 安全回归用例 | 零穿越 |

### 2. L1 单元测试汇总（按里程碑归档）

- M0：`test_site_yaml_enabled_agents_have_config_files` 修复后全绿；`qdoubao-seed-evolving` 清理验证。
- M1：加载器唯一性校验三场景；新旧字段兼容装配；`ai_provider_yaml_writer` 回写新字段。
- M2：`02_router_classifier.md` §6 九条用例；难度判准率评测门禁。
- M3：`03_model_health_monitor.md` §8 八条用例。
- M4：`04_model_selector.md` §8 十一条用例 + 权限回归。

### 3. L2 集成测试用例

| # | 用例 | 链路覆盖 |
| --- | --- | --- |
| I1 | 普通请求：路由 → complexity=low → 轻量档 → 完成 | 全链路正常路径 |
| I2 | 复杂请求：complexity=high → 推理档 → 完成 | 档位切换 |
| I3 | 工具循环 5 步：第 1 步轻量、第 4 步截断升级 | 步进调度 + 升级 |
| I4 | 显式选模型 + 会诊 fan-out | 显式优先级 + 子任务 |
| I5 | 分类失败 → 默认模型降级 → 留痕 | M2 降级路径 |
| I6 | 分类模型熔断（M3）→ 不发起分类调用直接降级 | M2×M3 交接 |
| I7 | 轻量档全不健康 → 全档放开 → 推理档承接 | 健康过滤 + 放开重选 |
| I8 | 主模型限流 → 级联 → 成功 | 级联路径 |
| I9 | 主模型限流 → 级联 2 次仍失败 → 原异常上报 | 级联上限 |
| I10 | 决策日志异步写库失败 → 请求不受影响 + WARN | 留痕健壮性 |

环境要求：模拟 Provider（沿用现有单测的 mock 体系）+ 真实 `ai_call_metrics` 管道 + 临时 PG 实例（迁移脚本验证）。

### 4. L3 故障演练

| # | 演练 | 操作 | 预期 |
| --- | --- | --- | --- |
| F1 | 分类模型 5xx | 拦截 deepseek-v4-flash 返回 5xx | 请求走降级路径成功；无分类调用日志；`degrade_reason` 正确；告警送达 |
| F2 | 轻量档模型全挂 | 拦截全部 light Provider | 请求由推理档承接；reason=no_healthy_candidate 或全档放开记录 |
| F3 | 推理档超时 | 注入 heavy 超时 | 降级轻量档重跑 + 质量受损标注；总开关关闭时不降级 |
| F4 | 输出截断 | 注入 finish_reason=length | 升级重跑 1 次；第二次截断按原异常上报 |
| F5 | 数据库决策日志不可用 | 断 `model_routing_decisions` 连接 | 请求成功率不下降；WARN 日志 |
| F6 | 逃生舱 | 关闭 `dynamic_model_routing_enabled` | 全链路行为 = 静态绑定基线 |

每项演练前后各跑一遍 L2 冒烟子集（I1/I2/I5），确认无状态泄漏。

### 5. L4 对照实验与验收标准

#### 5.1 任务集

- 规模：≥50 条真实历史请求，覆盖 Agent 分布与难度分布（low/medium/high 建议 5:3:2）。
- 标注：人工质量参考答案 + 难度真值（M2 评测集扩充复用，不重复造）。
- 来源：生产日志抽样，脱敏后使用。

#### 5.2 对照组

| 组 | 配置 |
| --- | --- |
| A 静态基线 | 动态路由关闭（逃生舱），静态绑定 = M1 迁移后的档位中位模型 |
| B 动态调度 | 全功能开启（含级联升级） |

每组跑 3 遍取中位数，消除厂商侧抖动。真实供应商调用，成本按供应商实际单价折算人民币（不是平台 cost_cookie 口径——现状调查 §8.2 明确两者不同）。

#### 5.3 成本口径（必须全口径）

总成本 = Σ（每次模型调用的 in/out token × 单价），**包含**：

- Router 分类调用（每次请求 1 次，除非熔断降级）
- 级联重试与升级重跑
- 工具循环全部步进调用
- 会诊 / fan-out 子 Agent 调用

排除：主动探测流量（M3 已标记 `is_probe` 且不计费）。

#### 5.4 验收标准（对应设计文档 §8）

| # | 标准 | 目标 |
| --- | --- | --- |
| V1 | 质量：回答质量评分（LLM-as-judge + 人工抽检 20%）相对 A 组下降 ≤3% 相对分差；low 难度任务无可感知劣化 | 硬门槛 |
| V2 | 成本：B 组全口径总成本较 A 组下降 ≥20%；分类调用成本占比 ≤5% | 硬门槛 |
| V3 | 延迟：端到端 P50 下降；首 token 延迟恶化 ≤300 ms | 硬门槛 |
| V4 | 可靠性：F1/F2 演练通过；B 组请求成功率与 A 组无显著差异（≥99% 对 ≥99%） | 硬门槛 |
| V5 | 留痕：100% 请求可查决策日志；分类调用 100% 固定 deepseek-v4-flash | 审计核验 |
| V6 | 权限：安全回归零穿越 | 硬门槛 |

#### 5.5 验收流程

1. 评测脚本产出对照报告（质量分 / 成本 / 延迟 / 级联率 / 升级率 / 降级率 / 决策 reason 分布）。
2. 未达标项进入分析：质量降 → 查 high→low 误判与超时降级占比；成本降不够 → 查 complexity 分布与升级率；延迟恶化 → 查分类调用耗时与级联次数。
3. 允许一次调参复测（提示词 / 权重 / 阈值），仍不达标则回退逃生舱并复盘设计，**不允许带着未达标指标上线**。

### 6. L5 权限回归清单

- [ ] 需审批工具请求 + 触发级联：审批触发次数与静态路径一致
- [ ] 需审批工具请求 + 触发升级重跑：重跑前重新审批
- [ ] 数据权限受限 Agent：模型切换后受限数据访问仍被拒绝
- [ ] MCP / Skill 边界：动态调度后可用工具集不变
- [ ] 决策日志抽检：不含用户消息正文

### 7. 交付物清单

| 交付物 | 位置 |
| --- | --- |
| 对照实验报告（含原始数据） | `reports/model_routing_ab_<date>/` |
| 故障演练记录 | 同上 `fault_drill.md` |
| 权限回归记录 | 同上 `security_regression.md` |
| 验收结论（签字项） | 同上 `acceptance.md` |
| 上线检查单（逃生舱默认值、告警接收人、回滚指令） | 同上 `go_live_checklist.md` |

### 8. 上线后观察期（建议 2 周）

- 灰度：开关按用户组放量（1% → 10% → 50% → 100%），每档观察 ≥2 个工作日。
- 观察指标：决策 reason 分布、级联率、升级率、降级率、每请求模型调用次数分布、用户投诉 / 质量反馈。
- 熔断回退：观察期内任一验收指标劣化超过 20%，一键回退逃生舱并冻结放量。

---

