"""ReAct agent node implementation."""
from typing import List, Callable
import re
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from .state import GraphState
from .common import log


# Legal document assistant system prompt
SYSTEM_PROMPT = """You are a legal document assistant specialized in retrieving and explaining Chinese law documents.

Core requirements:
1. Always ground every answer in retrieved documents. Do not rely on prior knowledge alone.
2. Use the 'retrieve_legal_docs' tool to find relevant laws and context.
3. Structure your final answer strictly into these sections:
   - **問題答案**: Direct answer to the question, explaining the applicability and general context.
   - **具體條文**: List specific articles with their content that support the answer. Use bullet points.
   - **結論**: A concise summary of the findings.
   - **參考資料**: A list of all referenced documents and articles.
4. If no relevant documents are found, explicitly state that the knowledge base lacks information.
"""

def create_agent_node(llm: ChatOpenAI, tools: List[Callable]) -> Callable:
    """Create a ReAct agent node for the workflow."""
    # Removing specific prompt parameters to ensure compatibility across LangGraph versions.
    # We will inject the system prompt manually in the input messages.
    agent_executor = create_react_agent(
        llm,
        tools
    )
    
    def agent_node(state: GraphState) -> dict:
        """ReAct agent node for general queries."""
        log("--- GENERAL AGENT NODE ---")

        # Truncate history to prevent overflow
        messages_input = state['messages']
        if len(messages_input) > 10:
            messages_input = messages_input[-10:]
            
        # Prepend System Prompt
        messages_with_prompt = [SystemMessage(content=SYSTEM_PROMPT)] + messages_input

        try:
            result = agent_executor.invoke({
                "messages": messages_with_prompt
            })
            
            messages = result['messages']
            final_answer = ""
            
            # Extract the final answer from the last AI message
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, AIMessage):
                    final_answer = last_msg.content

            return {
                "generation": final_answer,
                "messages": messages
            }

        except Exception as e:
            error_msg = f"處理問題時發生錯誤: {str(e)}"
            log(f"ERROR in agent_node: {error_msg}")
            return {"generation": f"抱歉，{error_msg}"}

    return agent_node