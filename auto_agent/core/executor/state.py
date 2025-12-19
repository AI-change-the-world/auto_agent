"""
状态管理工具

提供状态读取、更新、压缩等功能。
"""

import json
from typing import Any, Dict, Optional


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """从嵌套字典中获取值，支持点号路径"""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


def compress_state_for_llm(state: Dict[str, Any], max_chars: int = 4000) -> str:
    """压缩状态信息供 LLM 使用"""
    compressed = {}
    for key, value in state.items():
        if key == "control":
            continue
        if key == "documents" and isinstance(value, list):
            compressed["documents"] = f"[{len(value)} documents]"
            if value:
                compressed["document_ids"] = [d.get("id") for d in value[:10]]
        elif key == "document_ids" and isinstance(value, list):
            compressed["document_ids"] = value[:20]
        elif isinstance(value, dict) and len(str(value)) > 500:
            compressed[key] = f"{{...{len(value)} keys}}"
        elif isinstance(value, list) and len(value) > 10:
            compressed[key] = f"[{len(value)} items]"
        else:
            compressed[key] = value

    result = json.dumps(compressed, ensure_ascii=False, indent=2)
    if len(result) > max_chars:
        result = result[:max_chars] + "..."
    return result


def update_state_from_result(
    tool_name: Optional[str],
    result: Dict[str, Any],
    state: Dict[str, Any],
    step_id: Optional[str],
    tool_registry: Any,
) -> None:
    """
    根据工具执行结果更新状态字典

    状态结构设计（与 BindingPlanner 对齐）：
    ```
    state = {
        "inputs": {"query": "...", ...},           # 用户输入
        "control": {"iterations": 0, ...},         # 控制信息
        "steps": {                                  # 步骤输出（新增）
            "1": {
                "tool": "analyze_requirements",
                "output": {...},                   # 完整输出
            },
            "2": {
                "tool": "design_api",
                "output": {...},
            },
        },
        # 兼容旧逻辑：也写入顶层（后续可废弃）
        "entities": [...],
        "endpoints": [...],
    }
    ```

    BindingPlanner 的 source 格式：
    - "step_1.output.entities" -> state["steps"]["1"]["output"]["entities"]
    - "query" (user_input) -> state["inputs"]["query"]

    Args:
        tool_name: 工具名称
        result: 执行结果
        state: 状态字典
        step_id: 步骤 ID（用于存储到 steps 下）
        tool_registry: 工具注册表
    """
    if not result or not result.get("success"):
        return

    if not tool_name:
        return

    # 获取工具定义
    tool = tool_registry.get_tool(tool_name) if tool_registry else None

    # 需要排除的通用字段
    exclude_keys = {"success", "error", "message"}

    # 获取 state_mapping（如果有）
    state_mapping = {}
    if tool and hasattr(tool, "definition") and tool.definition.state_mapping:
        state_mapping = tool.definition.state_mapping

    # 确定要写入的字段
    fields_to_write = set()
    if tool and tool.definition.output_schema:
        fields_to_write = set(tool.definition.output_schema.keys()) - exclude_keys
    else:
        fields_to_write = set(result.keys()) - exclude_keys

    # === 新增：写入 state["steps"][step_id] ===
    if step_id:
        if "steps" not in state:
            state["steps"] = {}

        # 过滤掉 success/error/message，只保留有意义的输出
        clean_output = {k: v for k, v in result.items() if k not in exclude_keys}

        state["steps"][step_id] = {
            "tool": tool_name,
            "output": clean_output,
        }

    # === 兼容旧逻辑：也写入顶层（后续可废弃）===
    for key in fields_to_write:
        if key in result:
            # 应用 state_mapping（如果有映射则用映射后的 key，否则用原 key）
            target_key = state_mapping.get(key, key)
            state[target_key] = result[key]
