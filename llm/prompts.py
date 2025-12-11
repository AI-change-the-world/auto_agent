"""
提示词模板
"""

PLANNING_PROMPT = """You are an intelligent task planner. Given a user query, you need to:
1. Understand the user's intent
2. Break down the task into subtasks
3. Select appropriate tools for each subtask
4. Generate an execution plan

User Query: {query}

Available Tools:
{tool_descriptions}

User Context (Long-term Memory):
{user_context}

Conversation Context (Short-term Memory):
{conversation_context}

Please generate a detailed execution plan in JSON format:
{{
  "intent": "...",
  "subtasks": [
    {{
      "id": "1",
      "description": "...",
      "tool": "tool_name",
      "parameters": {{}},
      "dependencies": []
    }}
  ],
  "expected_outcome": "..."
}}
"""

ERROR_ANALYSIS_PROMPT = """An error occurred during task execution. Please analyze the error and provide suggestions.

Error Type: {error_type}
Error Message: {error_message}
Stack Trace: {stack_trace}

Task Context:
- Task: {task_description}
- Tool: {tool_name}
- Parameters: {parameters}
- Attempt: {attempt}/{max_retries}

Execution History:
{execution_history}

Please analyze:
1. Is this error recoverable?
2. What might be the root cause?
3. Should we retry? If yes, any parameter adjustments needed?
4. Alternative approaches?

Respond in JSON format:
{{
  "is_recoverable": true/false,
  "root_cause": "...",
  "should_retry": true/false,
  "suggested_changes": {{
    "parameters": {{}},
    "alternative_tool": "..."
  }},
  "reasoning": "..."
}}
"""
