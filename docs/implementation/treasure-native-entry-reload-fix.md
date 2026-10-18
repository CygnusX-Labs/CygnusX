# 寻宝鼠重载后仍显示临时页面：定位与修复

## 现场与原因

用户截图 `docs/info/26.10.15/2026-10-15_22.26.26.png` 可读取，画面包含 P0 新增的“刷新权限”“入口尚未启用”提示。这与当前源码中的临时 Vue 工作台一致，不能归因为浏览器仍显示迁移前代码。

已核实的源码问题：

1. 正式 `TreasureMouseView` 只挂载临时 `TreasureResearchWorkbench`；原版 EmptyState/Composer 在 `frontend/poc/`，未接入正式路由。`make docker-reload` 只调用主前端 `npm run build`，此前没有包含原展示模块的构建步骤。成功重载仍会得到临时聊天页。
2. 本地根 `.env` 未设置 `TREASURE_NATIVE_UI_ENABLED`；主 Compose 对该值使用默认 false。重启不会自动开启只读发现。截图呈现了相同的关闭状态，但没有取得现场 capabilities HTTP 响应，运行中容器实际环境仍未核验。

## 本次修复

- `TreasureOriginalDisplay.vue` 在正式工作台挂载旧 React 展示 Island。空态直接使用原鼠形象、标题/副标题、四场景八示例和 Composer；已有消息仍由原平台工作台保存与显示，底部复用原 Composer，不在本轮迁移结果卡片协议。
- 草稿、发送、停止、项目由 Vue 持有；主题/语言跟随平台 DOM 标记。异步模块晚于卸载返回时不挂载 React，卸载会释放 observer/root。
- 简化重复的大标题，关闭服务时移除空白历史侧栏，但保留中文授权/服务状态。关闭 capability 时依然能看见原欢迎界面，输入和检索禁用，不绕过 BFF。
- `frontend/package.json` 的 prebuild/predev 调用 `frontend/scripts/build-treasure-island.mjs`。使用子仓既有锁定依赖独立构建，仅将展示 JS、字体分片和图片放入自动生成的 `frontend/public/treasure-island/`；随后由主 Vite 复制进 dist。诊断 module-inventory 不发布。没有给 Vue package 新增 React 依赖，没有手改锁文件。
- 普通 Docker 前端构建同步准备子仓锁定依赖并使用对应目录结构；npm/pnpm 采用可配置国内源与官方回退。此 Dockerfile 分支未实际构建，当前环境无法连接 Docker daemon。
- 三份 Nginx 配置为稳定 JS 入口指定 no-cache；字体/图片仍以 hash 文件名缓存。旧 `/treasure-mouse/` 独立认证路径没有恢复。
- 仅本地 `.env` 新增 `TREASURE_NATIVE_UI_ENABLED=true`，用于平台 JWT 内的只读发现。未修改凭据、写开关或源码执行门禁；`.env.example` 与默认关闭策略不变。

## 验证边界

- 主平台相关入口/能力/会话隔离：12 项通过。
- 独立展示与实际正式工作台集成：10 项 DOM 测试通过。其中新增两项实际渲染正式工作台：服务关闭时仍有鼠形象/四场景且不请求会话；服务允许时示例写入 Vue 草稿并回显到原 Composer。
- 原 React TS、Island TS、Vue PoC TS/构建通过；主 npm run build 的 prebuild 已生成原展示模块，dist 内核实含入口、本地字体与图片，主 JS 引用展示入口。后续核实主 Vite 配置为 logLevel: error，正常构建不会输出完成记录；原命令返回 0 并更新 dist。最新截图样式调整使用 --logLevel info 单独保存完整主构建记录。日志见 `evidence/treasure-native/entry-fix-build.log`。
- 不将 DOM 当作浏览器视觉验收。G-P1A 的截图、真实字体/焦点/窄屏与用户视觉确认仍待完成；本次接线是用户明确要求修复正式页面后进行的欢迎区接入，未进入 P1-B/P1-C/P2。
- Docker socket 访问被拒绝，无法检查或重建运行中容器，也没有宣称新页面已经在浏览器中生效。

## 生效与核验

原 `make docker-reload` 会重新构建包含原版展示的主前端，并重建容器使本地新增只读环境变量生效。仅 restart 已有容器不能更新它创建时的环境变量。正确目标拼写为 docker-reload。

已在本地生成 dist；还需在拥有 Docker 权限的终端执行：

```bash
make docker-reload
```

该目标本身会重建整个开发栈。若只刷新本次涉及的 web/nginx，且当前环境正是 make docker-reload 所用的 pgvector + AgentTeams 开发栈，可用同一组 Compose overlays 定向重建，保留其他服务：

```bash
docker compose --env-file .env \
  -f deploy/docker/docker-compose.yml \
  -f deploy/docker/docker-compose.pgvector.yml \
  -f deploy/agentteams/docker-compose.cygnusx-proxy.yml \
  up -d --no-deps --force-recreate web nginx
```

然后刷新寻宝鼠页面。预期首次空态有阿寻头像、四场景和原版输入区；只读服务状态仍以实际 capability 为准。开启 UI 不等于下载/分析写执行准入。

## 回退

只回退本报告列出的接线/build hook/Nginx 稳定入口增量；生成目录已加入 .gitignore，可由 prebuild 重建。撤销本地只读 opt-in 时只改该单一布尔配置，并重建 web 容器。不要覆盖既有 Phase5 工作或子仓未提交科研后端改动。本轮未提交、未推送、未部署。
