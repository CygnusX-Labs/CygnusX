# 实验室知识库

知识库采用「文件即数据源」的轻量架构：文档直接以 `.md` 存储在 `docs/knowledge/`，通过 `meta.yaml` 注册。

## 目录结构

```text
docs/knowledge/
├── meta.yaml
├── getting-started.md
├── data-directory-guide.md
├── figure/
└── ...
```

运行时副本：`/data/omichub/omichub_data/knowledge/`（用于备份迁移）。

## meta.yaml

```yaml
title: "实验室知识库"
items:
  - id: "getting-started"
    title: "快速入门"
    file: "getting-started.md"
    category: "上手指南"
```

## API 接口

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/v1/docs/knowledge` | 登录用户 |
| GET | `/api/v1/docs/knowledge/{doc_id}` | 登录用户 |
| PUT | `/api/v1/docs/knowledge/{doc_id}` | 管理员 |
| POST | `/api/v1/docs/knowledge/upload` | 管理员 |

## 安全设计

- 路径遍历防护：`_resolve_doc_path()` 限制只能访问 `meta.yaml` 注册的文件
- 原子写入：先写 `.md.tmp` 再 `Path.replace()`
- 图片上传白名单：`png/jpg/gif/svg/webp`，单文件最大 10MB

## 新增文档

1. 在 `docs/knowledge/` 新建 `.md`
2. 在 `meta.yaml` 添加条目
3. 配图放入 `docs/knowledge/figure/`，正文用 `./figure/xxx.png` 引用
4. 刷新前端即可见
