"""
全栈项目生成器 - 代码写入工具

CodeWriterTool: 将生成的代码写入文件
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from auto_agent import BaseTool, ToolDefinition, ToolParameter
from auto_agent.models import (
    PostSuccessConfig,
    ResultHandlingConfig,
    ToolPostPolicy,
    ValidationConfig,
)


class CodeWriterTool(BaseTool):
    """
    代码写入工具

    将生成的代码写入文件，支持：
    - 自动创建目录
    - 添加文件头注释
    - 格式化代码（可选）
    - 备份已存在的文件
    """

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_code",
            description="将生成的代码写入文件。每次代码生成工具执行后，都应该调用此工具将代码保存到文件。",
            parameters=[
                ToolParameter(
                    name="filename",
                    type="string",
                    description="文件名（如 models.py, service.py）",
                    required=True,
                ),
                ToolParameter(
                    name="code",
                    type="string",
                    description="要写入的代码内容",
                    required=True,
                ),
                ToolParameter(
                    name="code_type",
                    type="string",
                    description="代码类型: model/service/router/test/config",
                    required=False,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="代码描述（会添加到文件头注释）",
                    required=False,
                ),
                ToolParameter(
                    name="overwrite",
                    type="boolean",
                    description="是否覆盖已存在的文件（默认 True）",
                    required=False,
                ),
            ],
            category="file_operation",
            output_schema={
                "file_path": {"type": "string", "description": "写入的文件路径"},
                "bytes_written": {"type": "integer", "description": "写入的字节数"},
                "line_count": {"type": "integer", "description": "代码行数"},
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=False,  # 写文件不是高影响力操作
                    requires_consistency_check=False,
                    extract_working_memory=False,
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=False,
                ),
            ),
        )

    async def execute(
        self,
        filename: str,
        code: str,
        code_type: str = "code",
        description: str = "",
        overwrite: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """写入代码到文件"""
        try:
            file_path = self.output_dir / filename

            # 检查文件是否存在
            if file_path.exists() and not overwrite:
                return {
                    "success": False,
                    "error": f"文件已存在: {file_path}",
                    "file_path": str(file_path),
                }

            # 备份已存在的文件
            if file_path.exists():
                backup_path = file_path.with_suffix(
                    f".bak.{datetime.now().strftime('%H%M%S')}"
                )
                file_path.rename(backup_path)

            # 添加文件头注释
            header = self._generate_header(filename, code_type, description)
            full_code = header + code

            # 写入文件
            file_path.write_text(full_code, encoding="utf-8")

            line_count = len(code.split("\n"))
            bytes_written = len(full_code.encode("utf-8"))

            return {
                "success": True,
                "file_path": str(file_path),
                "filename": filename,
                "bytes_written": bytes_written,
                "line_count": line_count,
                "code_type": code_type,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_header(
        self,
        filename: str,
        code_type: str,
        description: str,
    ) -> str:
        """生成文件头注释"""
        type_names = {
            "model": "数据模型",
            "service": "服务层",
            "router": "路由层",
            "test": "测试用例",
            "config": "配置文件",
        }
        type_name = type_names.get(code_type, "代码")

        header = f'''"""
{filename} - {type_name}

{description if description else "自动生成的代码"}

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

'''
        return header


class ProjectInitTool(BaseTool):
    """
    项目初始化工具

    创建项目目录结构和基础文件
    """

    def __init__(self, base_output_dir: str):
        self.base_output_dir = Path(base_output_dir)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="init_project",
            description="初始化项目目录结构，创建必要的文件夹和 __init__.py 文件。应该在开始生成代码之前调用。",
            parameters=[
                ToolParameter(
                    name="project_name",
                    type="string",
                    description="项目名称（英文，snake_case）",
                    required=True,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="项目描述",
                    required=False,
                ),
            ],
            category="file_operation",
            output_schema={
                "project_dir": {"type": "string", "description": "项目目录路径"},
                "created_files": {"type": "array", "description": "创建的文件列表"},
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(on_fail="abort"),
                post_success=PostSuccessConfig(
                    high_impact=True,
                    extract_working_memory=True,
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="config",
                ),
            ),
        )

    async def execute(
        self,
        project_name: str,
        description: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """初始化项目"""
        try:
            project_dir = self.base_output_dir / project_name
            project_dir.mkdir(parents=True, exist_ok=True)

            created_files = []

            # 创建 __init__.py
            init_content = f'''"""
{project_name}

{description if description else "自动生成的 REST API 项目"}

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

__version__ = "0.1.0"
'''
            init_file = project_dir / "__init__.py"
            init_file.write_text(init_content, encoding="utf-8")
            created_files.append("__init__.py")

            # 创建 README.md
            readme_content = f"""# {project_name}

{description if description else "自动生成的 REST API 项目"}

## 生成时间

{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 文件结构

```
{project_name}/
├── __init__.py      # 模块入口
├── models.py        # Pydantic 数据模型
├── service.py       # 服务层
├── router.py        # FastAPI 路由
└── test_api.py      # 测试用例
```

## 使用方法

```python
from fastapi import FastAPI
from {project_name}.router import router

app = FastAPI(title="{project_name}")
app.include_router(router)
```

## 运行测试

```bash
pytest {project_name}/test_api.py -v
```
"""
            readme_file = project_dir / "README.md"
            readme_file.write_text(readme_content, encoding="utf-8")
            created_files.append("README.md")

            return {
                "success": True,
                "project_name": project_name,
                "project_dir": str(project_dir),
                "created_files": created_files,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
