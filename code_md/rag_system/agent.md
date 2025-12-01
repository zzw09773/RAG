# rag_system/agent.py
```python
"""LangGraph workflow orchestration for legal document RAG agent."""
from typing import Callable
from langgraph.graph import END, StateGraph
from .state import GraphState


def build_workflow(general_agent_node: Callable) -> StateGraph:
    """Build the LangGraph workflow for legal document RAG.

    Creates a simple linear workflow:
    - Entry point -> general_agent_node -> END

    The general agent handles all queries using ReAct pattern with
    tools for document retrieval, metadata search, and calculations.

    Args:
        general_agent_node: The ReAct agent node for processing all queries

    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(GraphState)
    workflow.add_node("general_agent", general_agent_node)
    workflow.set_entry_point("general_agent")
    workflow.add_edge("general_agent", END)
    return workflow.compile()
```
