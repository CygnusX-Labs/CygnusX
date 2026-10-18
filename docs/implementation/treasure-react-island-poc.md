# Treasure React Island P1-A PoC

> 后续变更：根据用户“先解决正式页面”的要求，欢迎区与 Composer 已接入正式工作台及主构建；本文以下保留最初 PoC 阶段记录。当前接线、只读开关与验证边界以 [重载修复报告](../implementation/treasure-native-entry-reload-fix.md) 为准，G-P1A 仍未通过。

状态：最小真实展示 PoC 已实现；隔离编译与 DOM 验证通过；浏览器/视觉 Gate BLOCKED。不是原版体验完整恢复，也不是发布 READY。

P0 仍保留 CONDITIONAL 结论。本阶段使用任务书明确允许的完全隔离 UI PoC 路径，不放开正式 native 入口，不依赖现场 403 已被确认。

## 代码与边界

| 位置 | 内容 |
|---|---|
| 子仓 `src/island/contract.ts` | typed 非敏感 context/messages/models/draft 与 callbacks |
| 子仓 `src/island/index.tsx` | mount/update/unmount、ShadowRoot、refcount 字体资源、原 EmptyState/Composer |
| 子仓 `src/island/reference.tsx` | 同一原展示组件在普通 document CSS 下渲染的对照页，不含原 SPA/auth |
| 子仓 `src/i18n/provider.tsx` | 新增受控 provider，不读取或修改平台语言存储 |
| 子仓 `src/components/chat/{EmptyState,Composer}.tsx` | 可选 Portal 容器与 typing callback；原默认行为保留 |
| 子仓 `src/components/ui/dialog.tsx` | 可选 Portal container |
| 子仓 `vite.island*.config.ts`、`tsconfig.island.json` | 隔离 React/对照构建与类型检查；无旧 env/Router 插件 |
| `frontend/poc/treasure-island/` | 独立 Vue 展示宿主、冲突样式探针、生命周期与交互测试 |
| `scripts/poc/check-treasure-island.sh` | 本地构建和测试复现入口 |
| `scripts/poc/treasure-island-browser.mjs` | 离线拦截本地产物的浏览器验证/截图 runner，阻断外网请求 |

主平台 `frontend/src/`、生产路由、生产部署、依赖清单和锁文件在 P1-A 未修改。子仓既有后端脏改动原样保留；修改前共用文件快照在 `evidence/treasure-native/p1a-baseline/`。子仓 HEAD 仍为 `88dae95e7294dea5004330203f56e4211776fd74`。

## 展示恢复矩阵

| 原 UI | PoC 实现证据 | 待验 |
|---|---|---|
| 阿寻头像、品牌名、问题标题/副标题 | 直接复用 EmptyState 与原 webp；DOM 有本地资产 | 实际图片绘制、字体、主视觉 |
| 四场景、双示例 | 原 TASKS 和双语字典；4 sections/8 buttons，四场景 callback 测试 | 点击与键盘真实浏览器体验 |
| 原 Composer / 模型选择 / 下铲 / 停止 | 直接复用，draft/model/streaming 由 Vue 控制 | IME、自动高度、触屏/焦点 |
| 中英、明暗 | props update；不改 html/title/storage | 4 视口 × 2 语言 × 2 主题截图 |
| 彩蛋 Dialog | 原遮罩 class 在 shadow Portal 内复用；Tab 双向边界、关闭焦点恢复与 focus guards 卸载的 DOM 验证 | 遮罩、Focus Trap/恢复、滚动、层叠 |
| BrandMark / 原独立 Header | 未移入展示首页，避免引入旧独立 Header | 需要时在平台导航另行复用原 BrandMark |
| Dataset/Literature/Trace/Grounding/Next Shovel | 尚未实现，属于 P1-B | PoC 非空 messages 显式拒绝，避免静默丢消息 |

