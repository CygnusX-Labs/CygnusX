# 寻宝鼠完整前端展示迁移调查与实现

2026-10-15。依据用户要求将迁移范围从欢迎区扩展到原始前端展示树。此前 Vue Markdown、简化结果卡与临时工具条不能表达原站的完整回复，本次已经移除这些替代渲染。

## 原始来源与逐项映射

来源为子仓 `pipelines/Treasure-Seeking_Mouse` 的活动 `src/`，不是 `qmuse` 档案。入口是 `src/island/FullPresentation.tsx`；父平台通过 `TreasureOriginalDisplay.vue` 挂载独立 React 模块。

| 元素 | 原始组件/资源 | 平台处理 |
|---|---|---|
| 欢迎页、示例、输入、模型菜单、停止按钮 | EmptyState、Composer | 原组件；草稿、提交、取消由 Vue 管理 |
| 用户/助手回复、Markdown、复制、重试、建议 | ChatMessage、Markdown及其子组件 | 原组件；重试将原问题作为新一轮提交 |
| GEO/SRA 等数据卡与文献卡 | DatasetCardGrid、DatasetCard.tsx 内 LiteratureResultCard | 原组件；保留完整来源 metadata |
| 编号悬浮、证据链、详情弹窗 | IdLink、LiteratureCard、LiteratureDetailDialog | 原组件；文献读取走 owner 校验 BFF |
| 运行状态、耗时、核验提示、Polariseq | ToolTrace、GroundingNotice、DownloadBoostCard | 原组件；统一实时/历史投影 |
| 会话搜索、日期分组、改名、移除 | SessionSidebar | 原组件；平台身份；移除为软归档 |
| 折叠侧栏、移动抽屉、顶栏 | FullPresentation 组合原组件 | 保留平台项目切换与权限刷新 |
| 统计、排行榜 | UsageStatsDialog、Leaderboard | 原界面与真实不可用态；原站聚合数据服务尚未连接 |
| 关于、介绍图、致谢 | 原 about 页面提取 AboutPresentation | 保留原内容并标注原项目介绍与平台边界 |
| 桌宠、拖动、气泡、设置、成就反馈 | TreasureMouse、PetSettingsPanel、原 petStore 逻辑 | 原组件；设置改为模块内存，离开不保留 |
| 主题、双语、图标、字体、纹理、动效 | 原 styles.css、i18n、assets、fontsource | ShadowRoot 隔离、本地字体与资源；不修改平台 html |

## 发现及修复

旧工作台只显示 Markdown，未消费实时 cards 与 polariseq，工具 running/done 重复展示，终态 cards 快照未完整进入历史。新适配器统一处理 SSE UTF-8 分块、CRLF、多行 data、缓冲尾帧；缺少终态不当作成功。实时卡和终态卡按来源/编号合并并保留 metadata；工具状态合并而保留重复执行。历史和实时使用同一投影。来源链接限制 HTTP(S)，命令入口 accession 限定项目编号。

新增会话 PATCH 重命名/归档、会话文献 POST，均复用 active/module/owner 检查。归档保留数据库历史；未改数据库 schema。平台仍控制会话、身份、项目、模型请求、SSE 及取消。构建图禁止旧 SPA router、Supabase 与旧身份/聊天客户端进入模块；旧存储服务经 build alias 改为内存服务。原站统计不可用时不伪造计数或榜单。

## 验证与限制

已执行主/子前端类型检查、独立模块与主生产构建、真实展示树的隔离 DOM 测试、Vue 会话隔离测试、协议适配测试、BFF ASGI SQLite owner/历史测试，以及相关 Python Ruff/mypy。日志在 `evidence/treasure-native/full-ui-verification/`（本地证据，不提交）。结果：主/子类型检查与生产构建通过；独立展示树 13 项、前端相关域 32 项、BFF 33 项通过。全前端套件 546 项通过、7 项失败，失败仍来自既有 agent-teams-room-send、deep-thinking-stream、live-stream-render 三个测试文件，不能声称全仓门禁全绿。

Docker info 实际返回 `docker.sock: connect: operation not permitted`。此环境无法启动真实 Chromium 或访问 Docker socket，因此没有完成真实浏览器像素、字体、窄屏拖动及线上截图验收，也没有重启或发布服务。不能据 DOM 测试宣称与截图逐像素一致。未连接原站排行榜、全站统计和昵称写入；没有恢复独立账号入口；平台默认模型菜单沿用平台模型策略。后续真实视觉验收与上述服务接入仍需跟踪。

回退只恢复 `evidence/treasure-native/full-ui-baseline` 中此次迁移前文件并移除本次新增展示文件；禁止重置整个脏工作区。该目录是工作证据，不提交。未创建 commit、未推送。
