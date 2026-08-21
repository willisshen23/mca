# 活动数据 Mock API

基于 Excel 样例数据的活动查询接口，支持按活动名称模糊搜索。

## 数据文件

- `清洗后_活动运营数据.xlsx` — 活动样例数据（19 条记录，55 个字段）
- `活动模板清单接口.txt` — 活动模板清单数据（JSON 格式，6 条记录）

## 快速启动

```bash
# 方式一：直接运行（推荐）
cd mock
uvicorn app:app --reload --port 8005

# 方式二：作为 Python 模块运行
cd 项目根目录
python -m mock.app
```

## API 接口

### 1. 模糊搜索活动

```
GET /api/campaigns/search?q={keyword}
```

**参数：**
- `q` (query): 活动名称模糊查询关键词，空字符串返回所有活动
- `limit` (query, 可选): 返回条数上限，默认 50，最大 200

**示例：**
```bash
curl "http://localhost:8005/api/campaigns/search?q=流失客户"
```

**响应：**
```json
{
  "total": 2,
  "campaigns": [
    {
      "活动名称": "2025流失客户挽回T1输送_专班",
      "活动编号": "ACT20250512104494",
      "活动状态": "活动结束",
      "活动运营目标": "促资产提升",
      ...
    }
  ]
}
```

### 2. 列出所有活动（分页）

```
GET /api/campaigns?limit=50&offset=0
```

### 3. 精确查询单个活动

```
GET /api/campaigns/{activity_id}
```

**示例：**
```bash
curl "http://localhost:8001/api/campaigns/ACT20250612104742"
```

### 4. 获取全量分析模板信息

```
GET /api/templates
```

返回所有活动分析模板的关键字段：模板ID、模板名称、模板描述。

**响应：**
```json
{
  "total": 6,
  "templates": [
    {
      "template_id": "MB202606091500002668",
      "template_name": "策略中心_单策略分析优化模板",
      "template_desc": "适用于策略中心单活动的策略分析模块使用"
    }
  ]
}
```

### 5. 获取组件业务数值

```
POST /api/component-values
```

**请求体：**
```json
{
  "template_id": "MB202606091500002668",
  "activity_ids": ["ACT20250612104742"],
  "component_ids": ["overview", "customer_value", "asset_growth"],
  "metrics": []
}
```

**响应：**
```json
{
  "success": true,
  "template_id": "MB202606091500002668",
  "activity_count": 1,
  "component_values": {
    "overview": {},
    "customer_value": {},
    "asset_growth": {}
  }
}
```

### 6. 重新加载数据

```
POST /api/campaigns/reload
```

用于 Excel 文件更新后强制重新加载（开发调试用）。

## 集成到主 Backend

在 `backend/src/api/routers/__init__.py` 中注册：

```python
from mock.integration import include_mock_router

def create_api_router() -> APIRouter:
    router = APIRouter()
    # ... 现有路由 ...
    include_mock_router(router, prefix="/mock")
    return router
```

集成后接口路径变为：
- `GET /api/mock/campaigns/search?q=xxx`
- `GET /api/mock/campaigns`
- `GET /api/mock/campaigns/{activity_id}`
- `GET /api/mock/templates`
- `POST /api/mock/component-values`

## 数据模型

所有 55 个字段均通过 Pydantic 模型定义，字段名保持与 Excel 原始列名一致（中文键名），详见 `schemas.py`。
