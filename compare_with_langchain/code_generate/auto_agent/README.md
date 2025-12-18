# task_api

自动生成的 REST API 项目。

## 生成时间

2025-12-18 21:07:09

## 文件结构

```
task_api/
├── __init__.py
├── models.py      # Pydantic 数据模型
├── service.py     # 服务层
├── router.py      # FastAPI 路由
└── test_api.py    # 测试用例
```

## 使用方法

```python
from fastapi import FastAPI
from task_api.router import router

app = FastAPI()
app.include_router(router)
```

## 运行测试

```bash
pytest task_api/test_api.py -v
```
