"""ReAct agent node implementation."""
from typing import List, Callable
import json
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from .state import GraphState
from .common import log


# Legal document assistant system prompt
SYSTEM_PROMPT = """You are a legal document assistant specialized in retrieving and explaining Chinese law documents.

Core requirements:
1. Always ground every answer in retrieved documents. Do not rely on prior knowledge alone.
2. First call the collection_router tool to decide the collection, then use retrieve_legal_documents (and metadata/search tools if needed) before concluding.
3. When you answer, clearly reference the supporting evidence. The answer must include a '參考資料' section listing every document via lines formatted as '來源: <檔名>…'.
4. If no relevant documents are found, explicitly state that the knowledge base lacks information instead of fabricating details.

Follow a ReAct style reasoning loop: think → choose tool → observe → repeat → final answer."""


def _build_standard_format(tool_responses, ai_responses):
    """Build standard formatted output for tool responses."""
    answer_parts = ["# 🎯 查詢結果\n"]
    answer_parts.append("根據您的查詢,以下是各工具執行結果:\n")
    
    for idx, tr in enumerate(tool_responses, 1):
        tool_name = tr['name']
        tool_content = tr['content']
        
        answer_parts.append(f"\n## {idx}. 【{tool_name}】\n")
        
        try:
            data = json.loads(tool_content)
            if isinstance(data, dict):
                if 'error' in data:
                    answer_parts.append(f"⚠️ 錯誤: {data['error']}\n")
                else:
                    for key, value in data.items():
                        if key.startswith('_'):
                            continue
                        if isinstance(value, dict):
                            answer_parts.append(f"\n**{key}**:\n")
                            for k, v in value.items():
                                answer_parts.append(f"  - {k}: {v}\n")
                        elif isinstance(value, list):
                            answer_parts.append(f"**{key}**: {value}\n")
                        else:
                            answer_parts.append(f"**{key}** = {value}\n")
            else:
                answer_parts.append(str(data))
        except json.JSONDecodeError:
            answer_parts.append(tool_content)
        
        answer_parts.append("\n---\n")
    
    if ai_responses:
        answer_parts.append("\n## 💡 補充說明:\n")
        for ai_resp in ai_responses:
            answer_parts.append(ai_resp + "\n")
    
    answer_parts.append(f"\n✅ 共執行了 {len(tool_responses)} 個工具,完成查詢。\n")
    
    return "".join(answer_parts)


def _extract_sources_from_text(text: str) -> List[str]:
    """Extract source entries from tool output text."""
    if not isinstance(text, str):
        return []

    sources: List[str] = []
    lines = text.splitlines()

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line.startswith("來源:"):
            continue

        entry = line.split("來源:", 1)[1].strip()

        # Attach metadata information if present on the next line
        if idx + 1 < len(lines):
            next_line = lines[idx + 1].strip()
            if next_line.startswith("Metadata:"):
                metadata = next_line.split("Metadata:", 1)[1].strip()
                if metadata:
                    entry = f"{entry} ({metadata})"

        if entry and entry not in sources:
            sources.append(entry)

    return sources


def _collect_sources(tool_responses: List[dict]) -> List[str]:
    """Collect unique source entries from all tool responses."""
    collected: List[str] = []
    seen = set()

    for tr in tool_responses:
        entries = _extract_sources_from_text(tr.get('content', ""))
        for entry in entries:
            if entry not in seen:
                seen.add(entry)
                collected.append(entry)

    return collected


def _build_sources_section(source_entries: List[str]) -> str:
    """Build the citation section appended to final answers."""
    if not source_entries:
        return ""

    bullets = "\n".join(f"- 來源: {entry}" for entry in source_entries)
    return f"\n\n參考資料:\n{bullets}"


def create_agent_node(llm: ChatOpenAI, tools: List[Callable]) -> Callable:
    """Create a ReAct agent node for the workflow."""
    agent_executor = create_react_agent(
        llm,
        tools,
        prompt=SYSTEM_PROMPT
    )

    def agent_node(state: GraphState) -> dict:
        """ReAct agent node for general queries."""
        log("--- GENERAL AGENT NODE ---")

        question = state['question']
        # The router ensures the message history is initialized
        messages_input = state['messages']

        # Truncate message history to keep context size under control
        if len(messages_input) > 4:
            log(f"Message history has {len(messages_input)} messages. Truncating to the last 4.")
            messages_input = messages_input[-4:]

        try:
            result = agent_executor.invoke({
                "messages": messages_input
            })

            tool_responses = []
            ai_responses = []
            
            for i, msg in enumerate(result['messages']):
                if type(msg).__name__ == 'ToolMessage':
                    tool_responses.append({
                        'name': getattr(msg, 'name', 'unknown_tool'),
                        'content': msg.content
                    })
                elif type(msg).__name__ == 'AIMessage' and msg.content.strip():
                    ai_responses.append(msg.content.strip())

            final_llm_answer = result['messages'][-1].content if result['messages'] else ""
            
            if not final_llm_answer.strip() or len(final_llm_answer.strip()) < 10:
                log("LLM final answer is empty or too short. Building answer from tool responses...")
                if tool_responses:
                    final_answer = _build_standard_format(tool_responses, ai_responses)
                else:
                    final_answer = "執行了查詢,但沒有獲得有效的工具回應結果。"
            else:
                final_answer = final_llm_answer

            sources = _collect_sources(tool_responses)
            if sources:
                final_answer = final_answer.rstrip() + _build_sources_section(sources)

            return {
                "generation": final_answer,
                "messages": result['messages']
            }

        except Exception as e:
            error_msg = f"處理問題時發生錯誤: {str(e)}"
            log(f"ERROR in agent_node: {error_msg}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")
            return {"generation": f"抱歉，{error_msg}"}

    return agent_node
