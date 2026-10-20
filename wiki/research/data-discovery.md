# 数据发现与获取

平台有两条相关的数据入口：**寻宝鼠**负责对话式公共数据发现与证据解析，**下载模块**负责把选定数据真正取回并登记为文件。二者共享项目、Dataset 和 Agent 工具边界，但运行门禁独立。

> **当前状态**：发现、预案、审批、Dataset 草案与下载契约均已实现；**公共数据下载和 Agent 写路径仍受源码门禁保护**，真实 Worker/传输运行验收未完成。不要把“能发现”当成“能下载”，也不要把“能下载”当成“已可用”。

## 三条调用链

```text
1) UI typed action
   React Island（唯一展示树）→ Vue 外壳 → BFF /api/v1/research-agent/*
   → useResearchWorkflow → /agent-tools/sessions/{sid}/invoke

2) Node 有限委托
   寻宝鼠 Node/TS Runtime → 平台 BFF 签发委托 JWT
   → 固定 CYGNUSX_TOOL_CALLBACK_URL → AgentToolGateway

3) 平台 AI
   AgentService → cygnusx-tools builtin → MCPClient → ToolBridgeService
   → AgentToolGateway
```

三条链汇入同一个 `AgentToolGateway`；身份、项目、会话、Agent 类型和 scope 由 Gateway 从真实上下文派生，模型不能传入 owner/project/scopes。

## 寻宝鼠边界

| 组件 | 职责 |
| --- | --- |
| React Island `FullPresentation` | 唯一展示树 |
| Vue 外壳 `TreasureResearchWorkbench` | 页面集成 |
| FastAPI BFF `/api/v1/research-agent/*` | 会话、项目、委托、预案、审批 |
| Node Runtime | 保留自己的 LLM loop、GEO/SRA/文献工具 |
| `AgentToolGateway` | 平台能力目录、prepare/approve/execute、持久关联 |

委托约束：

- 独立 JWT key domain、固定 issuer/audience；
- TTL 300 秒，jti + Redis NX 防重放；
- scope 与最新服务端 scope 取交集；
- **委托不含 execute/approve 能力**，不能进入模型 messages；
- Redis 不可用返回 503。

## 发现与预案

```text
用户提出数据结构需求
  → 寻宝鼠检索 GEO/ENA/文献
  → 只读证据适配：URL、获取时间、响应摘要、样本/Run 上限
  → prepare：服务端校验 owner/project/scope/参数
  → 人类 JWT 确认
  → execute：进入下载/Dataset 业务（受门禁）
```

- GEO/ENA 适配器只读，受信 HTTPS 主机、禁重定向、响应/样本/Run 上限、超时与缓存。
- 不伪造 supplementary 链接；不把 PRJNA 直接传给原 SRR 下载入口；GSE/GSM 元数据不自动推导分组真值。
- 下载预案只接受格式合法的 SRR/PRJNA 候选；GSE/GSM 返回 `NEEDS_METADATA_RESOLUTION`；任意 URL、GEO processed matrix、counts-only DEG 不受支持。
- 能力目录会区分“代码存在、配置可用、未认证、执行阻断”，并声明 `WRITE_GATE_BLOCKED`。

## 下载模块（三来源）

| 来源 | 机制 | 备注 |
| --- | --- | --- |
| EBI/NCBI（SRA） | EBIDownload CLI | 需要二进制、YAML 配置和 Worker 依赖 |
| 云对象存储 | ossutil / tosutil / obsutil | OSS/TOS/OBS URI 前缀 |
| 直接/云盘 | aria2c/ftplib 等受控传输 | 云盘 UI 为占位，不等同已接通 |

下载链路复用标准 Task：

```text
POST /api/v1/downloads
  → DownloadService → Task(flow_id 下载类)
  → Celery run_download
  → 传输实现 → 校验 → FileRecord 登记
  → reconcile-only 验证
```

关键事实：

- 代码中存在 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`；传输层未完成运行验收。
- Worker 的硬预算、重定向策略与挂载尚未运行验收，不能开放写入。
- 传输实现、Worker/CLI 分发、FileRegistry 登记和 DL-RG 验收以[下载架构权威文档](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)为准。
- 子模块版本与宿主程序/容器可能不同；不要把子模块代码版本当作已部署版本。

## 与 Dataset 的交接

下载完成不等于可分析：

```text
下载文件 → FileRecord
  → Dataset 导入/资产校验（格式、行列、SHA、样本映射）
  → DatasetVersion 冻结
  → DataHandoff（固定排序 + SHA-256）
  → AnalysisLink → Flow 提交
```

交接面、资产校验和 Handoff 见 [Dataset 与 Handoff](dataset)。当前 `worker_paths_verified=false`，Handoff 不是 READY。

## 验收缺口

- 寻宝鼠 RG-01–RG-12 全部未闭环；
- 无真实视觉/发布验收；
- 真实 Redis、HTTP/STDIO MCP、Node→平台网络、双用户全栈和 Worker 未验收；
- 下载传输与 Dataset 引入写入未验收；
- 浏览器只读预案检查不等同执行。

## 修改门禁

1. 改发现/委托/Gateway → 跑双 Runtime 权限隔离、委托重放、scope 交集测试。
2. 改下载传输 → 以下载架构文档与 DL-RG 为准，不只看下载 Service。
3. 改 Dataset 交接 → 跑 Handoff 稳定性、owner 校验、文件 SHA 复验。
4. 不得绕过确认凭证或源码门禁；不接受模型自证确认。

## 关联文档

- 权威基线：[`CygnusX_treasure_mouse_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_treasure_mouse_architecture.md)、[`CygnusX_download_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)、[`CygnusX_agent_tool_gateway.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md)
- [Dataset 与 Handoff](dataset) · [科研能力与证据边界](evidence-boundaries) · [数据下载](../features/downloads) · [安全模型](../architecture/security-model)
