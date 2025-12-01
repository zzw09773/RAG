# rag_system/state.py
```python
"""GraphState definition for legal document RAG workflow."""
from typing import Annotated
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages


class GraphState(MessagesState):
    """State structure for the legal document RAG workflow.

    Extends MessagesState to maintain message history across the graph
    while tracking legal document retrieval and generation state.

    Attributes:
        messages: Chat message history (inherited from MessagesState)
        question: The user's original question
        generation: The final generated answer with legal citations
        collection: Optional target collection name for legal documents
        retrieved_docs: Documents retrieved from the vector database
    """
    question: str = ""
    generation: str = ""
    collection: str = ""
    retrieved_docs: list = []
```
