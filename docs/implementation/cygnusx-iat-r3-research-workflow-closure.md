# IAT-R3 Research Workflow Closure

本轮状态：SOURCE / ISOLATION 增量完成，真实运行与浏览器验收 **BLOCKED**。未签发 R3_READ_PREPARE_PASS_RUNTIME 或 R3_PRODUCT_PASS_E2E。未启动服务、访问生产、执行外部元数据请求、下载或 Agent 写任务；门禁未改动，未提交或推送。

## 基线与文件所有权

依据资料包 `02_IATR3_Implementation.md`、对应 Prompt、活动架构 `CygnusX_agent_tool_gateway.md` / `CygnusX_treasure_mouse_architecture.md` 和 2026-10-18 audit 逐项核对。实测基线主仓 HEAD 为 `e78fd1efa1df3ebfcb098be973e81e193b1db224`；早先审计 SHA 不代表本次源码。完整主仓状态、递归子模块 SHA/dirty、diff SHA、核心源码与锁文件 SHA 见 `evidence/iat-r3-runtime/baseline.json`。共享树仍在演进，验收必须重新冻结镜像和源码指纹。

本轮只修改 `frontend/src/components/research/adapters/useResearchWorkflow.ts` 及原 `researchWorkflow.test.ts`，独立报告与证据；未修改 Node 子仓、共享 Task/Download/DatasetImport/Admission。

## 实际缺口与修复

原 adapter 在目录刷新失败后只清空 permissions/proposals/tasks/assets/datasets，旧 sources、候选 files、samples、relations、reports、workflows 与 accession/hash 仍能留在显示树；成功刷新返回更少 scope 时也保留历史投影。现改为清空全部科研投影及关联版本映射，并保留可见错误。成功但缩减工具目录也先失效历史数据，再投影当前权限。每次动作仍走原 catalog/Gateway、generation 与 session/project 校验；没有新增业务接口或执行路径。

回归断言覆盖权限拒绝后所有科研字段清空、成功返回空目录后旧报告与来源清空、迟到跨项目响应拒绝、合法 prepare 不自动批准/提交以及 transport executionAllowed 永为 false。

## 本轮隔离验证

命令、工作目录、退出码及原始日志见 `evidence/iat-r3-runtime/commands.json`。

- `npx vitest run src/components/research`：9 文件、51 项通过。
- `npx vue-tsc --noEmit`：最终结果见 commands.json；首次检查发现 optional allowedTools，已修正并重跑。
- `node --test functions/seqout-chat/tests/platform-tools.test.ts`：退出码 0，Node runner 报告一个测试文件通过；不将其冒充真实 HTTP 或完整 Node chat 轮次。测试以替换 fetch 验证固定 callback、redirect:error、凭据不进 schema、危险工具剔除与失败不重试。

未启动监听 API/Node、PG/Redis 或 Chromium，未构建运行镜像。已有源码接线：Node index.ts 经 platformToolAdapter 注入工具和正式模型 loop；BFF producer/cancel 仍由进程内注册表协调，跨进程取消与重启接管未实现。源码接线不计运行通过。

## RA01–RA14 验收矩阵

逐项状态 CSV 见 `evidence/iat-r3-runtime/acceptance.csv`，均为 **BLOCKED**：RA01 Legacy、RA02 LangGraph、RA03 Node 原聊天、RA04 Node 隔离、RA05 metadata、RA06 assets/FileRegistry、RA07 合法持久 prepare、RA08 React 实际 mount、RA09 cards/digest、RA10 撤权、RA11 SSE 断流重连、RA12 待人审且零下载、RA13 faults/i18n/widths、RA14 restart。共同缺少本轮明确授权的独立非生产环境。RA10/RA11/RA12 有本轮前端隔离支撑，不能升级为 PASS_RUNTIME/PASS_E2E。RA14 另有进程内 producer 的实现缺口。

旧 120 Test IDs 维持原审计统计，不与本轮 51 个 Vitest 断言相加。原弱断言纠偏仍成立：AG14 的 Python URLError 不等于 Node 网络故障；AG15 空列表类型断言不等于 200 版本上界；BR04 的 401 不等于合法 Prepare，BR06 重复首页不等于跨项目迟到帧，BR08 首页刷新不等于 cursor 恢复；本轮没有伪造这些运行通过。

## 运行准入与回滚

资料包要求明确的非生产 role/db、Redis namespace、API/Node 端口、测试账号/项目、存储与清理权限，并禁止继承旧授权；本轮未得到这些资源授权。后续须先冻结本次源码和镜像，再用正式 ProviderManager、agent_templates、Gateway audit/nonce、真实 FileRegistry SHA、合法 proposal 与零新增下载 Task、Chromium mount/HAR/截图关联同一请求身份。不得仅使用现有单元日志签发准入。

源码回滚仅逆向本轮 adapter/test hunks，保留其他共享 dirty 和历史事实，不 reset/clean。没有运行服务或创建测试数据库，因此无容器或数据清理动作；证据保留。下载、人类执行、Agent write 与 worker_paths_verified 门禁保持原 false/未认证。
