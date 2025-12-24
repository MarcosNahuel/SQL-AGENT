"""
Insight Graph v2 - Arquitectura Supervisor con Reflexión

Implementa el patrón Supervisor de LangGraph con:
- Supervisor Agent que orquesta agentes especializados
- SQL Writer con Chain-of-Thought
- Ciclo de Reflexión para autocorrección de errores
- Command objects para routing dinámico
- Validación AST de SQL
"""
import os
import sys
import uuid
import json
import asyncio
from typing import TypedDict, Optional, List, Literal, Any, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END, START
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import add_messages

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..agents.intent_router import IntentRouter, RoutingDecision, ResponseType, get_intent_router
from ..agents.data_agent import DataAgent
from ..agents.presentation_agent import PresentationAgent
from ..schemas.intent import QueryRequest
from ..schemas.payload import DataPayload
from ..schemas.dashboard import DashboardSpec, SlotConfig, NarrativeConfig, KpiCardConfig, ChartConfig
from ..schemas.agent_state import (
    InsightStateV2,
    SQLOutput,
    SQLReflection,
    SupervisorDecision,
    ExecutionStatus,
    SQLExecutionResult,
    create_initial_state
)
from ..utils.sql_validator import validate_sql_ast, SQLRiskLevel
from ..observability.langsmith import traced
from ..sql.allowlist import get_available_queries, QUERY_ALLOWLIST
from ..sql.schema_docs import BUSINESS_CONTEXT, SCHEMA_CONTEXT
from ..memory.checkpointer import get_checkpointer_manager


# ============== Configuración LLM ==============

def get_llm(temperature: float = 0.1):
    """Obtiene el LLM configurado con fallback."""
    use_openrouter = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"

    if use_openrouter:
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            return ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=temperature,
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent-v2"
                }
            )

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=temperature
    )


# ============== Estado Simplificado ==============

class SupervisorState(TypedDict):
    """Estado del grafo con Supervisor Pattern."""
    # Input
    question: str
    date_from: Optional[str]
    date_to: Optional[str]
    filters: Optional[dict]

    # Routing
    routing_decision: Optional[RoutingDecision]

    # Data Processing
    data_payload: Optional[DataPayload]

    # Reflection
    retry_count: int
    max_retries: int
    last_error: Optional[str]

    # Output
    dashboard_spec: Optional[DashboardSpec]
    direct_response: Optional[str]

    # Metadata
    trace_id: Optional[str]
    error: Optional[str]
    agent_steps: List[dict]


# ============== Agentes Singleton ==============

_data_agent: Optional[DataAgent] = None
_presentation_agent: Optional[PresentationAgent] = None


def get_data_agent() -> DataAgent:
    global _data_agent
    if _data_agent is None:
        _data_agent = DataAgent()
    return _data_agent


def get_presentation_agent() -> PresentationAgent:
    global _presentation_agent
    if _presentation_agent is None:
        _presentation_agent = PresentationAgent()
    return _presentation_agent


# ============== Nodos del Grafo v2 ==============

@traced("Supervisor")
def supervisor_node(state: SupervisorState) -> Command[Literal["router", "data_agent", "presentation", "direct_response", "__end__"]]:
    """
    Nodo Supervisor que orquesta el flujo.
    Usa Command objects para routing dinámico.
    """
    step = {
        "node": "supervisor",
        "timestamp": datetime.utcnow().isoformat(),
        "action": "routing"
    }

    # Primera vez: ir al router
    if state.get("routing_decision") is None:
        step["decision"] = "route_to_router"
        return Command(
            goto="router",
            update={"agent_steps": state.get("agent_steps", []) + [step]}
        )

    decision = state["routing_decision"]

    # Si es conversacional, respuesta directa
    if decision.response_type in [ResponseType.CONVERSATIONAL, ResponseType.CLARIFICATION]:
        step["decision"] = "direct_response"
        return Command(
            goto="direct_response",
            update={"agent_steps": state.get("agent_steps", []) + [step]}
        )

    # Si necesita datos y no los tenemos
    if decision.needs_sql and state.get("data_payload") is None:
        step["decision"] = "fetch_data"
        return Command(
            goto="data_agent",
            update={"agent_steps": state.get("agent_steps", []) + [step]}
        )

    # Si tenemos datos y necesitamos dashboard
    if decision.needs_dashboard and state.get("dashboard_spec") is None:
        step["decision"] = "generate_dashboard"
        return Command(
            goto="presentation",
            update={"agent_steps": state.get("agent_steps", []) + [step]}
        )

    # Completado
    step["decision"] = "complete"
    return Command(
        goto=END,
        update={"agent_steps": state.get("agent_steps", []) + [step]}
    )


