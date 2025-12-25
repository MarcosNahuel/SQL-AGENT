"""
AI SDK v5 Compatible Chat Streaming Endpoint

This module implements the /v1/chat/stream endpoint that emits
the AI SDK v5 DATA stream protocol for seamless integration
with the useChat hook.

Wire Format:
data: {"type":"start","messageId":"msg-xxx"}
data: {"type":"text-start","textId":"text-1"}
data: {"type":"text-delta","textId":"text-1","delta":"..."}
data: {"type":"text-end","textId":"text-1"}
data: {"type":"data-agent_step","data":{...}}
data: {"type":"data-dashboard","data":{...}}
data: {"type":"finish","finishReason":"complete"}
data: [DONE]

Supports both v1 (linear) and v2 (supervisor) graph architectures.
Set USE_GRAPH_V2=true to enable the new supervisor pattern.

Now includes chat memory persistence for conversation history.
"""
import os
import json
import uuid
from datetime import datetime
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..schemas.intent import QueryRequest
from ..graphs.insight_graph import run_insight_graph_streaming
from ..utils.date_parser import extract_date_range, format_date_context
from ..memory.chat_memory import get_chat_memory

# Import v2 graph if available
try:
    from ..graphs.insight_graph_v2 import run_insight_graph_v2_streaming
    V2_AVAILABLE = True
except ImportError:
    V2_AVAILABLE = False
    print("[v1_chat] Warning: Graph v2 not available")

