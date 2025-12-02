import time
import uuid
from typing import List, Optional, Dict, Any, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

from rag_system.config import RAGConfig
from rag_system.workflow import run_query

# Initialize FastAPI app
app = FastAPI(title="RAG Agent API", description="OpenAI-compatible API for Agentic RAG")

# Load Config globally to avoid reloading on every request
load_dotenv()
try:
    config = RAGConfig.from_env()
    config.validate()
    print("RAG Configuration loaded successfully.")
except Exception as e:
    print(f"Warning: Configuration load failed: {e}. Ensure .env is set.")
    config = None # Handle gracefully, though run_query will likely fail

# --- Pydantic Models for OpenAI API Compatibility ---

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "rag-agent"
    messages: List[Message]
    temperature: Optional[float] = 0.0
    stream: Optional[bool] = False

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: Message
    finish_reason: str

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: Optional[Dict[str, int]] = None

# --- Routes ---

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": config is not None}

@app.get("/v1/models")
async def list_models():
    # Return a dummy model list so OpenWebUI can see it
    return {
        "object": "list",
        "data": [
            {
                "id": "rag-agent",
                "object": "model",
                "created": 1677610602,
                "owned_by": "user",
            }
        ]
    }

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    if not config:
        raise HTTPException(status_code=500, detail="Server configuration invalid.")

    try:
        # 1. Extract the latest question (Logic can be improved to handle full history contextually)
        # For this RAG implementation, we map the OpenAI history to LangChain format
        # so the agent *can* potentially see history if the graph supports it.
        
        langchain_messages = []
        for msg in request.messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                langchain_messages.append(SystemMessage(content=msg.content))
        
        # Ideally, we identify the last user question to drive the retrieval
        last_user_content = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                last_user_content = msg.content
                break
        
        if not last_user_content:
             raise HTTPException(status_code=400, detail="No user message found.")

        # 2. Run the RAG Workflow
        # We pass the formatted messages. run_query expects 'messages' in the state.
        result_state = run_query(
            question=last_user_content,
            config=config,
            messages=langchain_messages,
            use_hierarchical=True # Defaulting to True as per current codebase preference
        )

        # 3. Extract the response
        # The graph state typically has 'messages' with the final AIMessage appended
        # or a 'generation' field.
        
        response_content = ""
        
        # Strategy A: Check 'generation' field (explicit output)
        if result_state.get("generation"):
             response_content = result_state["generation"]
        
        # Strategy B: Check the last message in the state
        elif result_state.get("messages"):
            last_msg = result_state["messages"][-1]
            if isinstance(last_msg, AIMessage) or hasattr(last_msg, 'content'):
                response_content = last_msg.content
            else:
                response_content = str(last_msg)
        else:
            response_content = "Error: No response generated from the RAG agent."

        # 4. Construct OpenAI-compatible response
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4()}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=Message(role="assistant", content=response_content),
                    finish_reason="stop"
                )
            ]
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Run via: python api.py
    uvicorn.run(app, host="0.0.0.0", port=8000)
