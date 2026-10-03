# Skill-First 沙箱执行架构提案

> **状态：提案 v2（2026-10-03 补充 Skill 路由决策），非 as-built 现状描述。** 本文档描述"将平台全部 Skill 暴露给全部 Agent、以 Skill 引导沙箱代码生成"的目标架构与实施路径。落地完成前，不得作为现状依据引用。
> 日期：2026-10-01（v1: 2026-09-30）｜ 关联现状文档：`agent_execution_framework.md`、`cygnusx_sandbox_architecture_2026-10-01.md`

---

## 1. 背景：三个已核实的问题

### 1.1 Skill 库与 Agent 是"两个平行宇宙"

平台存在**完全独立**的两套 Skill 体系（AGENTS.md §4 第 7 条亦确认）：

| 体系 | 位置 | 数量 | 消费方 | 加载方式 |
|---|---|---|---|---|
| bio-* 编码助手 Skill | `.agents/skills/bio-*` | **561** | Kimi CLI 编码助手 | 磁盘目录扫描 |
| 平台业务 Skill | `data/ai/skills/` | **12** | 平台 Agent | DB 三表索引 + 磁盘真相源（`infrastructure/skills/skill_store.py`） |

后果：平台 Agent 的 `chat_sandbox_execute`（`chat_service.py:3455-3462` 对所有非 Studio 会话无条件挂载）生成脚本时**检索不到 561 个专家流程**，只能依赖模型先验知识自由发挥；"物理计算收敛于 Skill"的叙事在执行面断裂；`skill_invocations` 审计表（`infrastructure/database/models/skill.py:91`）对沙箱执行不可见，审计链断裂。

### 1.2 生成环节风险（本期接受，不优化）

"参考 Skill 生成脚本"仍是一次 LLM 自由生成，模型可能偏离 Skill 描述。项目 roadmap 已承认 Skill 层无机器可校验的输入参数 schema（`docs/todo/平台技术演进路线图_v3.0_更新计划.md:117`）。**本期决策：接受该风险**，契约硬化留待 P2（另行提案）。

### 1.3 Skill 环境假设与沙箱现实冲突

- ✅ **micromamba 属实**：runtime image 声明 `micromamba: "2.0.5"`（`data/ai/runtime_images.yaml:30`）。
- ❌ **uv 不属实**：全部 runtime-images 与 `deploy/runtime-images/` 中**不存在 uv**，需新增（按镜像变更 6 处同步规范：清单 → config_files → build.sh/Makefile/.env.example/config.py → 子镜像重建 → `make validate-image-mapping`）。
- ❌ **网络硬冲突**：`analysis-*` 镜像 `network_policy: none`，边界注释明确"默认无外网，不能直接访问 GEO/NCBI/EBI"（`runtime_images.yaml:23,161`）。micromamba 运行时安装必须访问包源，**默认策略下不可行**——这不是改提示词能绕过的。

---

## 2. 目标与非目标

**目标：**

1. 平台全部 Skill（**全量** 561 个 bio-* + 12 个业务 Skill，决策 D2）对全部 Agent **可检索**，主 Agent 会话上下文不被 Skill 库占用。
2. 沙箱代码生成**以选中的 Skill 为条件**（Skill-First），替代当前的先验知识自由生成。
3. 依赖缺失时有**确定性安装策略**，而非模型随意安装。
4. 沙箱执行**强制绑定 `skill_id` 落审计**（决策 D1）。

**非目标（本期不做）：**

- 不对生成脚本做机器校验（契约硬化、参数 schema、静态嗅探）——接受 §1.2 风险。
- 不改动 L0 声明式 Flow 提交链路（`rna_seq_submit` 等）——标准分析仍走 L0。
- 不重构 Studio Loop / Worker ReAct 闭环，仅改造 chat（Legacy/LangGraph）路径。

---

## 3. 已评审决策（2026-10-01）