@traced("Router")
def router_node(state: SupervisorState) -> Command[Literal["supervisor"]]:
    """
    Nodo Router que clasifica la intención.
    Retorna al Supervisor con la decisión.
    """
    step = {
        "node": "router",
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        router = get_intent_router()
        decision = router.route(state["question"])
        step["response_type"] = decision.response_type.value
        step["domain"] = decision.domain

        print(f"[Router] Decision: {decision.response_type.value}, Domain: {decision.domain}")

        return Command(
            goto="supervisor",
            update={
                "routing_decision": decision,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )
    except Exception as e:
        print(f"[Router] Error: {e}")
        # Fallback: asumir dashboard
        step["error"] = str(e)
        fallback = RoutingDecision(
            response_type=ResponseType.DASHBOARD,
            needs_sql=True,
            needs_dashboard=True,
            needs_narrative=True,
            confidence=0.5,
            reasoning="Router fallback"
        )
        return Command(
            goto="supervisor",
            update={
                "routing_decision": fallback,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DataAgent")
def data_agent_node(state: SupervisorState) -> Command[Literal["supervisor", "reflection"]]:
    """
    Nodo DataAgent que ejecuta queries.
    Si hay error, puede ir a Reflection para autocorrección.
    """
    step = {
        "node": "data_agent",
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        agent = get_data_agent()
        payload = agent.run(
            question=state["question"],
            date_from=state.get("date_from"),
            date_to=state.get("date_to")
        )

        step["refs_count"] = len(payload.available_refs)
        step["status"] = "success"
        print(f"[DataAgent] Completado: {len(payload.available_refs)} refs")

        return Command(
            goto="supervisor",
            update={
                "data_payload": payload,
                "last_error": None,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        error_msg = str(e)
        step["error"] = error_msg
        step["status"] = "error"
        print(f"[DataAgent] Error: {e}")

        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)

        # Si aún podemos reintentar, ir a reflection
        if retry_count < max_retries:
            return Command(
                goto="reflection",
                update={
                    "last_error": error_msg,
                    "retry_count": retry_count + 1,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )

        # Max retries alcanzado
        return Command(
            goto="supervisor",
            update={
                "error": f"Max retries ({max_retries}) exceeded: {error_msg}",
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("Reflection")
def reflection_node(state: SupervisorState) -> Command[Literal["data_agent"]]:
    """
    Nodo de Reflexión para analizar errores y autocorregir.
    """
    step = {
        "node": "reflection",
        "timestamp": datetime.utcnow().isoformat(),
        "retry_count": state.get("retry_count", 0),
        "error": state.get("last_error")
    }

    print(f"[Reflection] Retry {state.get('retry_count')}: {state.get('last_error')}")

    # Aquí podríamos usar LLM para analizar el error y ajustar la estrategia
    # Por ahora, simplemente reintentamos

    return Command(
        goto="data_agent",
        update={
            "agent_steps": state.get("agent_steps", []) + [step]
        }
    )


@traced("Presentation")
def presentation_node(state: SupervisorState) -> Command[Literal["supervisor"]]:
    """
    Nodo PresentationAgent que genera el dashboard.
    """
    step = {
        "node": "presentation",
        "timestamp": datetime.utcnow().isoformat(),
    }

    if state.get("error") or not state.get("data_payload"):
        step["status"] = "skipped"
        return Command(
            goto="supervisor",
            update={"agent_steps": state.get("agent_steps", []) + [step]}
        )

    try:
        agent = get_presentation_agent()
        spec = agent.run(
            question=state["question"],
            payload=state["data_payload"]
        )

        step["status"] = "success"
        step["title"] = spec.title
        print(f"[Presentation] Dashboard: {spec.title}")

        return Command(
            goto="supervisor",
            update={
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        step["error"] = str(e)
        step["status"] = "error"
        print(f"[Presentation] Error: {e}")

        return Command(
            goto="supervisor",
            update={
                "error": f"Presentation error: {str(e)}",
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DirectResponse")
def direct_response_node(state: SupervisorState) -> Command[Literal["supervisor"]]:
    """
    Nodo para respuestas directas (conversacionales).
    """
    step = {
        "node": "direct_response",
        "timestamp": datetime.utcnow().isoformat(),
    }

    decision = state.get("routing_decision")

    if decision and decision.direct_response:
        response = decision.direct_response
        spec = DashboardSpec(
            title="SQL Agent",
            subtitle="Asistente de datos",
            conclusion=response,
            slots=SlotConfig(
                filters=[],
                series=[],
                charts=[],
                narrative=[NarrativeConfig(type="summary", text=response)]
            )
        )

        step["status"] = "success"
        return Command(
            goto="supervisor",
            update={
                "direct_response": response,
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    step["status"] = "no_response"
    return Command(
        goto="supervisor",
        update={"agent_steps": state.get("agent_steps", []) + [step]}
    )


# ============== Construcción del Grafo ==============

def build_insight_graph_v2(checkpointer=None):
    """
    Construye el grafo v2 con Supervisor Pattern.

    Args:
        checkpointer: Optional checkpointer for state persistence (PostgresSaver or MemorySaver)

    Flujo:
    [Supervisor] --> [Router] --> [Supervisor]
         |
         +--> [DataAgent] --> [Reflection] --> [DataAgent] (retry loop)
         |         |
         |         +--> [Supervisor]
         |
         +--> [Presentation] --> [Supervisor]
         |
         +--> [DirectResponse] --> [Supervisor]
         |
         +--> [END]
    """
    workflow = StateGraph(SupervisorState)

    # Agregar nodos
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("router", router_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("presentation", presentation_node)
    workflow.add_node("direct_response", direct_response_node)

    # Entry point: Supervisor
    workflow.set_entry_point("supervisor")

    # Compilar con o sin checkpointer
    if checkpointer:
        return workflow.compile(checkpointer=checkpointer, name="InsightGraph-v2-Supervisor")
    return workflow.compile(name="InsightGraph-v2-Supervisor")


# ============== Singleton del Grafo ==============

_compiled_graph_v2 = None
_compiled_graph_v2_with_checkpointer = None


def get_insight_graph_v2(use_checkpointer: bool = True):
    """
    Obtiene el grafo v2 compilado (singleton).

    Args:
        use_checkpointer: If True, tries to use the global checkpointer for persistence
    """
    global _compiled_graph_v2, _compiled_graph_v2_with_checkpointer

    if use_checkpointer:
        # Try to get checkpointer from global manager
        try:
            manager = get_checkpointer_manager()
            if manager and manager.checkpointer:
                if _compiled_graph_v2_with_checkpointer is None:
                    _compiled_graph_v2_with_checkpointer = build_insight_graph_v2(manager.checkpointer)
                    print("[Graph v2] Compiled with checkpointer")
                return _compiled_graph_v2_with_checkpointer
        except Exception as e:
            print(f"[Graph v2] Checkpointer not available: {e}")

    # Fallback to graph without checkpointer
    if _compiled_graph_v2 is None:
        _compiled_graph_v2 = build_insight_graph_v2()
        print("[Graph v2] Compiled without checkpointer")
    return _compiled_graph_v2


# ============== Entry Points ==============

def run_insight_graph_v2(
    request: QueryRequest,
    trace_id: Optional[str] = None,
    thread_id: Optional[str] = None
) -> SupervisorState:
    """
    Ejecuta el grafo v2 de forma síncrona.

    Args:
        request: Query request with question and filters
        trace_id: Trace ID for observability
        thread_id: Thread ID for checkpointer persistence (enables conversation memory)
    """
    trace = trace_id or str(uuid.uuid4())[:8]
    thread = thread_id or f"thread-{trace}"

    initial_state: SupervisorState = {
        "question": request.question,
        "date_from": request.date_from.isoformat() if request.date_from else None,
        "date_to": request.date_to.isoformat() if request.date_to else None,
        "filters": request.filters,
        "routing_decision": None,
        "data_payload": None,
        "retry_count": 0,
        "max_retries": 3,
        "last_error": None,
        "dashboard_spec": None,
        "direct_response": None,
        "trace_id": trace,
        "error": None,
        "agent_steps": []
    }

    graph = get_insight_graph_v2()
    config = {
        "run_name": f"InsightGraph-v2-{trace}",
        "tags": ["sql-agent", "v2", "supervisor"],
        "metadata": {"trace_id": trace},
        "configurable": {
            "thread_id": thread  # For checkpointer persistence
        }
    }

    print(f"[Graph v2] Starting with trace_id={trace}, thread_id={thread}")
    result = graph.invoke(initial_state, config=config)
    print(f"[Graph v2] Completed. Steps: {len(result.get('agent_steps', []))}")

    return result


async def run_insight_graph_v2_streaming(
    request: QueryRequest,
    trace_id: Optional[str] = None,
    thread_id: Optional[str] = None
):
    """
    Versión streaming del grafo v2.
    Genera eventos SSE con el progreso.

    Args:
        request: Query request with question and filters
        trace_id: Trace ID for observability
        thread_id: Thread ID for checkpointer persistence (enables conversation memory)
    """
    trace = trace_id or str(uuid.uuid4())[:8]
    thread = thread_id or f"thread-{trace}"

    initial_state: SupervisorState = {
        "question": request.question,
        "date_from": request.date_from.isoformat() if request.date_from else None,
        "date_to": request.date_to.isoformat() if request.date_to else None,
        "filters": request.filters,
        "routing_decision": None,
        "data_payload": None,
        "retry_count": 0,
        "max_retries": 3,
        "last_error": None,
        "dashboard_spec": None,
        "direct_response": None,
        "trace_id": trace,
        "error": None,
        "agent_steps": []
    }

    # Evento: Inicio
    yield json.dumps({
        "event": "start",
        "trace_id": trace,
        "message": "🔍 Analizando tu pregunta...",
        "step": "init",
        "timestamp": datetime.utcnow().isoformat()
    })
    await asyncio.sleep(0.05)

    graph = get_insight_graph_v2()
    config = {
        "run_name": f"InsightGraph-v2-{trace}",
        "tags": ["sql-agent", "v2", "supervisor", "streaming"],
        "metadata": {"trace_id": trace},
        "configurable": {
            "thread_id": thread  # For checkpointer persistence
        }
    }

    last_node = None
    final_state = None

    try:
        # Stream updates from the graph
        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name != last_node:
                    # Emitir evento de progreso
                    message = _get_node_message(node_name)
                    yield json.dumps({
                        "event": "progress",
                        "message": message,
                        "step": node_name,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    await asyncio.sleep(0.05)
                    last_node = node_name

                # Guardar estado final
                if isinstance(node_output, dict):
                    if final_state is None:
                        final_state = node_output
                    else:
                        final_state.update(node_output)

    except Exception as e:
        yield json.dumps({
            "event": "error",
            "message": f"❌ Error: {str(e)}",
            "step": "error",
            "timestamp": datetime.utcnow().isoformat()
        })
        return

    # Evento: Completado
    if final_state:
        result = _build_result(final_state)
        yield json.dumps({
            "event": "complete",
            "message": "✨ Análisis completado",
            "trace_id": trace,
            "result": result
        })


def _get_node_message(node_name: str) -> str:
    """Obtiene el mensaje de progreso para un nodo."""
    messages = {
        "supervisor": "🎯 Supervisor coordinando...",
        "router": "🧠 Clasificando consulta...",
        "data_agent": "🔎 Ejecutando consultas SQL...",
        "reflection": "🔄 Analizando y corrigiendo...",
        "presentation": "🤖 Generando dashboard...",
        "direct_response": "💬 Preparando respuesta..."
    }
    return messages.get(node_name, f"⚙️ {node_name}...")


def _build_result(state: SupervisorState) -> dict:
    """Construye el resultado final para SSE."""
    spec = state.get("dashboard_spec")
    payload = state.get("data_payload")

    return {
        "success": state.get("error") is None,
        "dashboard_spec": spec.model_dump() if spec and hasattr(spec, 'model_dump') else (spec.dict() if spec else None),
        "data_payload": {
            "kpis": payload.kpis.model_dump() if payload and payload.kpis and hasattr(payload.kpis, 'model_dump') else (payload.kpis.dict() if payload and payload.kpis else None),
            "time_series": [ts.model_dump() if hasattr(ts, 'model_dump') else ts.dict() for ts in payload.time_series] if payload and payload.time_series else [],
            "top_items": [ti.model_dump() if hasattr(ti, 'model_dump') else ti.dict() for ti in payload.top_items] if payload and payload.top_items else [],
            "tables": []
        } if payload else None,
        "data_meta": {
            "available_refs": payload.available_refs if payload else [],
            "datasets_count": len(payload.datasets_meta) if payload and payload.datasets_meta else 0,
            "has_kpis": payload.kpis is not None if payload else False,
            "has_time_series": bool(payload.time_series) if payload else False,
            "has_top_items": bool(payload.top_items) if payload else False
        } if payload else None,
        "agent_steps": state.get("agent_steps", [])
    }


# ============== Exportar para compatibilidad ==============

# Re-exportar funciones del grafo v1 para compatibilidad
from .insight_graph import (
    build_visual_slots,
    get_demo_data,
    run_insight_graph,
    run_insight_graph_streaming,
    get_insight_graph,
    get_cache_stats,
    invalidate_cache
)
