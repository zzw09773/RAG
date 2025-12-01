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
from .tool import (
    create_article_lookup_tool,
    create_metadata_search_tool,
    create_retrieve_tool,
    create_router_tool,
)
from .tool.retrieve_hierarchical import create_hybrid_retrieve_tool
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
    *,
    use_hierarchical: bool = False,
) -> List[callable]:
    """Create the set of LangChain tools used by the agent."""
    router_tool = create_router_tool(llm, config.conn_string)

    if use_hierarchical:
        retrieval_tool = create_hybrid_retrieve_tool(
            conn_str=config.conn_string,
            embed_api_base=config.embed_api_base,
            embed_api_key=config.embed_api_key,
            embed_model=config.embed_model,
            verify_ssl=config.verify_ssl,
            top_k=config.top_k,
            content_max_length=config.content_max_length,
            use_hierarchical=True,
        )
    else:
        retrieval_tool = create_retrieve_tool(
            conn_str=config.conn_string,
            embed_api_base=config.embed_api_base,
            embed_api_key=config.embed_api_key,
            embed_model=config.embed_model,
            verify_ssl=config.verify_ssl,
            top_k=config.top_k,
            content_max_length=config.content_max_length,
        )

    metadata_tool = create_metadata_search_tool(conn_str=config.conn_string)
    article_lookup_tool = create_article_lookup_tool(conn_str=config.conn_string)

    return [
        router_tool,
        retrieval_tool,
        metadata_tool,
        article_lookup_tool,
    ]


def create_rag_workflow(
    config: RAGConfig,
    *,
    llm: Optional[ChatOpenAI] = None,
    use_hierarchical: bool = True,
):
    """Create and compile the LangGraph workflow for notebooks or services."""
    config.validate()

    if llm is None:
        llm = create_llm(config)

    tools = _build_tools(llm, config, use_hierarchical=use_hierarchical)
    general_agent_node = create_agent_node(llm, tools)
    return build_workflow(general_agent_node)


def run_query(
    question: str,
    config: RAGConfig,
    *,
    llm: Optional[ChatOpenAI] = None,
    messages: Optional[list] = None,
    use_hierarchical: bool = True,
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