| # | 开放问题 | 决策 |
|---|---|---|
| D1 | `skill_id → skill_invocations` 审计绑定本期是否采纳 | **采纳，且为强制绑定**（P0 落地，见 §4.4） |
| D2 | 561 个 Skill 全量入库还是先 top 100 试点 | **全量可检索**；不要求把不同目录的磁盘真相源迁移或复制到同一目录，平台索引可分批建立但不能限制为 top 100 |
| D3 | `.agents/skills` 双消费的 frontmatter 真相源 | **各 Skill 目录的 `SKILL.md` 是正文真相源，平台索引负责补充可检索元数据**（见 §4.2 治理约定） |
| D4 | 无 Skill 命中时的默认行为 | **自由生成 + 显式告知用户**（不强制审批，见 §4.4） |
| D5 | `skill_route` 是否另起一套 Agent 架构 | **复用 Router Agent 的子代理架构、`ParallelSubAgentService`、只读工具边界和结构化输出约束；仅替换 Skill 路由提示词与 Skill 检索/读取工具** |

---

## 4. 目标架构

### 4.1 分层总览

```
┌─────────────────────────────────────────────────────────────┐
│ 用户请求                                                      │
└──────────────┬──────────────────────────────────────────────┘
               ▼
   L0 声明式 Flow 提交（rna_seq_submit / atac_seq_submit）      ← 标准分析，不变
               │ （不命中）
               ▼
┌─ L1 Skill-First 沙箱执行（本提案改造面）───────────────────────┐
│  ① skill_route（复用 Router 子代理，独立上下文）              │
│     tag/关键词逐步预筛 → 少量候选 → 读取完整 SKILL.md        │
│     → 适配审查 → 返回 skill_id、理由、置信度和缺失条件        │
│  ② 主 Agent 接收审查结果 → 按会话版本懒加载 Skill 正文（L2） │
│     + 按需资源（L3）                                          │
│  ③ 按 Skill 流程生成脚本 → chat_sandbox_execute 执行          │
│  ④ skill_id 强制落 skill_invocations（D1 审计绑定）           │
└─────────────────────────────────────────────────────────────┘
               │ （无 Skill 命中，置信度低于阈值）
               ▼
   自由沙箱执行（D4）：允许，但必须在回复中显式告知用户
   "无专家 Skill 覆盖本问题，以下结果由模型自由生成，建议人工复核"，
   且 skill_id 落库为 null（审计可区分"有依据"与"无依据"执行）
```

### 4.2 Skill 接入平面（Skill Ingestion）

将不同物理目录中的 Skill 通过统一 Skill Store 暴露给平台 Agent，**不迁移、不复制磁盘真相源**：

- **多目录适配器**：为 `.agents/skills/`、`data/ai/skill_marketplace/` 及后续受控 Skill 根目录建立统一只读索引适配器。适配器将物理路径映射为稳定的 `skill_id`，并提供 `list_skill_metadata`、`read_skill_body`、`read_skill_resource` 三类接口；`skill_route` 不感知目录位置。
- **元数据索引**：扫描各 Skill 根目录，解析 `SKILL.md` frontmatter，建立 `name`、`description`、`task_tags`、`entrypoints`、`env_requirements`、来源目录和正文版本指纹等 L1 索引。索引可落 DB 或其他受控索引，但不得把完整正文预加载进主 Agent 上下文。
- **正文真相源（D3）**：每个 Skill 文件夹内的 `SKILL.md` 仍是正文真相源；平台侧只生成或维护检索元数据，不覆盖编码助手或业务 Skill 的正文文件。缺少 `task_tags` 时由索引管线根据 description 生成临时标签，后续可人工修订；新增目录必须先登记根目录和来源策略，才能进入平台索引。

### 4.3 Skill 路由平面（复用 Router 的 `skill_route` 子代理）

**核心约束：子代理上下文隔离，主 Agent 零负担。**

