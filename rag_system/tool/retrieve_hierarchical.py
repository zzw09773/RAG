"""Hierarchical retrieval tool for LangGraph agent.

This tool integrates the hierarchical RAG system with the existing ReAct agent.
"""
from typing import Optional
from langchain.tools import tool

from ..application import HierarchicalRetrievalUseCase
from ..application.indexing import EmbeddingService
from ..infrastructure import HierarchicalDocumentRepository, VectorStoreRepository
from ..domain import DocumentId
from ..common import LocalApiEmbeddings, log


def create_hierarchical_retrieve_tool(
    conn_str: str,
    embed_api_base: str,
    embed_api_key: str,
    embed_model: str = "nvidia/nv-embed-v2",
    verify_ssl: bool = True,
    top_k: int = 5,
    content_max_length: int = 800,
    strategy: str = "summary_first",
    embedding_dimension: int = 1024
):
    """Create a hierarchical retrieval tool for the agent.

    Args:
        conn_str: PostgreSQL connection string
        embed_api_base: Embedding API base URL
        embed_api_key: API key
        embed_model: Embedding model name
        verify_ssl: Whether to verify SSL
        top_k: Number of results to return
        content_max_length: Maximum content length
        strategy: Retrieval strategy ("summary_first" or "direct")
        embedding_dimension: Dimension of embedding vectors

    Returns:
        LangChain tool for hierarchical retrieval
    """
    # Initialize repositories
    doc_repository = HierarchicalDocumentRepository(conn_str)
    vector_repository = VectorStoreRepository(conn_str, embedding_dimension)

    # Initialize embedding service
    embedding_model = LocalApiEmbeddings(
        api_base=embed_api_base,
        api_key=embed_api_key,
        model_name=embed_model,
        verify_ssl=verify_ssl
    )
    embedding_service = EmbeddingService(embedding_model)

    # Initialize use case
    retrieval_use_case = HierarchicalRetrievalUseCase(
        doc_repository=doc_repository,
        vector_repository=vector_repository,
        embedding_service=embedding_service,
        default_strategy=strategy
    )

    @tool
    def retrieve_hierarchical(
        query: str,
        collection: Optional[str] = None
    ) -> str:
        """Retrieve relevant legal document chunks using hierarchical search.

        This tool uses a two-phase retrieval strategy:
        1. Search high-level summaries (chapters, articles)
        2. Expand to detailed chunks within relevant sections

        This provides better context and reduces token consumption by 30-50%.

        Args:
            query: The search query describing what legal information you need
            collection: Optional collection name (document) to search within.
                       If not specified, searches across all documents.

        Returns:
            A formatted string containing relevant legal document excerpts with
            hierarchical context (parent sections, current chunk, child details).

        Example:
            retrieve_hierarchical(
                query="航空器設計的罰則規定",
                collection="民用航空法"
            )
        """
        try:
            log(f"Hierarchical retrieval: query='{query}', collection='{collection}'")

            # Convert collection name to document_id if provided
            document_id = DocumentId(value=collection) if collection else None

            # Execute retrieval
            results = retrieval_use_case.execute(
                query=query,
                k=top_k,
                document_id=document_id,
                strategy=strategy,
                content_max_length=content_max_length
            )

            if not results:
                return f"找不到與「{query}」相關的法律文件。"

            # Format results
            formatted_output = []
            for i, result in enumerate(results, 1):
                metadata = result["metadata"]
                content = result["content"]

                # Build source citation
                source_parts = []
                if metadata.get("article"):
                    source_parts.append(metadata["article"])
                if metadata.get("section_path"):
                    source_parts.append(f"({metadata['section_path']})")
                source = " ".join(source_parts) if source_parts else metadata.get("source", "")

                # Format entry
                entry = f"【檢索結果 {i}】 {source}\n"

                # Add hierarchical context indicator
                if metadata.get("has_parents"):
                    entry += f"  [包含 {metadata['parent_count']} 層上層內容]\n"
                if metadata.get("has_children"):
                    entry += f"  [包含 {metadata['child_count']} 個子項目]\n"

                entry += f"\n{content}\n"

                # Add similarity score if significant
                if metadata.get("similarity_score", 0) > 0.1:
                    entry += f"\n  [相關度: {metadata['similarity_score']:.2f}]\n"

                formatted_output.append(entry)

            return "\n" + "="*60 + "\n".join(formatted_output)

        except Exception as e:
            log(f"Error in hierarchical retrieval: {e}")
            return f"檢索時發生錯誤: {str(e)}"

    # Set tool metadata
    retrieve_hierarchical.name = "retrieve_hierarchical"
    retrieve_hierarchical.description = (
        "Retrieve relevant legal document chunks using hierarchical two-phase search. "
        "Searches summaries first, then expands to details for better context and "
        "reduced token consumption. Use this for legal document queries."
    )

    return retrieve_hierarchical


def create_hybrid_retrieve_tool(
    conn_str: str,
    embed_api_base: str,
    embed_api_key: str,
    embed_model: str = "nvidia/nv-embed-v2",
    verify_ssl: bool = True,
    top_k: int = 5,
    content_max_length: int = 800,
    embedding_dimension: int = 1024,
    use_hierarchical: bool = True
):
    """Create a hybrid tool that can use both old and new retrieval systems.

    This allows gradual migration and A/B testing.

    Args:
        conn_str: PostgreSQL connection string
        embed_api_base: Embedding API base URL
        embed_api_key: API key
        embed_model: Embedding model name
        verify_ssl: Whether to verify SSL
        top_k: Number of results
        content_max_length: Max content length
        embedding_dimension: Embedding dimension
        use_hierarchical: Whether to use hierarchical retrieval

    Returns:
        Retrieval tool (hierarchical or legacy based on flag)
    """
    if use_hierarchical:
        log("Using hierarchical retrieval system")
        return create_hierarchical_retrieve_tool(
            conn_str=conn_str,
            embed_api_base=embed_api_base,
            embed_api_key=embed_api_key,
            embed_model=embed_model,
            verify_ssl=verify_ssl,
            top_k=top_k,
            content_max_length=content_max_length,
            strategy="summary_first",
            embedding_dimension=embedding_dimension
        )
    else:
        log("Using legacy flat retrieval system")
        # Import existing retrieve tool
        from .retrieve import create_retrieve_tool
        return create_retrieve_tool(
            conn_str=conn_str,
            embed_api_base=embed_api_base,
            embed_api_key=embed_api_key,
            embed_model=embed_model,
            verify_ssl=verify_ssl,
            top_k=top_k,
            content_max_length=content_max_length
        )
