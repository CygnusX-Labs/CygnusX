# CygnusX 前端全平台优化实施总报告

## 结论和证据等级

本轮按 W00–W17 连续执行了现有前端可安全验证的优化。源码、静态契约、单元测试、类型检查和生产构建均有记录；真实浏览器、六视口双主题截图、测试账户业务 Smoke/E2E 和动态 chunk 故障复现受环境限制，不能标记为完成。

| 类别 | 完成 | 未完成/阻塞 |
|---|---:|---:|
| W00 基线与 W01–W15 源码优化包 | 1 + 15 | 全部保留部分完成状态 |
| W16 chunk 故障实测 | 静态核查 | 浏览器不可用，未植入未经复现的 reload hook |
| W17 文档与清单 | 已生成 | 截图和执行记录待补 |
| `npm run type-check` | 通过 | — |
| `npm run build` | 通过（基线及收尾） | — |
| Vitest | 504 passed / 7 failed，68 files | 同基线的 3 个失败文件；详见下文 |
| `git diff --check` | 通过 | — |
| 浏览器视觉/业务回归 | 未执行 | Chromium snap/AppArmor 与本地服务连接受限 |

## 批次变更清单

| 批次 | 实际结果 |
|---|---|
| W01 | 项目详情对下线 AgentTeams 路由禁用并说明原因 |
| W02 | 状态令牌补齐 Light/Dark，`--arco-*` 保留兼容别名 |
| W03 | 进度归一化工具、Dashboard/TaskTable 共用、BLAST 列宽修正 |
| W04 | `navigationRegistry.ts` 统一顶部/侧栏入口投影 |
| W05 | `standard-page`、PageHeader 长标题/窄屏换行、去重复 padding |
| W06 | 首页最近任务真实数据卡、Hero 间距和 Dashboard 静态横幅收敛 |
| W07 | Files 空态按个人/团队/搜索失败区分，移除未实现假入口 |
| W08 | Downloads 进度和 SRA Dry Run 接入已有合同，参考库文案纠正 |
| W09 | Reports `taskId` 深链扫描真实列表 API，Monitor 断线文案，常规页间距 |
| W10 | Projects/Detail 加载失败与重试，避免失败误报为空 |
| W11 | AgentSandbox Token 诊断改为可聚焦按钮，窄屏收纳 |
| W12 | PendingApprovalBar 摘要/澄清按钮键盘可达，移动端换行 |
| W13 | FilePreviewModal 增加受鉴权 PDF Blob 预览、打印和请求代次保护 |
| W14 | ToolsHub 本地搜索；Knowledge 错误态/重试 |
| W15 | About 品牌标语和真实能力文案；GitHub 安全 rel；Canvas `aria-hidden` |
| W16 | 静态确认动态 import + AppErrorBoundary；未复现故障，未改 router |
| W17 | 本总报告、设计系统、回归清单、问题 backlog、W16 报告和架构图 |

## 影响文件

源码改动集中在 `frontend/src/components/`、`frontend/src/layouts/`、`frontend/src/styles/`、`frontend/src/views/`，以及新增 `frontend/src/layouts/navigationRegistry.ts`、`frontend/src/utils/progress.ts` 和对应测试。活动架构文档 `ARCHITECTURE_DESIGN/CygnusX_frontend.md` 增加了导航/布局/主题图和 chunk 验收事实。未修改后端、API、数据库、SSE/WS 协议、流程 YAML、依赖锁文件或五个已有脏子模块。

## 路由、深链和状态检查

- 路由仍由 `frontend/src/router/index.ts` 定义，动态 import 和 `meta.fullscreen` 保留。
- 顶部/侧栏目标统一来自 `navigationRegistry.ts`；路由可达性仍须通过真实菜单点击和模块权限验证。
- Project/Task/Report ID 均继续使用已有路由参数；Reports 的 `?taskId=` 使用既有列表 API 分页查找，因为后端 keyword 不搜索 task_id。
- 任务进度统一经过 `normalizeProgress()`，避免 10000% 展示；新增单测覆盖 0/1/0.45/45/100、异常和边界值。

## Token 与兼容变更图

见 [`CygnusX_Design_System_v1.md`](CygnusX_Design_System_v1.md)。关键链路为 `tokens.css → global.css 历史别名 → 业务 CSS`，以及 `tokens.css/theme store → App.vue themeOverrides → Naive UI`。Naive UI 仍使用解析后的颜色字面量，避免把 `var()` 传给 seemly。

## 自动验证和既有失败

在 `frontend/` 执行：

```text
npm run type-check   PASS
npm run build        PASS
npm test             68 files; 504 passed, 7 failed
git diff --check     PASS
```

7 项失败仍集中在原有 3 个文件：`deep-thinking-stream.test.ts` 1 项、`agent-teams-room-send.test.ts` 5 项、`live-stream-render.test.ts` 1 项。W00 基线为 66 files、493 passed、7 failed；失败断言分别涉及已有 `cachedOutput` 字段和 AgentTeams mock 参数/异步行为，本轮相关执行器未修改。新增导航测试 2 项、进度测试 9 项以及 W11/W12 目标测试通过。

## 视觉、可访问性、安全与性能

- Light/Dark 六宽度和 14 页截图：未取得；执行模板见 `CygnusX_UI_Regression_Checklist.md`。
- 键盘按钮、Canvas `aria-hidden`、外链 `noopener noreferrer`、错误重试和 Blob URL 回收已静态确认；完整 Tab/屏幕阅读器/forced colors 待浏览器检查。
- 未添加 UI 库或依赖；未改变鉴权、文件 ID、任务参数、审批确认或用户可见路径协议。
- 性能指标和 chunk 缓存/404 行为未测量；W16 需要可用浏览器和可控静态资源环境。

## 剩余技术债与建议顺序

1. 在可用浏览器环境执行 14 页 × 6 视口 × Light/Dark 及数据状态矩阵，补截图索引。
2. 用测试账户执行 S1–S10，覆盖 SSE、WS、审批、文件/PDF、报告和任务深链。
3. 复现过期 chunk 后再决定 `router.onError` 的重试或错误页策略。
4. 单独修复基线中的 7 项 Vitest 失败，避免把协议字段断言更新混入视觉批次。

变更均未提交、未推送、未部署；回滚按各 Wxx 报告逐批恢复对应文件即可，不应清理用户原有子模块改动。
