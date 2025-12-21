"""
LangChain 工具定义 - 第二部分

反思、润色和报告生成工具
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# 添加项目根目录到 path（支持直接运行）
_script_dir = Path(__file__).parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _parse_json_input(data: Any) -> Dict[str, Any]:
    """解析输入，支持字符串或字典"""
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {"raw": data}
    return {"raw": str(data)}


@tool
async def reflect(analysis: str, depth: str = "medium") -> Dict[str, Any]:
    """
    对分析结果进行批判性反思，使用 LLM 发现逻辑问题、潜在偏见和缺失视角。
    这是确保研究质量的关键步骤。

    Args:
        analysis: 分析结果 JSON 字符串（从 analyze_content 获取）
        depth: 反思深度 - shallow(浅层), medium(中等), deep(深入)

    Returns:
        包含 logical_issues, potential_biases, confidence_assessment 等的反思结果
    """
    from examples.langchain_compare.tools import _llm_client

    try:
        # 解析输入
        analysis_data = _parse_json_input(analysis)

        depth_instructions = {
            "shallow": "进行快速的逻辑检查和表面问题发现",
            "medium": "进行中等深度的批判性分析，检查论证逻辑和潜在偏见",
            "deep": "进行深入的批判性反思，包括哲学层面的质疑和多角度审视",
        }

        depth_instruction = depth_instructions.get(depth, depth_instructions["medium"])
        analysis_text = json.dumps(analysis_data, ensure_ascii=False, indent=2)

        prompt = f"""请对以下研究分析结果进行批判性反思。

反思深度要求: {depth_instruction}

分析结果:
{analysis_text[:4000]}

请从以下角度进行反思，并以 JSON 格式返回:
{{
    "logical_issues": [
        {{"issue": "问题描述", "location": "出现位置", "suggestion": "改进建议"}}
    ],
    "potential_biases": [
        {{"bias": "偏见描述", "impact": "可能影响", "mitigation": "缓解方法"}}
    ],
    "missing_perspectives": [
        {{"perspective": "视角描述", "importance": "重要性说明"}}
    ],
    "strengthening_suggestions": [
        {{"current": "当前状态", "suggestion": "改进建议"}}
    ],
    "confidence_assessment": {{
        "overall_score": 0.0-1.0,
        "reasoning": "评估理由"
    }},
    "reflection_summary": "反思总结（200字以内）"
}}"""

        response = await _llm_client.ainvoke(prompt)
        response_text = response.content

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            reflection = json.loads(json_match.group())
            reflection["success"] = True
            reflection["reflection_result"] = reflection.copy()
            return reflection
        else:
            return {"success": True, "raw_reflection": response_text}

    except json.JSONDecodeError:
        return {"success": True, "raw_reflection": response_text}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def polish_text(text: str, style: str = "professional") -> Dict[str, Any]:
    """
    对文本进行语言润色，使用 LLM 提升表达的专业性、清晰度和可读性。
    通常用于润色最终报告。

    Args:
        text: 待润色的文本
        style: 目标风格 - academic(学术), professional(专业), casual(通俗)

    Returns:
        包含 polished_text 的结果
    """
    from examples.langchain_compare.tools import _llm_client

    if not text:
        return {"success": False, "error": "没有待润色的文本"}

    try:
        style_instructions = {
            "academic": "使用学术论文的严谨风格，准确使用专业术语",
            "professional": "使用专业报告的风格，清晰准确，兼顾可读性",
            "casual": "使用通俗易懂的风格，避免过多术语",
        }

        style_instruction = style_instructions.get(
            style, style_instructions["professional"]
        )

        prompt = f"""请对以下文本进行语言润色。

风格要求: {style_instruction}

原文:
{text}

请直接输出润色后的完整文本，保持原有结构，提升表达质量。"""

        response = await _llm_client.ainvoke(prompt)

        return {
            "success": True,
            "polished_text": response.content.strip(),
            "original_length": len(text),
            "polished_length": len(response.content),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def generate_report(
    analysis: str,
    topic: str,
    reflection: Optional[str] = None,
    format: str = "standard",
) -> Dict[str, Any]:
    """
    基于分析结果和反思意见，使用 LLM 生成结构化的研究报告。
    这是研究流程的最终输出步骤。

    Args:
        analysis: 内容分析结果 JSON 字符串
        topic: 研究主题
        reflection: 反思结果 JSON 字符串（可选）
        format: 报告格式 - brief(简报), standard(标准), detailed(详细)

    Returns:
        包含 report 和 word_count 的结果
    """
    from examples.langchain_compare.tools import _llm_client

    try:
        # 解析输入
        analysis_data = _parse_json_input(analysis)
        reflection_data = _parse_json_input(reflection) if reflection else None

        format_instructions = {
            "brief": "生成简明扼要的研究简报（500-800字）",
            "standard": "生成标准研究报告（1000-1500字）",
            "detailed": "生成详细研究报告（2000字以上）",
        }

        format_instruction = format_instructions.get(
            format, format_instructions["standard"]
        )

        analysis_text = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        reflection_text = (
            json.dumps(reflection_data, ensure_ascii=False, indent=2)
            if reflection_data
            else "无"
        )

        prompt = f"""请基于以下分析结果和反思意见，生成一份专业的研究报告。

研究主题: {topic}
格式要求: {format_instruction}

=== 内容分析结果 ===
{analysis_text[:3000]}

=== 批判性反思 ===
{reflection_text[:2000]}

请生成一份 Markdown 格式的研究报告，包含以下部分:
1. 标题和摘要
2. 研究背景与问题
3. 核心发现
4. 讨论与反思
5. 局限性与未来方向
6. 结论

请直接输出 Markdown 格式的报告内容。"""

        response = await _llm_client.ainvoke(prompt)

        return {
            "success": True,
            "report": response.content,
            "word_count": len(response.content),
            "format": format,
            "topic": topic,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_all_tools():
    """获取所有工具列表"""
    from examples.langchain_compare.tools import analyze_content, read_materials

    return [read_materials, analyze_content, reflect, polish_text, generate_report]
