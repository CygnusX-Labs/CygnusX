# OmicHub 知识库目录

`docs/knowledge/` 是 OmicHub 仓库内所有知识库源文件的统一存放目录。后续新增知识库不再放入
日期版本目录或其他 `docs/` 子目录。

实现、导入、权限过滤、向量/关键词召回以及 PDF/图片混合索引的完整说明见
[`knowledge-base-implementation.md`](knowledge-base-implementation.md)。

## 目录约定

- 单篇、无附件的知识文档可以直接保存为 `docs/knowledge/<document>.md`。
- 包含多篇文档、PDF、图片或其他附件的领域知识库使用
  `docs/knowledge/<knowledge-base-id>/` 独立目录。
- 领域知识库的入口 Markdown、附件和该知识库专属资源应保存在同一个领域目录内。
- 需要显示在实验室知识库导航中的入口文档，必须登记到 `docs/knowledge/meta.yaml`。
- 需要进入数据库向量/全文索引的知识库，应由对应导入脚本从 `docs/knowledge/` 读取，不应引用
  日期版本目录。

## 当前领域知识库

| 知识库 | 入口文件 | 导入方式 |
| --- | --- | --- |
| RNA-seq | `docs/knowledge/rna-seq/RNA-seq.md` | `scripts/import_rnaseq_knowledge.py` |
| ATAC-seq | `docs/knowledge/atac-seq/ATAC-seq.md` | `scripts/import_atacseq_knowledge.py` |
| 单细胞 RNA-seq | `docs/knowledge/sc-seq/sc-seq.md` | `scripts/import_scseq_knowledge.py` |

## 新增知识库示例

```text
docs/knowledge/example-kb/
├── README.md
├── example-kb.md
├── file/
└── image/
```

新增后应同步检查：

1. `meta.yaml` 中的 `id` 唯一且 `file` 使用相对 `docs/knowledge/` 的路径；
2. Markdown 内附件路径在领域目录内可解析；
3. 导入脚本、测试、Agent Prompt 和 README 不再引用旧目录；
4. `/docs-static/knowledge/...` 静态资源路径和 AI 检索结果可正常访问。