- **架构复用**：沿用 `agent-router` 的独立上下文、`ParallelSubAgentService`、只读工具集、超时/重试/失败隔离和结构化 JSON 输出。`skill_route` 不执行沙箱、不写工作区、不提交 Flow。
- **专用职责提示词**：不复制 Router 的 Agent 分派提示词；新提示词只约束 Skill 候选筛选、正文适配审查、缺失条件识别和结果交付。输出字段至少包括 `matched`、`skill_id`、`confidence`、`reason`、`fit_checks`、`missing_requirements` 和 `recommended_action`。
- **逐步检索与全文复核**：
  1. **L1 确定性预筛**：按任务标签、分析步骤、文件类型、关键词和来源元数据逐步收窄候选；每轮只传递元数据，不读取正文。P0 使用 SQL/内存索引，候选控制在 ≤20 个。
  2. **L2 候选读取**：对候选逐个调用统一 Skill Store 的 `read_skill_body`，读取完整 `SKILL.md`；正文可来自不同物理目录，但对路由子代理呈现统一接口。
  3. **适配审查**：子代理将用户任务与全文中的适用场景、输入要求、限制、依赖和交付物逐项比对，返回最合适的 Skill；没有真正覆盖时返回 `matched=false`，不得仅因关键词相似而绑定。
  4. **结果交付**：把 `skill_id`、版本/来源指纹、匹配理由、置信度、缺失条件和建议动作交给主 Agent。主 Agent 生成前再按会话 pin 调用 `use_skill`，保证审查和执行使用同一版本。
- **资源按需读取**：只有正文明确需要 references/assets 时才调用 `read_skill_resource`（L3），不得在候选筛选阶段批量加载资源。
- **向量检索定位**：P1 可加入 description embedding 作为 L1 预筛优化；不能替代 L2 全文读取和适配审查。
- **质量守护**：建立 Skill 路由评测集（≥50 条真实问题 → 期望 Skill），仿照 `scripts/evaluate_router_20.py` 模式；评测不达标不得全量开启。

### 4.4 执行平面（chat 闭环改造）

- `chat_sandbox_execute` schema 增加 `skill_id` 字段（可空）。**每次执行强制落 `skill_invocations`**（D1）：有 Skill 时记录 skill_id；无 Skill 命中时记录 `skill_id=null` + 路由置信度，使审计面可区分"专家流程支撑的执行"与"自由生成执行"（session_id/user_id 列已具备，`models/skill.py:99-113`）。
- 提示词改造（`data/ai/prompts/shared/sandbox_protocol.md`，经管理端 API 发布生效），新增"Skill-First 协议"：
  - ① 遇计算需求先 `skill_route`；
  - ② 有候选则声明遵循的 Skill 再生成；
  - ③ 无候选（置信度低）时**允许直接自由生成，但必须显式告知用户**"无专家 Skill 覆盖，结果建议人工复核"（D4），**禁止静默降级**（不告知即违规）；
  - ④ 每次执行如实上报 `skill_id`（含 null），禁止虚报绑定。
- 提示词**不设强制审批门**（D4）：自由生成是合法路径，靠告知义务 + 审计区分度兜底。

### 4.5 依赖安装策略（解决 §1.3 网络冲突，三选一）

| 方案 | 描述 | 确定性 | 实施成本 | 建议 |
|---|---|---|---|---|
| A. 内网镜像白名单 | conda/pypi 内网镜像加入 `network_policy: whitelist` 放行列表，仅包源域名 | 中（pin 版本可复现） | 低 | **P0 采用** |
| B. Skill 依赖预烘焙 | `env_requirements` 声明 → 镜像构建期 conda layer 烘焙，新增镜像变体 | 高 | 高（镜像矩阵膨胀） | P2 演进方向 |
| C. 审批式临时网络 | 复用"前端审批 network_request"模式，安装窗口临时授权 | 中 | 中 | 作为 A 的例外补充 |

**提示词配套**：沙盒协议新增依赖处理节——"缺依赖 → 声明式列出缺失包 → 按 A 策略 mamba/uv 安装（版本必须 pin）→ 安装失败/需系统级依赖时报出建议换镜像，**禁止静默降级与无 pin 安装**；每次安装写入运行清单供交付审计"。

---

## 5. 分阶段实施

**P0 — 通路 + 审计（目标：Skill 可检索、可路由、可执行、可审计）**

