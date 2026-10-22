# 隔离只读开放与会话挂链试点门禁清单

实施工作树：`/tmp/cygnusx-session-lineage-q2usvvh7/worktree`。现有部署源码、Compose、根 .env、生产数据库不修改。当前代码可在该工作树独立审阅；本次没有复制现网 .env。

| 门/确认 | 本轮目标 | 理由及授权边界 |
| --- | --- | --- |
| RESEARCH_PLAN_ENABLED | 仅隔离 true | 用户 Part A.1 已授权；验证计划只读及 PLAN_ONLY 空状态，不自动创建计划 |
| RESEARCH_DELIVERY_READ_ENABLED | 仅隔离 true | 用户 Part A.1 已授权；读取空/非空血缘及 inventory，不允许采集写入或导出 |
| TOOL_GATEWAY_READ_ENABLED | 仅隔离 true | 用户 Part A.1 允许按需核对；本试点经现有 Gateway 解析真实会话身份和准备元数据，不调用 LLM |
| DATASET_DISCOVERY_READONLY | **等待用户确认，仅隔离 true** | 名称虽只读，现有架构明确包含 JWT 元数据登记/审阅；本试点需要复用它准备 Dataset/资产/Handoff/AnalysisLink。严格按附件 B.5 先交清单后开启 |
| Assay、样本分组审阅 | owner JWT，逐版本审阅 | 初次 Gateway 调用仅保存声明，group_confirmed=false、assay unknown；必须经既有 JWT review API 明确确认后，才能重试冻结/准备 |
| 分析预案 approve | owner JWT，一次性确认存储 | 沿用 DatasetAnalysisService.decide/ToolConfirmationService；模型参数不得携带 owner/project/approved/group_confirmed |
| WRITE_RUNTIME_ACCEPTED | **源码 false，不改** | 本轮未验收真实执行，不授予发布准入 |
| worker_paths_verified | **真实 Handoff false，不回写** | 其值属于冻结摘要，本轮没有 Worker 验证，不伪造证明 |
| AGENT_ANALYSIS_WRITE_ENABLED | **false** | execute 应在写门拒绝，不创建 Task |
| ANALYSIS_SUBMIT_FROM_DATASET | **false** | 不授予 Dataset 提交计算资格 |
| DATASET_IMPORT_WRITE / AGENT_DOWNLOAD_WRITE_ENABLED | **false** | 显式选择已登记文件，无导入下载需求 |
| RESEARCH_DELIVERY_WRITE_ENABLED | **false** | 不采集计算成果、不生成 Observation/报告 |
| PROJECT_EXPORT_ENABLED | **false** | 只读清单和空状态，ZIP 生成/下载不开放 |
| PROJECT_REPORT_WRITE_ENABLED / PROJECT_REPORT_PDF_ENABLED | **false** | 不生成正式报告/PDF |
| COUNTS_DEG_FLOW_ENABLED | **false** | 试点选 FASTQ→现有 RNAFlow 预案，不启用实验 counts Flow |
| TREASURE_NATIVE_UI_ENABLED / TREASURE_AGENT_WRITE_TOOLS_ENABLED / AGENT_TASK_CANCEL_ENABLED | **false** | 不启用寻宝鼠写工具、独立 UI 或取消任务 |

元数据登记及 human review 均在专用 PostgreSQL/Redis 与私有本地文件范围内；不将这类准备操作称为科学计算完成。此次新增能力只接受显式文件/样本 ID 和类型化 RNA 参数；模型无法提供项目身份，调用前从服务器验证的 ChatSession 解析 owner/project。注册与预案复用现有表/服务，不纳管历史 Task。

代码审阅入口：`application/services/session_dataset_preparation_service.py`、Gateway 的 `analysis.prepare_from_session_files` 分支、`RunPlanService.register_dataset_proposal/confirm`、`TaskService.submit(..., run_id=...)`；均在上述独立工作树。Run 与 Dataset 共享 dataset:{proposal} 幂等身份，TaskService 在提交事务中绑定 Run 与 Link，移除 Task 提交后才绑定 Run 的接缝。