router = APIRouter(prefix="/v1", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for chat endpoint"""
    question: str = Field(..., description="User question in natural language")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    user_id: Optional[str] = Field(None, description="User ID")


def emit_sse(event_type: str, data: dict) -> str:
    """Format a server-sent event in AI SDK v5 format"""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


def emit_custom_data(data_type: str, data: dict) -> str:
    """Emit a custom data part (data-xxx format)"""
    payload = {"type": f"data-{data_type}", "data": data}
    return f"data: {json.dumps(payload)}\n\n"


async def generate_ai_sdk_stream(
    question: str,
    trace_id: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Generate AI SDK v5 compatible SSE stream.

    This wraps the existing LangGraph pipeline and converts
    its events to AI SDK v5 protocol format.

    Supports both v1 (linear) and v2 (supervisor) architectures
    via USE_GRAPH_V2 environment variable.
    """
    message_id = f"msg-{trace_id}"
    text_id = f"text-{trace_id}"

    # Check if v2 is enabled
    use_v2 = os.getenv("USE_GRAPH_V2", "false").lower() == "true" and V2_AVAILABLE
    print(f"[v1_chat] use_v2={use_v2}, V2_AVAILABLE={V2_AVAILABLE}, USE_GRAPH_V2={os.getenv('USE_GRAPH_V2')}", flush=True)

    # Initialize chat memory for persistence (user message saved at endpoint level)
    thread_id = conversation_id or f"thread-{trace_id}"
    chat_memory = get_chat_memory(thread_id, user_id)

    # 1. Start message
    yield emit_sse("start", {"messageId": message_id})

    # 2. Emit trace info as custom data
    yield emit_custom_data("trace", {
        "trace_id": trace_id,
        "request_id": conversation_id or trace_id,
        "ts": datetime.now().isoformat(),
        "graph_version": "v2" if use_v2 else "v1"
    })

    # 3. Start text block for narrative
    yield emit_sse("text-start", {"textId": text_id})

    # Extract dates from natural language question
    date_from, date_to = extract_date_range(question)
    date_context = format_date_context(date_from, date_to)

    # Emit date extraction info
    yield emit_custom_data("agent_step", {
        "step": "date_extraction",
        "status": "progress",
        "ts": datetime.now().isoformat(),
        "message": f"Periodo detectado: {date_context}",
        "detail": {"date_from": date_from, "date_to": date_to}
    })

    # Create query request for LangGraph with extracted dates
    query_request = QueryRequest(
        question=question,
        date_from=date_from,
        date_to=date_to,
        filters={}
    )

    # Track accumulated narrative for progressive streaming
    accumulated_text = ""
    dashboard_emitted = False
    data_payload_emitted = False

    # 4. Process through LangGraph pipeline (v1 or v2)
    # Pass thread_id for checkpointer persistence (already set above)

    if use_v2:
        stream_generator = run_insight_graph_v2_streaming(query_request, trace_id, thread_id)
    else:
        stream_generator = run_insight_graph_streaming(query_request, trace_id, thread_id)

    async for event_str in stream_generator:
        try:
            event = json.loads(event_str)
            event_type = event.get("event", "")

            # Map to agent_step custom data
            step_data = {
                "step": event.get("step", "unknown"),
                "status": "progress" if event_type == "progress" else event_type,
                "ts": event.get("timestamp", datetime.now().isoformat()),
                "message": event.get("message", ""),
            }
            if event.get("detail"):
                step_data["detail"] = {"info": event["detail"]}

            yield emit_custom_data("agent_step", step_data)

            # Handle completion event
            if event_type == "complete" and event.get("result"):
                result = event["result"]

                # Emit dashboard spec as custom data
                if result.get("dashboard_spec") and not dashboard_emitted:
                    yield emit_custom_data("dashboard", result["dashboard_spec"])
                    dashboard_emitted = True

                    # Extract narrative from dashboard spec for text streaming
                    spec = result["dashboard_spec"]

                    # Stream conclusion as text
                    conclusion = spec.get("conclusion", "")
                    if conclusion:
                        yield emit_sse("text-delta", {"textId": text_id, "delta": conclusion})
                        accumulated_text = conclusion
                        # Save assistant response to persistent storage
                        chat_memory.add_message_sync("assistant", conclusion, {
                            "trace_id": trace_id,
                            "dashboard_title": spec.get("title", "")
                        })

                # Emit data payload
                if result.get("data_payload") and not data_payload_emitted:
                    yield emit_custom_data("payload", result["data_payload"])
                    data_payload_emitted = True

                # Emit data meta
                if result.get("data_meta"):
                    yield emit_custom_data("meta", result["data_meta"])

            # Handle error event
            if event_type == "error":
                error_text = event.get("message", "Error procesando la consulta")
                yield emit_sse("text-delta", {"textId": text_id, "delta": error_text})
                yield emit_custom_data("agent_step", {
                    "step": "error",
                    "status": "error",
                    "ts": datetime.now().isoformat(),
                    "message": error_text
                })

        except json.JSONDecodeError:
            # Skip malformed events
            continue

    # 5. End text block
    yield emit_sse("text-end", {"textId": text_id})

    # 6. Finish message
    yield emit_sse("finish", {
        "finishReason": "complete",
        "messageId": message_id
    })

    # 7. Done marker
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    AI SDK v5 compatible streaming chat endpoint.

    Accepts chat messages and returns a streaming response
    in the AI SDK v5 DATA stream protocol format.
    """
    trace_id = str(uuid.uuid4())[:8]

    # Save user message BEFORE streaming (synchronous, guaranteed to run)
    thread_id = request.conversation_id or f"thread-{trace_id}"
    try:
        chat_memory = get_chat_memory(thread_id, request.user_id)
        chat_memory.add_message_sync("user", request.question, {"trace_id": trace_id})
    except Exception as e:
        print(f"[chat_stream] Error saving user message: {e}", flush=True)

    return StreamingResponse(
        generate_ai_sdk_stream(
            question=request.question,
            trace_id=trace_id,
            conversation_id=request.conversation_id,
            user_id=request.user_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-ui-message-stream": "v1",
        }
    )


@router.get("/chat/test-memory")
async def test_memory():
    """Test endpoint for chat memory debugging"""
    from ..memory.chat_memory import get_memory_client, get_chat_memory

    client = get_memory_client()
    result = {
        "is_available": client.is_available,
        "base_url": client.base_url[:30] + "..." if client.base_url else "EMPTY",
        "api_key_present": bool(client.api_key)
    }

    # Try to insert a test message
    if client.is_available:
        memory = get_chat_memory("test-from-endpoint", "test-user")
        memory.add_message_sync("user", "Test from endpoint", {"test": True})
        result["insert_attempted"] = True

    return result