旧 SPA 的身份、历史、Router、网络调用均未接入。`onOpenDataset` 和 messages 是后续 adapter 的保留类型，当前没有卡片展示实现。项目/模型仅为合成的非敏感测试 ViewModel，不宣称已接通真实项目与 Provider。

## 实际验证

证据全部位于 `evidence/treasure-native/`：

| 验证 | 当前结果 | 日志 |
|---|---|---|
| 原 React `tsc --noEmit` | PASS | `p1a-react-types.log` |
| 独立 Island 与新 Vite 配置 TS | PASS | `p1a-island-types.log` |
| React library 构建 | PASS | `p1a-library-build.log` |
| 原展示对照页构建 | PASS | `p1a-reference-build.log` |
| Vue PoC 类型检查 | PASS | `p1a-vue-types.log` |
| Vue 消费 React 产物构建 | PASS | `p1a-vue-build.log` |
| 隔离 DOM | 8 passed | `p1a-dom-tests.log` |
| 导入边界图 | 1792 modules，forbidden=[] | `p1a-module-inventory.json` |
| 真浏览器 | BLOCKED：socket setsockopt EPERM / SIGTRAP | `p1a-browser-attempt.log`、`p1a-browser/result.json` |
| dev server | BLOCKED：listen EPERM 127.0.0.1:5178 | 工具返回；浏览器 runner 本身不依赖监听端口 |
| 截图 / 人工视觉 | 未执行，没有生成截图 | `p1a-browser/result.json` 的 screenshots=[] |

DOM 测试证明 DOM/回调/指定资源释放，不能证明像素、字体加载、焦点循环、移动布局或所有事件监听器均无泄漏。没有把 jsdom 结果计为真实 E2E。主平台源码未被本 PoC 修改，P0 的主前端 type/build 通过记录保留；P0 全仓门禁失败也仍保留。

## 复现

已有两侧 node_modules 时，在父仓根运行：

```bash
bash scripts/poc/check-treasure-island.sh
```

产物位于 `/tmp/treasure-island-poc-lib/`、`/tmp/treasure-reference-poc-dist/`、`/tmp/treasure-vue-poc-dist/`，不进入子仓提交。可运行浏览器的环境中指定**已安装** playwright-core 与 Chromium：

```bash
TREASURE_POC_PLAYWRIGHT_PATH=/path/to/playwright-core/index.js \
TREASURE_POC_CHROMIUM=/path/to/chrome \
node scripts/poc/treasure-island-browser.mjs
```

runner 仅提供本地编译产物，拒绝其他 origin；计划输出 32 张原展示/Island 对照图及弹窗图。对照页是原 EmptyState/Composer 的实际渲染，不代表旧独立 SPA 的完整截图。还需与用户原截图一起人工对照；脚本通过也只标记 AUTOMATED_CHECKS_PASSED_VISUAL_REVIEW_PENDING。

## 尚未闭合的 Gate

G-P1A 未通过：缺真浏览器图像、字体/窄屏/焦点验证与用户视觉确认，字体已外置分片，仍需实际加载及最终 chunk 预算评估。具体隔离方案与回退见 `docs/adr/treasure-react-island-poc.md`。

P1-B、P1-C、P2、Release 不因编译成功而自动启动。没有更改 `WRITE_RUNTIME_ACCEPTED=False` 或 `worker_paths_verified=false`，没有下载、分析、审批执行、生产访问或部署。下一步是在允许 Chromium 运行的环境执行 runner、逐项修复真实渲染问题并取得视觉验收，再决定正式依赖方案。

本轮 PoC 复核修复：Radix 非模态路径原本省略遮罩，已补 shadow 内原样遮罩；以 ShadowRoot.activeElement 处理键盘边界并显式恢复头像焦点。离线 DOM 验证更新为 8 项通过；浏览器 runner 新增字体/图片加载、水平溢出、样式泄漏与真实键盘焦点断言，当前仍因 socket 权限未执行。