1. 多目录 Skill Store 适配器和全量元数据索引；frontmatter 校验与标签补全（`skillmd.py`/`scripts/`），不迁移 Skill 正文。
2. 复用 Router 子代理执行内核，注册 `skill_route` 专用提示词与结构化输出；实现 L1 逐步预筛、L2 候选全文读取和适配审查。
3. `chat_sandbox_execute` 增加 `skill_id` 字段 + **强制落 `skill_invocations`**（D1，含 null 路径）。
4. `sandbox_protocol.md` Skill-First 协议 + 依赖处理节 + 自由生成告知义务（D4）（管理端发布）。
5. 方案 A 内网镜像白名单；uv 加入基础镜像（6 处同步 + `make validate-image-mapping`）。
6. 验证：`make lint && make type-check`；新增单测（frontmatter 校验、预筛、scout 输出 schema、审计落库含 null 路径）；Skill 路由评测集 v1 达标。

**P1 — 检索质量**

1. description embedding 向量预筛（pgvector）。
2. 路由评测集扩至 ≥100 条，纳入回归。

**P2 — 契约硬化（另行提案评审）**

1. 审计数据驱动收紧：对 `skill_id=null` 占比高的会话/Agent 评估是否强制审批或转 L0 Flow。
2. 方案 B 预烘焙镜像变体；Skill 参数 schema 机器契约；生成脚本对 Skill 指定工具调用的静态嗅探。

---

## 6. 风险与遗留关注项

| 风险 | 等级 | 缓解 |
|---|---|---|
| Skill 路由选错 → 生成方向性错误 | 高 | 评测集门槛；top 3–5 而非 top-1；置信度低转显式告知（D4） |
| 多目录 Skill 元数据不一致导致 L1 预筛质量差 | 中 | 统一适配器、标签补全、来源指纹和评测集；P1 embedding 仅作预筛优化 |
| 内网镜像源可用性/带宽 | 中 | 方案 A 落地前需运维确认镜像源；超时降级为方案 C |
| 运行时安装破坏可复现性 | 中 | pin 版本 + 安装记录入运行清单（§4.5） |
| 子代理增加时延（每次计算需求 +1 轮 LLM） | 低 | L1 预筛确定性缓存（同会话同问题直接复用候选） |
| 与 Studio Loop 能力差异扩大 | 低 | Studio 路径同步挂载 `skill_route`（同一工具注册表） |
| 自由生成 + 告知义务的合规性依赖模型自觉 | 中 | D1 审计兜底：null 占比可监控；P2 据此收紧（§5 P2-1） |

**遗留关注（原开放问题已全部决策，见 §3）：** 多目录 Skill 的来源登记、`skill_id` 稳定映射、正文版本指纹和会话 pin 必须由统一 Skill Store 保证；平台生成的标签不能覆盖目录内 `SKILL.md` 正文，也不能让同名目录互相覆盖。

---

## 7. 变更影响清单

| 类别 | 变更点 |
|---|---|
| 配置/数据 | `data/ai/runtime_images.yaml`（uv、白名单域名）；`data/ai/prompts/shared/sandbox_protocol.md`；Skill 根目录注册表；`skill_route` 专用提示词 |
| 代码 | `infrastructure/skills/skillmd.py`（frontmatter 校验）；`infrastructure/skills/skill_store.py`（多目录适配、元数据索引、统一正文读取）；`application/services/chat_service.py`（skill_route 挂载 + skill_id 传参）；复用 `ParallelSubAgentService` 并新增 Skill 路由工具；`models/skill.py`（来源目录/版本指纹/标签索引字段）；审计写库（skill_invocations） |
| 镜像 | 基础镜像 + uv；`make validate-image-mapping` + `scripts/test_studio_agent_runtime.py` |
| 脚本 | `scripts/` 新增多目录 Skill 索引/同步管线和 Skill 路由评测脚本（仿 `evaluate_router_20.py`） |
| 测试守护 | frontmatter 校验单测；预筛单测；scout 输出 schema 单测；审计落库单测（含 skill_id=null 路径）；路由评测集；现有沙盒安全基线测试不回退 |
