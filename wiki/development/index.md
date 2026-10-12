# 开发规范

本章节面向 CygnusX 开发者，说明如何新增模块、设计 API、编写前端页面、管理数据库迁移、扩展 Flow/工具以及执行验证。修改前先读 [Wiki 总览](../README) 和 `ARCHITECTURE_DESIN/README.md` 中对应的 as-built 文档。

## 内容导航

- [模块设计与接入](module-design) — 新增模块的设计原则、文档模板与评审问题
- [前端规范与工具箱](frontend-conventions) — Vue 3 目录组织、UI/主题/响应式约定
- [API 设计约定](api-design) — REST/WebSocket 接口、DTO、错误码与分页规范
- [数据库迁移](database-migrations) — Alembic 迁移创建、检查与常见错误修复
- [分析流程扩展](flow-extension) — Flow YAML、Snakefile 与参数映射
- [生信工具接入](bio-tool-guide) — 工具注册、配置与交付闭环

## 开发前必读

1. 先阅读 `ARCHITECTURE_DESIN/CygnusX_platform_design.md` 的设计原则与模块类型划分，并核对对应的 as-built 文档。
2. 新增模块前，按 [模块设计与接入](module-design) 完成可审查设计文档；当前设计文档应保存在
   `ARCHITECTURE_DESIN/` 或 `docs/` 的活动位置，不要把日期快照或提案当作唯一规范。
3. 前后端接口先定契约（Pydantic DTO ↔ TypeScript types），再写页面。
4. 所有资源操作必须校验认证、角色与所属关系。

## 最低验证命令

```bash
# 后端
uv run ruff check src tests
uv run pytest <相关测试路径>

# 前端
cd frontend
npm run type-check
npm run build
```
