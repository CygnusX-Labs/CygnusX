# API 设计约定

## DTO 与响应

项目没有强制所有接口套用一个 `code/message/data` 包装。路由根据用例返回具体的 Pydantic DTO；分页请求优先复用 `src/cygnusx/application/schemas/base.py` 的 `PaginationParams`（`page` 默认 1、`page_size` 默认 20、最大 200、`sort_by`、`sort_order`），响应使用领域对应的 `*ListResponse` 或资源 DTO。新增接口先查同领域路由和 schema，保持字段命名、状态码和错误结构一致。

示例：

```python
@router.get("/items", response_model=ItemListResponse)
async def list_items(params: PaginationParams = Depends()) -> ItemListResponse:
    ...
```

## 异常处理

| 异常 | HTTP body code | 说明 |
|---|---|---|
| 业务异常 | 4xx/5xx | `CygnusXException` 及其领域子类 |
| 参数校验失败 | 422 | `RequestValidationError` |
| 未处理异常 | 500 | 兜底，不暴露堆栈 |

## JWT 认证

- Access Token 默认 30 分钟
- Refresh Token 默认 7 天
- 生产环境必须替换默认 `JWT_SECRET_KEY`
- 引入 `token_version` 实现 JWT 吊销

## 路由注册

所有模块路由在 `src/cygnusx/api/v1/router.py` 统一挂载，不要在应用入口散落注册。
