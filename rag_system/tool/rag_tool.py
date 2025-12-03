from typing import Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from ..rag_service import RAGService
from ..config import RAGConfig

class RetrieveInput(BaseModel):
    query: str = Field(description="The query string to search for in the legal document database.")

class RAGRetrieveTool(BaseTool):
    name: str = "retrieve_legal_docs"
    description: str = (
        "Retrieve relevant legal documents and context based on the user's query. "
        "Use this tool when you need to find laws, regulations, or legal context."
    )
    args_schema: Type[BaseModel] = RetrieveInput
    rag_service: RAGService

    def _run(self, query: str) -> str:
        docs = self.rag_service.query(query)
        if not docs:
            return "No relevant documents found."
        
        # Format docs for the LLM
        result = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Unknown")
            result.append(f"[{i}] Source: {source}\nContent: {doc.page_content}\n")
            
        return "\n".join(result)

def create_rag_tool(config: RAGConfig) -> RAGRetrieveTool:
    service = RAGService(config)
    return RAGRetrieveTool(rag_service=service)

