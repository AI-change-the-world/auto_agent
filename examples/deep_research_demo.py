"""
Deep Research 智能体示例 - 自主规划版本

演示用户用自然语言描述需求，由智能体自主规划执行路径并得到结果。

核心特点：
- LLM 根据用户需求动态规划执行步骤
- 所有工具都使用 LLM 驱动，不使用硬编码逻辑
- 包含反思工具和语言润色工具
- 支持失败重试和重规划

使用方法:
1. 设置环境变量:
   export OPENAI_API_KEY=your-api-key  # 或 DEEPSEEK_API_KEY
   export OPENAI_BASE_URL=https://api.deepseek.com/v1  # 可选
   export OPENAI_MODEL=deepseek-chat  # 可选

2. 准备素材（可选，会自动创建示例）:
   在 examples/research_materials/ 目录下放置 .txt 或 .md 文件

3. 运行:
   python examples/deep_research_demo.py
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from auto_agent import (
    AutoAgent,
    BaseTool,
    OpenAIClient,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)


# ==================== LLM 客户端配置 ====================


def get_llm_client() -> Optional[OpenAIClient]:
    """获取 LLM 客户端（通过环境变量配置）"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    return OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=120.0,
    )


# ==================== 工具定义（全部使用 LLM 驱动） ====================


