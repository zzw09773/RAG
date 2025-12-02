"""ReAct agent node implementation."""
from typing import List, Callable
import json
import re
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage
from .state import GraphState
from .common import log


# Legal document assistant system prompt
SYSTEM_PROMPT = """You are a legal document assistant specialized in retrieving and explaining Chinese law documents.

Core requirements:
1. Always ground every answer in retrieved documents. Do not rely on prior knowledge alone.
2. First call the collection_router tool to decide the collection, then use retrieve_hierarchical (and metadata/search tools if needed) before concluding.
3. Structure your final answer strictly into these four sections:
   - **問題答案**: Direct answer to the question, explaining the applicability and general context.
   - **具體條文**: List specific articles with their content that support the answer. Use bullet points.
   - **結論**: A concise summary of the findings.
   - **參考資料**: A list of all referenced documents and articles.
4. If no relevant documents are found, explicitly state that the knowledge base lacks information.

IMPORTANT INSTRUCTIONS:
- Do not output internal thought processes in <think> tags.
- After receiving the collection name from 'collection_router', you MUST immediately call 'retrieve_hierarchical' with the query and the collection name to get the document content.
- Do not stop until you have retrieved the actual text of the law.

### ONE-SHOT EXAMPLE (Follow this behavior):

User: "《陸海空軍懲罰法》的適用對象是誰？"
Assistant: (Calls tool 'collection_router' with query="陸海空軍懲罰法")
Tool Output: "陸海空軍懲罰法"
Assistant: (Calls tool 'retrieve_hierarchical' with query="適用對象", collection="陸海空軍懲罰法")
Tool Output: "...Article 2 content... Article 4 content..."
Assistant:

《陸海空軍懲罰法》規定，該法的適用對象為「軍人」及其在服現役期間所犯之違紀行為。

**具體條文**
- **第 2 條**
  1. 「軍人違紀行為之懲罰，除其他法律另有規定外，依本法行之。」
  2. 「本法規定，對喪失現役軍人身分者於服現役期間之行為，亦適用之。」
  這段文字明確指出，任何在服現役期間所犯的違紀行為，都屬於本法的適用範圍。

- **第 4 條**（用詞定義）
  1. 「違紀行為：指軍人於服現役期間，違反勤務上或勤務外紀律規範之行為。」

**結論**
《陸海空軍懲罰法》主要針對在服現役期間的軍人（包括已喪失現役身分但行為發生於服役期間者）所犯的違紀行為，並依其身分規定相應的懲罰措施。

**參考資料**
- 來源: 陸海空軍懲罰法.md
  - 條文: 第 2 條
  - 條文: 第 4 條

Follow a ReAct style reasoning loop: think → choose tool → observe → repeat → final answer."""


