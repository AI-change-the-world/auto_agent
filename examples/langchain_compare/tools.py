"""
LangChain 工具定义

与 auto_agent 版本对比，使用 LangChain 的 @tool 装饰器定义工具
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# 全局 LLM 客户端（在 main 中初始化）
_llm_client: Optional[ChatOpenAI] = None
_materials_dir: Optional[str] = None


def init_tools(llm_client: ChatOpenAI, materials_dir: str):
    """初始化工具所需的全局变量"""
    global _llm_client, _materials_dir
    _llm_client = llm_client
    _materials_dir = materials_dir


@tool
async def read_materials(file_types: str = ".txt,.md") -> Dict[str, Any]:
    """
    读取研究素材目录下的所有文件，返回文件内容和 LLM 生成的摘要。
    这是研究的第一步，用于获取原始数据。

    Args:
        file_types: 要读取的文件类型，用逗号分隔（如 .txt,.md）

    Returns:
        包含 materials 列表和 total_files 数量的字典
    """
    global _llm_client, _materials_dir

    if not _materials_dir:
        return {"success": False, "error": "素材目录未初始化"}

    try:
        dir_path = Path(_materials_dir)
        if not dir_path.exists():
            return {"success": False, "error": f"素材目录不存在: {_materials_dir}"}

        extensions = [ext.strip() for ext in file_types.split(",")]
        materials = []

        for file_path in dir_path.iterdir():
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    content = file_path.read_text(encoding="utf-8")

                    # 使用 LLM 生成摘要
                    summary_prompt = f"""请为以下文件内容生成一个简洁的摘要（100字以内）。
文件名: {file_path.name}
内容:
{content[:3000]}
{"..." if len(content) > 3000 else ""}

请直接输出摘要，不要有任何前缀。"""

                    summary_response = await _llm_client.ainvoke(summary_prompt)
                    summary = summary_response.content.strip()

                    materials.append(
                        {
                            "filename": file_path.name,
                            "content": content,
                            "summary": summary,
                            "word_count": len(content),
                        }
                    )
                except Exception as e:
                    materials.append(
                        {
                            "filename": file_path.name,
                            "error": str(e),
                        }
                    )

        if not materials:
            return {
                "success": False,
                "error": f"目录中没有找到 {file_types} 格式的文件",
            }

        return {
            "success": True,
            "materials": materials,
            "total_files": len(materials),
            "total_words": sum(m.get("word_count", 0) for m in materials),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_json_input(data: Any) -> Any:
    """解析输入，支持字符串或原始类型"""
    if isinstance(data, (dict, list)):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data
    return data


@tool
async def analyze_content(materials: str, focus: str = "") -> Dict[str, Any]:
    """
    分析研究素材内容，使用 LLM 提取主题、论点、关键数据和知识缺口。
    这是深度研究的核心分析步骤。

    Args:
        materials: 素材列表 JSON 字符串（从 read_materials 获取）
        focus: 研究重点/关注方向（可选）

    Returns:
        包含 main_themes, key_arguments, overall_insight 等的分析结果
    """
    global _llm_client

    # 解析输入
    materials_data = _parse_json_input(materials)
    if isinstance(materials_data, dict):
        materials_data = materials_data.get("materials", [])

    if not materials_data:
        return {"success": False, "error": "没有可分析的素材"}

    try:
        # 构建素材内容
        materials_text = ""
        for m in materials_data:
            if "content" in m:
                materials_text += f"\n\n=== {m['filename']} ===\n"
                materials_text += m["content"][:2500]
                if len(m["content"]) > 2500:
                    materials_text += "\n[...内容已截断...]"

        focus_instruction = f"\n特别关注: {focus}" if focus else ""

        prompt = f"""请深入分析以下研究素材，提取关键信息。{focus_instruction}

素材内容:
{materials_text}

请以 JSON 格式返回分析结果，包含以下字段:
{{
    "main_themes": ["主题1", "主题2", ...],
    "key_arguments": [
        {{"argument": "论点内容", "source": "来源文件", "evidence": "支撑证据"}}
    ],
    "key_data": [
        {{"data": "数据内容", "context": "上下文", "source": "来源"}}
    ],
    "knowledge_gaps": ["知识缺口1", ...],
    "cross_references": ["文件间的关联1", ...],
    "overall_insight": "整体洞察（200字以内）"
}}"""

        response = await _llm_client.ainvoke(prompt)
        response_text = response.content

        # 解析 JSON
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            analysis["success"] = True
            analysis["analysis_result"] = analysis.copy()
            return analysis
        else:
            return {
                "success": True,
                "raw_analysis": response_text,
                "main_themes": [],
                "overall_insight": response_text[:500],
            }

    except json.JSONDecodeError:
        return {
            "success": True,
            "raw_analysis": response_text,
            "parse_error": "JSON解析失败",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