class ReadMaterialsTool(BaseTool):
    """
    读取研究素材工具

    读取指定目录下的素材文件，并使用 LLM 生成每个文件的摘要
    """

    def __init__(self, llm_client: OpenAIClient, materials_dir: str):
        self.llm_client = llm_client
        self.materials_dir = materials_dir

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_materials",
            description="读取研究素材目录下的所有文件，返回文件内容和 LLM 生成的摘要。这是研究的第一步，用于获取原始数据。",
            parameters=[
                ToolParameter(
                    name="file_types",
                    type="string",
                    description="要读取的文件类型，用逗号分隔（如 .txt,.md）",
                    required=False,
                ),
            ],
            category="file_operation",
            output_schema={
                "materials": {"type": "array", "description": "素材列表"},
                "total_files": {"type": "integer", "description": "文件总数"},
            },
        )

    async def execute(self, file_types: str = ".txt,.md", **kwargs) -> Dict[str, Any]:
        """读取素材文件"""
        try:
            dir_path = Path(self.materials_dir)
            if not dir_path.exists():
                return {"success": False, "error": f"素材目录不存在: {self.materials_dir}"}

            extensions = [ext.strip() for ext in file_types.split(",")]
            materials = []

            for file_path in dir_path.iterdir():
                if file_path.is_file() and file_path.suffix in extensions:
                    try:
                        content = file_path.read_text(encoding="utf-8")

                        # 使用 LLM 生成文件摘要
                        summary = await self._generate_summary(file_path.name, content)

                        materials.append({
                            "filename": file_path.name,
                            "content": content,
                            "summary": summary,
                            "word_count": len(content),
                        })
                    except Exception as e:
                        materials.append({
                            "filename": file_path.name,
                            "error": str(e),
                        })

            if not materials:
                return {"success": False, "error": f"目录中没有找到 {file_types} 格式的文件"}

            return {
                "success": True,
                "materials": materials,
                "total_files": len(materials),
                "total_words": sum(m.get("word_count", 0) for m in materials),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _generate_summary(self, filename: str, content: str) -> str:
        """使用 LLM 生成文件摘要"""
        prompt = f"""请为以下文件内容生成一个简洁的摘要（100字以内）。

文件名: {filename}

内容:
{content[:3000]}
{"..." if len(content) > 3000 else ""}

请直接输出摘要，不要有任何前缀。"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            return response.strip()
        except Exception as e:
            return f"摘要生成失败: {str(e)}"


class AnalyzeContentTool(BaseTool):
    """
    内容分析工具

    使用 LLM 分析素材内容，提取主题、论点、关键数据等
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_content",
            description="分析研究素材内容，使用 LLM 提取主题、论点、关键数据和知识缺口。这是深度研究的核心分析步骤。",
            parameters=[
                ToolParameter(
                    name="materials",
                    type="array",
                    description="素材列表（从 read_materials 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="focus",
                    type="string",
                    description="研究重点/关注方向",
                    required=False,
                ),
            ],
            category="analysis",
            output_schema={
                "analysis_result": {"type": "object", "description": "完整分析结果"},
                "main_themes": {"type": "array", "description": "主要主题"},
                "key_arguments": {"type": "array", "description": "核心论点"},
                "overall_insight": {"type": "string", "description": "整体洞察"},
            },
            # 参数别名：从 state 的哪个字段获取参数
            param_aliases={
                "materials": "materials",
            },
        )

    async def execute(
        self,
        materials: List[Dict[str, Any]],
        focus: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """使用 LLM 分析素材内容"""
        try:
            if not materials:
                return {"success": False, "error": "没有可分析的素材"}

            # 构建素材内容
            materials_text = ""
            for m in materials:
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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2000,
            )

            # 解析 JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis["success"] = True
                # 保存完整分析结果供后续工具使用
                analysis["analysis_result"] = {
                    "main_themes": analysis.get("main_themes", []),
                    "key_arguments": analysis.get("key_arguments", []),
                    "key_data": analysis.get("key_data", []),
                    "knowledge_gaps": analysis.get("knowledge_gaps", []),
                    "overall_insight": analysis.get("overall_insight", ""),
                }
                return analysis
            else:
                fallback = {
                    "success": True,
                    "raw_analysis": response,
                    "main_themes": [],
                    "overall_insight": response[:500],
                }
                fallback["analysis_result"] = fallback.copy()
                return fallback

        except json.JSONDecodeError:
            return {"success": True, "raw_analysis": response, "parse_error": "JSON解析失败"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ReflectTool(BaseTool):
    """
    反思工具

    使用 LLM 对分析结果进行批判性反思，发现问题和改进方向
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="reflect",
            description="对分析结果进行批判性反思，使用 LLM 发现逻辑问题、潜在偏见和缺失视角。这是确保研究质量的关键步骤。",
            parameters=[
                ToolParameter(
                    name="analysis",
                    type="object",
                    description="分析结果（从 analyze_content 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="depth",
                    type="string",
                    description="反思深度: shallow(浅层), medium(中等), deep(深入)",
                    required=False,
                ),
            ],
            category="reasoning",
            output_schema={
                "reflection_result": {"type": "object", "description": "完整反思结果"},
                "reflection_summary": {"type": "string", "description": "反思总结"},
                "logical_issues": {"type": "array", "description": "逻辑问题"},
                "confidence_assessment": {"type": "object", "description": "可信度评估"},
            },
            # 参数别名：从 state["analysis_result"] 获取 analysis 参数
            param_aliases={
                "analysis": "analysis_result",
            },
        )

    async def execute(
        self,
        analysis: Dict[str, Any],
        depth: str = "medium",
        **kwargs,
    ) -> Dict[str, Any]:
        """使用 LLM 进行批判性反思"""
        try:
            depth_instructions = {
                "shallow": "进行快速的逻辑检查和表面问题发现",
                "medium": "进行中等深度的批判性分析，检查论证逻辑和潜在偏见",
                "deep": "进行深入的批判性反思，包括哲学层面的质疑和多角度审视",
            }

            depth_instruction = depth_instructions.get(
                depth, depth_instructions["medium"])
            analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=2500,
            )

            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                reflection = json.loads(json_match.group())
                reflection["success"] = True
                # 保存完整反思结果供后续工具使用
                reflection["reflection_result"] = {
                    "logical_issues": reflection.get("logical_issues", []),
                    "potential_biases": reflection.get("potential_biases", []),
                    "missing_perspectives": reflection.get("missing_perspectives", []),
                    "confidence_assessment": reflection.get("confidence_assessment", {}),
                    "reflection_summary": reflection.get("reflection_summary", ""),
                }
                return reflection
            else:
                fallback = {"success": True, "raw_reflection": response}
                fallback["reflection_result"] = fallback.copy()
                return fallback

        except json.JSONDecodeError:
            fallback = {"success": True, "raw_reflection": response}
            fallback["reflection_result"] = fallback.copy()
            return fallback
        except Exception as e:
            return {"success": False, "error": str(e)}


class PolishTextTool(BaseTool):
    """
    语言润色工具

    使用 LLM 对文本进行语言润色，提升表达质量
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="polish_text",
            description="对文本进行语言润色，使用 LLM 提升表达的专业性、清晰度和可读性。通常用于润色最终报告。",
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="待润色的文本",
                    required=True,
                ),
                ToolParameter(
                    name="style",
                    type="string",
                    description="目标风格: academic(学术), professional(专业), casual(通俗)",
                    required=False,
                ),
            ],
            category="writing",
            output_schema={
                "polished_text": {"type": "string", "description": "润色后的文本"},
            },
        )

    async def execute(
        self,
        text: str,
        style: str = "professional",
        **kwargs,
    ) -> Dict[str, Any]:
        """使用 LLM 进行语言润色"""
        try:
            if not text:
                return {"success": False, "error": "没有待润色的文本"}

            style_instructions = {
                "academic": "使用学术论文的严谨风格，准确使用专业术语",
                "professional": "使用专业报告的风格，清晰准确，兼顾可读性",
                "casual": "使用通俗易懂的风格，避免过多术语",
            }

            style_instruction = style_instructions.get(
                style, style_instructions["professional"])

            prompt = f"""请对以下文本进行语言润色。

风格要求: {style_instruction}

原文:
{text}

请直接输出润色后的完整文本，保持原有结构，提升表达质量。"""

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=4000,
            )

            return {
                "success": True,
                "polished_text": response.strip(),
                "original_length": len(text),
                "polished_length": len(response),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateReportTool(BaseTool):
    """
    报告生成工具

    使用 LLM 基于分析和反思结果生成研究报告
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_report",
            description="基于分析结果和反思意见，使用 LLM 生成结构化的研究报告。这是研究流程的最终输出步骤。",
            parameters=[
                ToolParameter(
                    name="analysis",
                    type="object",
                    description="内容分析结果",
                    required=True,
                ),
                ToolParameter(
                    name="reflection",
                    type="object",
                    description="反思结果",
                    required=False,
                ),
                ToolParameter(
                    name="topic",
                    type="string",
                    description="研究主题",
                    required=True,
                ),
                ToolParameter(
                    name="format",
                    type="string",
                    description="报告格式: brief(简报), standard(标准), detailed(详细)",
                    required=False,
                ),
            ],
            category="document",
            output_schema={
                "report": {"type": "string", "description": "生成的报告"},
                "word_count": {"type": "integer", "description": "字数"},
            },
            # 参数别名：从 state 获取参数
            param_aliases={
                "analysis": "analysis_result",
                "reflection": "reflection_result",
            },
        )

    async def execute(
        self,
        analysis: Dict[str, Any],
        topic: str,
        reflection: Dict[str, Any] = None,
        format: str = "standard",
        **kwargs,
    ) -> Dict[str, Any]:
        """使用 LLM 生成研究报告"""
        try:
            format_instructions = {
                "brief": "生成简明扼要的研究简报（500-800字）",
                "standard": "生成标准研究报告（1000-1500字）",
                "detailed": "生成详细研究报告（2000字以上）",
            }

            format_instruction = format_instructions.get(
                format, format_instructions["standard"])

            analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)
            reflection_text = json.dumps(
                reflection, ensure_ascii=False, indent=2) if reflection else "无"

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4000,
            )

            return {
                "success": True,
                "report": response,
                "word_count": len(response),
                "format": format,
                "topic": topic,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 示例素材创建 ====================


def create_sample_materials(materials_dir: Path):
    """创建示例研究素材"""
    materials_dir.mkdir(parents=True, exist_ok=True)

    sample1 = materials_dir / "ai_medical_applications.md"
    sample1.write_text("""# 人工智能在医疗领域的应用

## 概述
人工智能（AI）正在深刻改变医疗行业。从疾病诊断到药物研发，AI技术展现出巨大潜力。

## 主要应用领域

### 1. 医学影像分析
深度学习在医学影像分析方面取得了突破性进展。研究表明，AI在某些影像诊断任务中的准确率已经接近甚至超过专业医生。

### 2. 药物研发
AI可以加速药物发现过程，通过分析大量化合物数据预测潜在的药物候选分子。这将研发周期从传统的10-15年缩短到几年。

### 3. 个性化医疗
基于患者的基因信息、病史和生活方式数据，AI可以帮助医生制定个性化的治疗方案。

## 挑战与风险
- 数据隐私和安全问题
- AI决策的可解释性
- 医疗责任归属问题
- 技术应用的伦理边界

## 结论
AI在医疗领域的应用前景广阔，但需要在技术发展和伦理规范之间找到平衡。
""", encoding="utf-8")

    sample2 = materials_dir / "ai_ethics_challenges.md"
    sample2.write_text("""# AI 医疗诊断的伦理挑战

## 引言
随着人工智能在医疗诊断中的应用日益普及，相关的伦理问题也变得更加突出。

## 核心伦理问题

### 1. 算法偏见
如果训练数据存在偏见，AI系统可能对某些群体产生不公平的诊断结果。

### 2. 透明度问题
许多AI模型是"黑箱"系统，医生和患者难以理解其决策过程。

### 3. 责任划分
当AI参与诊断出现错误时，责任应该由谁承担？是AI开发者、医院还是使用AI的医生？

## 建议的解决方案
1. 建立AI医疗应用的伦理审查机制
2. 推动可解释AI技术的发展
3. 制定明确的责任框架和保险机制
4. 加强患者知情同意程序

## 总结
技术进步不能以牺牲伦理为代价，AI医疗应用需要在创新与伦理之间寻找平衡点。
""", encoding="utf-8")

    sample3 = materials_dir / "market_data.txt"
    sample3.write_text("""AI医疗市场数据报告（2024）

市场规模与增长:
- 2024年全球AI医疗市场规模: 约150亿美元
- 预计2030年市场规模: 450亿美元
- 年均复合增长率(CAGR): 约20%

应用领域分布:
1. 医学影像: 35%
2. 药物发现: 25%
3. 临床决策支持: 20%
4. 患者管理: 15%
5. 其他: 5%

主要参与者:
- 科技巨头: Google Health, IBM Watson Health, Microsoft Healthcare
- 专业医疗AI公司: Tempus, PathAI, Butterfly Network
- 传统医疗设备公司: GE Healthcare, Siemens Healthineers

投资趋势:
- 2023年AI医疗领域投资总额: 85亿美元
- 同比增长: 15%
- 主要投资方向: 诊断AI, 药物研发, 手术机器人

地区分布:
- 北美: 45%
- 欧洲: 25%
- 亚太: 25%
- 其他: 5%
""", encoding="utf-8")

    print(f"✅ 已创建示例素材到 {materials_dir}")


# ==================== 结果导出 ====================


async def export_results(
    report: str,
    execution_log: list,
    plan: "ExecutionPlan",
    results: list,
    state: dict,
    output_dir: Path,
    topic: str,
) -> None:
    """
    导出研究结果到 Markdown 和 HTML 文件

    使用项目内置的 ExecutionReportGenerator
    """
    from datetime import datetime
    from auto_agent import ExecutionReportGenerator

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 使用 ExecutionReportGenerator 生成报告数据
    report_data = ExecutionReportGenerator.generate_report_data(
        agent_name="Deep Research Agent",
        query=topic,
        plan=plan,
        results=results,
        state=state,
    )

    # 2. 导出 Markdown 报告（包含执行过程 + 最终研究报告）
    md_filename = output_dir / f"research_report_{timestamp}.md"

    # 生成执行过程报告
    execution_report = ExecutionReportGenerator.generate_markdown_report(
        report_data)

    # 组合完整报告
    md_content = f"""# 研究报告: {topic}

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

{report}

---

# 执行过程报告

{execution_report}
"""

    md_filename.write_text(md_content, encoding="utf-8")
    print(f"\n📄 Markdown 报告已保存: {md_filename}")

    # 3. 导出 HTML 报告
    html_filename = output_dir / f"research_report_{timestamp}.html"

    html_content = generate_html_report(
        topic=topic,
        research_report=report,
        report_data=report_data,
    )

    html_filename.write_text(html_content, encoding="utf-8")
    print(f"🌐 HTML 报告已保存: {html_filename}")

    # 4. 显示统计信息
    stats = report_data.get("statistics", {})
    print(f"\n📊 执行统计:")
    print(f"   - 总步骤: {stats.get('total_steps', 0)}")
    print(f"   - 成功: {stats.get('successful_steps', 0)}")
    print(f"   - 失败: {stats.get('failed_steps', 0)}")
    print(f"   - 成功率: {stats.get('success_rate', 0)}%")

    # 5. 显示 Mermaid 流程图
    print(f"\n📈 执行流程图:")
    print(report_data.get("mermaid_diagram", ""))


def generate_html_report(topic: str, research_report: str, report_data: dict) -> str:
    """生成 HTML 格式报告"""
    from datetime import datetime
    import re

    # 简单的 Markdown 转 HTML
    def md_to_html(md_text: str) -> str:
        html = md_text
        # 标题
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # 加粗
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # 列表项
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        # 段落
        lines = html.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('<'):
                result.append(f'<p>{line}</p>')
            else:
                result.append(line)
        return '\n'.join(result)

    html_report = md_to_html(research_report)
    stats = report_data.get("statistics", {})
    steps = report_data.get("steps", [])

    # 生成步骤详情 HTML
    steps_html = ""
    for step in steps:
        status_class = "success" if step['status'] == 'success' else "error" if step['status'] == 'failed' else "pending"
        status_icon = "✅" if step['status'] == 'success' else "❌" if step['status'] == 'failed' else "⏳"
        error_html = f'<p class="error"><strong>错误:</strong> {step["error"]}</p>' if step.get(
            'error') else ''

        steps_html += f"""
        <div class="step {status_class}">
            <h4>{status_icon} Step {step['step']}: {step['name']}</h4>
            <p><strong>描述:</strong> {step['description']}</p>
            {f"<p><strong>期望:</strong> {step['expectations']}</p>" if step.get('expectations') else ''}
            {error_html}
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>研究报告: {topic}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.8;
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f7fa;
            color: #333;
        }}
        .container {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
        h1 {{ color: #1a202c; border-bottom: 3px solid #4299e1; padding-bottom: 15px; }}
        h2 {{ color: #2d3748; margin-top: 40px; border-left: 4px solid #4299e1; padding-left: 15px; }}
        h3 {{ color: #4a5568; }}
        .meta {{ background: #edf2f7; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: #f7fafc; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #4299e1; }}
        .stat-label {{ color: #718096; font-size: 0.9em; }}
        .step {{ padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #e2e8f0; background: #f7fafc; }}
        .step.success {{ border-left-color: #48bb78; background: #f0fff4; }}
        .step.error {{ border-left-color: #fc8181; background: #fff5f5; }}
        .step.pending {{ border-left-color: #ecc94b; background: #fffff0; }}
        .step h4 {{ margin: 0 0 10px 0; color: #2d3748; }}
        .error {{ color: #c53030; }}
        .success {{ color: #276749; }}
        blockquote {{ border-left: 4px solid #cbd5e0; margin: 20px 0; padding: 15px 20px; background: #f7fafc; }}
        ul, ol {{ padding-left: 25px; }}
        li {{ margin: 8px 0; }}
        hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 30px 0; }}
        .report-content {{ background: #fafafa; padding: 30px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 研究报告: {topic}</h1>
        
        <div class="meta">
            <strong>生成时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            <strong>智能体:</strong> {report_data.get('agent_name', 'Deep Research Agent')}<br>
            <strong>意图:</strong> {report_data.get('intent', 'N/A')}
        </div>
        
        <h2>📊 执行统计</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{stats.get('total_steps', 0)}</div>
                <div class="stat-label">总步骤</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #48bb78;">{stats.get('successful_steps', 0)}</div>
                <div class="stat-label">成功</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #fc8181;">{stats.get('failed_steps', 0)}</div>
                <div class="stat-label">失败</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats.get('success_rate', 0)}%</div>
                <div class="stat-label">成功率</div>
            </div>
        </div>
        
        <h2>📖 研究内容</h2>
        <div class="report-content">
            {html_report}
        </div>
        
        <h2>🔧 执行步骤详情</h2>
        {steps_html}
        
    </div>
</body>
</html>
"""


# ==================== 主程序 ====================


async def main():
    """主函数 - 使用自主规划执行深度研究"""
    print("=" * 70)
    print("🔬 Deep Research Agent - 自主规划版本")
    print("=" * 70)

    # 1. 获取 LLM 客户端
    llm_client = get_llm_client()
    if not llm_client:
        print("\n❌ 未设置 API Key，请设置环境变量:")
        print("   export OPENAI_API_KEY=your-api-key")
        print("   # 或")
        print("   export DEEPSEEK_API_KEY=your-api-key")
        return

    print("\n✅ LLM 客户端初始化成功")

    # 2. 准备素材目录
    script_dir = Path(__file__).parent
    materials_dir = script_dir / "research_materials"

    if not materials_dir.exists() or not any(materials_dir.iterdir()):
        print(f"\n📁 素材目录为空，创建示例素材...")
        create_sample_materials(materials_dir)
    else:
        print(f"\n📁 素材目录: {materials_dir}")

    # 3. 注册工具到 ToolRegistry
    print("\n🔧 注册研究工具...")
    registry = ToolRegistry()

    registry.register(ReadMaterialsTool(llm_client, str(materials_dir)))
    registry.register(AnalyzeContentTool(llm_client))
    registry.register(ReflectTool(llm_client))
    registry.register(PolishTextTool(llm_client))
    registry.register(GenerateReportTool(llm_client))

    print(f"   已注册 {len(registry.get_all_tools())} 个工具:")
    for tool in registry.get_all_tools():
        print(
            f"   - {tool.definition.name}: {tool.definition.description[:50]}...")

    # 4. 创建智能体（带目标和约束）
    print("\n🤖 创建智能体...")
    agent = AutoAgent(
        llm_client=llm_client,
        tool_registry=registry,
        agent_name="Deep Research Agent",
        agent_description="一个能够自主规划和执行深度研究任务的智能体",
        agent_goals=[
            "阅读并理解研究素材",
            "进行深度分析，提取关键信息",
            "批判性反思分析结果",
            "生成高质量的研究报告",
        ],
        agent_constraints=[
            "所有分析必须基于提供的素材",
            "必须进行批判性反思",
            "报告必须经过语言润色",
        ],
    )

    # 5. 用户自然语言描述需求
    user_query = """
    请帮我做一个关于"人工智能在医疗领域的应用与伦理挑战"的深度研究。

    具体要求：
    1. 首先读取研究素材
    2. 分析素材内容，提取关键信息和论点
    3. 对分析结果进行批判性反思，发现可能的问题
    4. 生成一份研究报告
    5. 最后对报告进行语言润色
    
    请自行规划执行步骤，最终给我一份高质量的研究报告。
    """

    print("\n" + "=" * 70)
    print("📋 用户需求:")
    print("=" * 70)
    print(user_query.strip())
    print("\n" + "=" * 70)
    print("🚀 智能体开始自主规划和执行...")
    print("=" * 70)

    # 用于收集执行过程和最终结果
    execution_log = []  # 执行日志
    final_report = ""   # 最终报告
    execution_success = False
    collected_plan = None  # 执行计划
    collected_results = []  # 执行结果
    collected_state = {}  # 最终状态

    # 6. 流式执行（观察规划和执行过程）
    try:
        async for event in agent.run_stream(
            query=user_query,
            user_id="researcher",
        ):
            event_type = event.get("event")
            data = event.get("data", {})

            if event_type == "planning":
                print(f"\n📝 {data.get('message', '规划中...')}")
                execution_log.append(
                    {"event": "planning", "message": data.get('message', '')})

            elif event_type == "execution_plan":
                print("\n" + "-" * 50)
                print("📋 LLM 规划的执行步骤:")
                print("-" * 50)
                steps_info = []
                for step in data.get("steps", []):
                    pinned = "📌" if step.get("is_pinned") else "  "
                    print(
                        f"   {pinned} Step {step['step']}: [{step['name']}] {step['description']}")
                    steps_info.append(step)
                print("-" * 50)
                execution_log.append(
                    {"event": "execution_plan", "steps": steps_info})

                # 保存规划信息用于生成报告
                from auto_agent import ExecutionPlan, PlanStep
                collected_plan = ExecutionPlan(
                    intent=data.get("description", "深度研究"),
                    subtasks=[
                        PlanStep(
                            id=str(s.get("step", i+1)),
                            tool=s.get("name"),
                            description=s.get("description", ""),
                            expectations=s.get("expectations"),
                        )
                        for i, s in enumerate(steps_info)
                    ]
                )

            elif event_type == "stage_start":
                step = data.get("step", "?")
                name = data.get("name", "unknown")
                desc = data.get("description", "")
                print(f"\n▶️  Step {step}: {name}")
                print(f"   📝 描述: {desc}")

            elif event_type == "stage_complete":
                step = data.get("step", "?")
                name = data.get("name", "unknown")
                success = data.get("success", False)
                result = data.get("result", {}) or {}
                error = data.get("error")  # 获取错误信息
                status = "✅ 成功" if success else "❌ 失败"

                print(f"\n   {status}")
                print(f"   " + "-" * 40)

                # 显示错误原因（如果失败）
                if not success:
                    # 尝试从多个地方获取错误信息
                    error_msg = error
                    if not error_msg and isinstance(result, dict):
                        error_msg = result.get("error")
                    if not error_msg:
                        error_msg = str(result) if result else "未知错误 - 无返回结果"
                    print(f"   ❗ 失败原因: {error_msg}")
                    print(f"   " + "-" * 40)
                    continue

                # 详细展示输出
                if isinstance(result, dict):
                    print(f"   📤 输出:")

                    # 根据不同工具显示不同的输出内容
                    if "total_files" in result:
                        print(f"      - 文件数量: {result['total_files']}")
                        print(
                            f"      - 总字数: {result.get('total_words', 'N/A')}")
                        materials = result.get('materials', [])
                        for m in materials[:5]:
                            print(
                                f"      - 📄 {m.get('filename', 'unknown')}: {m.get('summary', 'N/A')[:80]}...")

                    if "main_themes" in result:
                        themes = result.get("main_themes", [])
                        print(f"      - 主题: {themes}")
                        args = result.get("key_arguments", [])
                        if args:
                            print(f"      - 核心论点数: {len(args)}")
                            for arg in args[:3]:
                                if isinstance(arg, dict):
                                    print(
                                        f"        • {arg.get('argument', 'N/A')[:60]}...")
                        insight = result.get("overall_insight", "")
                        if insight:
                            print(f"      - 整体洞察: {insight[:150]}...")

                    if "reflection_summary" in result:
                        summary = result.get("reflection_summary", "")
                        print(f"      - 反思总结: {summary[:200]}...")
                        issues = result.get("logical_issues", [])
                        if issues:
                            print(f"      - 发现问题数: {len(issues)}")
                        conf = result.get("confidence_assessment", {})
                        if conf:
                            print(
                                f"      - 可信度评分: {conf.get('overall_score', 'N/A')}")

                    if "report" in result:
                        report = result.get("report", "")
                        print(
                            f"      - 报告字数: {result.get('word_count', len(report))}")
                        print(f"      - 报告预览: {report[:200]}...")
                        # 保存报告内容
                        if success and report:
                            final_report = report

                    if "polished_text" in result:
                        polished = result.get("polished_text", "")
                        print(
                            f"      - 润色后字数: {result.get('polished_length', len(polished))}")
                        print(f"      - 润色预览: {polished[:200]}...")
                        # 更新为润色后的报告
                        if success and polished:
                            final_report = polished

                print(f"   " + "-" * 40)

                # 记录到执行日志
                execution_log.append({
                    "event": "step_complete",
                    "step": step,
                    "name": name,
                    "success": success,
                    "result": result,
                })

                # 收集执行结果用于报告生成
                from auto_agent import SubTaskResult
                collected_results.append(SubTaskResult(
                    step_id=str(step),
                    success=success,
                    output=result,
                    error=result.get("error") if isinstance(
                        result, dict) else None,
                ))

            elif event_type == "stage_retry":
                reason = data.get('message', '重试中...')
                print(f"\n   🔄 重试: {reason}")
                execution_log.append(
                    {"event": "retry", "step": data.get('step'), "reason": reason})

            elif event_type == "stage_replan":
                reason = data.get('reason', '')
                print(f"\n⚠️  触发重规划")
                print(f"   原因: {reason}")
                execution_log.append({"event": "replan", "reason": reason})

            elif event_type == "answer":
                print("\n" + "=" * 70)
                print("📄 最终研究报告:")
                print("=" * 70)
                answer = data.get("answer", "")
                if answer:
                    final_report = answer
                print(answer)

            elif event_type == "done":
                print("\n" + "=" * 70)
                execution_success = data.get("success", False)
                iterations = data.get("iterations", 0)
                if execution_success:
                    print(f"✅ 研究完成! (执行了 {iterations} 步)")
                else:
                    print(f"❌ 执行失败: {data.get('message', '')}")
                print("=" * 70)

            elif event_type == "error":
                print(f"\n❌ 错误: {data.get('message', '')}")
                if data.get("errors"):
                    for err in data["errors"]:
                        print(f"   - {err}")
                execution_log.append({"event": "error", "message": data.get(
                    'message', ''), "errors": data.get('errors', [])})

        # 7. 导出结果
        if final_report and collected_plan:
            await export_results(
                report=final_report,
                execution_log=execution_log,
                plan=collected_plan,
                results=collected_results,
                state={
                    "final_report": final_report[:500] + "..." if len(final_report) > 500 else final_report},
                output_dir=script_dir / "output",
                topic="人工智能在医疗领域的应用与伦理挑战",
            )

    except Exception as e:
        print(f"\n❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
