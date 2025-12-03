"""Programmatic workflow helpers for the legal RAG system.

This module exposes factory functions so notebooks and other orchestration
layers can instantiate the LangGraph workflow without relying on the CLI.
"""
from __future__ import annotations

from typing import List, Optional

import httpx
from langchain_openai import ChatOpenAI

from .agent import build_workflow
from .config import RAGConfig
from .node import create_agent_node
from .tool.rag_tool import create_rag_tool
from .common import log


def create_llm(config: RAGConfig) -> ChatOpenAI:
    """Instantiate ChatOpenAI client based on the provided configuration."""
    api_base = config.llm_api_base or config.embed_api_base
    if not api_base:
        raise ValueError("LLM API base is not configured")

    client = httpx.Client(
        verify=config.verify_ssl,
        follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )

    return ChatOpenAI(
        model=config.chat_model,
        openai_api_key=config.embed_api_key,
        openai_api_base=api_base,
        temperature=config.temperature,
        http_client=client,
    )


def _build_tools(
    llm: ChatOpenAI,
    config: RAGConfig,
) -> List[callable]:
    """Create the set of LangChain tools used by the agent."""
    # Refactored to use only the unified RAG tool
    rag_tool = create_rag_tool(config)
    
    return [rag_tool]


def create_rag_workflow(
    config: RAGConfig,
    *,
    llm: Optional[ChatOpenAI] = None,
    use_hierarchical: bool = True, # Kept for compatibility signature, but unused
):
    """Create and compile the LangGraph workflow for notebooks or services."""
    config.validate()

    if llm is None:
        llm = create_llm(config)

    tools = _build_tools(llm, config)
    general_agent_node = create_agent_node(llm, tools)
    return build_workflow(general_agent_node)


def run_query(
    question: str,
    config: RAGConfig,
    *,
    llm: Optional[ChatOpenAI] = None,
    messages: Optional[list] = None,
    use_hierarchical: bool = True, # Kept for compatibility signature, but unused
):
    """Execute a single query through the workflow and return the state."""
    workflow = create_rag_workflow(
        config,
        llm=llm,
        use_hierarchical=use_hierarchical,
    )

    initial_messages = messages or [("user", question)]
    state = {
        "question": question,
        "generation": "",
        "messages": initial_messages,
        "collection": "",
        "retrieved_docs": [],
    }

    log(f"Running workflow for question: {question}")
    return workflow.invoke(state, config={"recursion_limit": 50})


__all__ = [
    "create_llm",
    "create_rag_workflow",
    "run_query",
]