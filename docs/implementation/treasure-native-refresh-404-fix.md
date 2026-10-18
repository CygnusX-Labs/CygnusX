# 寻宝鼠直接访问与刷新 404 修复

用户入口：`http://192.168.5.102:8888/treasure-mouse`。

## 原因与改动

此前关闭旧独立应用时，主开发/生产 Nginx 对精确 `/treasure-mouse` 使用了 `return 404`，连同新的 Vue 路由入口一起拦截。站内 Vue history 导航不请求该文档所以能进入，直接访问/刷新由 Nginx 处理则会 404。这是前序入口隔离改动的遗漏。

本轮在 `deploy/docker/nginx/{nginx.conf,nginx.prod.conf,frontend.conf}` 统一边界：

- 精确 `/treasure-mouse`：`try_files /index.html =404` 返回主平台 SPA，禁止缓存。
- 精确 `/treasure-mouse/`：302 到无尾斜杠入口，保留查询参数。
- 旧 `/treasure-mouse/` 下的账号、聊天、静态资源等子路径：继续 404，不转发旧 Node SPA。

平台 JWT/BFF 授权行为未修改，不涉及前端或后端重新构建。

## 校验与生效边界

三份配置的入口/重定向/旧子路径拦截静态检查通过；本地 dist/index.html 存在；开发 Compose config --quiet 通过；git diff --check 通过。检查记录位于 `evidence/treasure-native/refresh-route-check.json`。

当前会话连接 192.168.5.102:8888 失败，Docker socket 报 operation not permitted，宿主未安装独立 nginx，故未执行真实 nginx -t、未 reload、未验证现场 HTTP 状态。不能将静态检查称为运行时验证。

现有开发 Compose 将 nginx.conf 挂载到 cygnusx-nginx，无需重建前端或整个栈。在有 Docker 权限的宿主执行：

```bash
docker exec cygnusx-nginx nginx -t && docker exec cygnusx-nginx nginx -s reload
```

随后访问/刷新无尾斜杠入口应返回主前端 HTML；带尾斜杠入口应先 302；旧 `/treasure-mouse/api/chat` 等路径应保持 404。若目标容器运行在其他主机，需先同步这次配置到其挂载目录后再校验和 reload。前端实际模块授权继续由平台处理。