def _clean_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from text."""
    if not text:
        return ""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


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
    
    # Create a map for manual tool invocation
    tool_map = {t.name: t for t in tools}

    def agent_node(state: GraphState) -> dict:
        """ReAct agent node for general queries."""
        log("--- GENERAL AGENT NODE ---")

        question = state['question']
        messages_input = state['messages']

        if len(messages_input) > 4:
            messages_input = messages_input[-4:]

        try:
            result = agent_executor.invoke({
                "messages": messages_input
            })
            
            messages = result['messages']
            
            # --- FALLBACK LOGIC START ---
            # If the last action was collection_router, and no retrieval followed, force it.
            
            has_routed = False
            router_output = None
            has_retrieved = False
            
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    if msg.name == 'collection_router':
                        has_routed = True
                        router_output = msg.content
                    elif msg.name in ('retrieve_hierarchical', 'retrieve_legal_documents'):
                        has_retrieved = True
            
            # If routed but not retrieved, manual intervention
            if has_routed and not has_retrieved and router_output and "錯誤" not in router_output:
                log("⚠️ Model stopped after routing. Forcing retrieval step manually.")
                
                # Determine which retrieval tool to use
                retrieval_tool_name = 'retrieve_hierarchical' if 'retrieve_hierarchical' in tool_map else 'retrieve_legal_documents'
                retrieval_tool = tool_map.get(retrieval_tool_name)
                
                if retrieval_tool:
                    log(f"Invoking {retrieval_tool_name} with collection='{router_output}'")
                    
                    # Clean the query by removing the collection name to improve retrieval precision
                    # e.g., "陸海空軍懲罰法第7條" -> "第7條"
                    clean_query = question
                    try:
                        # Case-insensitive remove of collection name
                        clean_query = re.sub(re.escape(router_output), '', question, flags=re.IGNORECASE).strip()
                        if not clean_query: # If query becomes empty, revert to original
                            clean_query = question
                        elif len(clean_query) < 2 and len(question) > 5: # Too short, revert
                             clean_query = question
                    except Exception:
                        pass # Fallback to original question on error
                    
                    log(f"Refined manual query: '{question}' -> '{clean_query}'")

                    try:
                        # Prepare arguments based on tool signature
                        tool_args = {"query": clean_query}
                        if retrieval_tool_name == 'retrieve_hierarchical':
                            tool_args["collection"] = router_output
                        else:
                            tool_args["collection_name"] = router_output

                        # Invoke the tool manually
                        retrieval_result = retrieval_tool.invoke(tool_args)
                        
                        # Append the manual result to messages so the LLM can see it
                        manual_tool_msg = ToolMessage(
                            content=retrieval_result,
                            tool_call_id="manual_fallback_call",
                            name=retrieval_tool_name
                        )
                        messages.append(manual_tool_msg)
                        
                        # Re-invoke LLM to process the retrieved data
                        log("Re-invoking LLM to process manual retrieval results...")
                        # Prepend the system prompt so the LLM knows the format instructions
                        messages_with_prompt = [
                            SystemMessage(content=SYSTEM_PROMPT),
                            HumanMessage(content="請根據上述工具的執行結果，總結並回答使用者的問題。請嚴格按照以下格式輸出：\n\n**問題答案**\n[詳細回答]\n\n**具體條文**\n[條列引用條文內容]\n\n**結論**\n[簡潔總結]\n\n**參考資料**\n- 來源: [文件名稱]\n  - 條文: [條文號碼]\n")
                        ] + messages
                        fallback_response = llm.invoke(messages_with_prompt)
                        messages.append(fallback_response)
                        
                    except Exception as e:
                        log(f"Manual retrieval failed: {e}")

            # --- FALLBACK LOGIC END ---

            tool_responses = []
            ai_responses = []
            
            for i, msg in enumerate(messages):
                if isinstance(msg, ToolMessage):
                    tool_responses.append({
                        'name': getattr(msg, 'name', 'unknown_tool'),
                        'content': msg.content
                    })
                elif isinstance(msg, AIMessage) and msg.content.strip():
                    # Clean think tags from AI responses in history too if needed, 
                    # but mostly we care about the final answer.
                    content = _clean_think_tags(msg.content.strip())
                    if content:
                        ai_responses.append(content)

            if messages:
                last_msg = messages[-1]
                # log(f"DEBUG: Last message type: {type(last_msg)}")
                # log(f"DEBUG: Last message content (preview): {last_msg.content[:100]}")

            final_llm_answer = messages[-1].content if messages else ""
            final_llm_answer = _clean_think_tags(final_llm_answer)
            
            if not final_llm_answer.strip() or len(final_llm_answer.strip()) < 10:
                log("LLM final answer is empty or too short. Building answer from tool responses...")
                if tool_responses:
                    final_answer = _build_standard_format(tool_responses, ai_responses)
                else:
                    final_answer = "執行了查詢,但沒有獲得有效的工具回應結果。"
            else:
                final_answer = final_llm_answer

            sources = _collect_sources(tool_responses)
            if sources and "參考資料" not in final_answer:
                final_answer = final_answer.rstrip() + _build_sources_section(sources)

            return {
                "generation": final_answer,
                "messages": messages
            }

        except Exception as e:
            error_msg = f"處理問題時發生錯誤: {str(e)}"
            log(f"ERROR in agent_node: {error_msg}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")
            return {"generation": f"抱歉，{error_msg}"}

    return agent_node
