"""
Insight Graph v2 - Arquitectura Router-as-CEO (LangGraph 2025)

Implementa el patrón Router-as-CEO de LangGraph v0.2+ con:
- Router que decide Y ejecuta navegación con Command objects
- DataAgent con .with_structured_output() para queries
- PresentationAgent con .with_structured_output() para narrativa
- Ciclo de Reflexión para autocorrección de errores
- Grafo simplificado: Router → Workers → END
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
from .cache import get_cache_stats, invalidate_cache


# ============== Utility Functions ==============

def build_visual_slots(payload) -> SlotConfig:
    """
    Genera configuraciones visuales (KPIs, Charts) basadas en el DataPayload.
    Usado en flujo DATA_ONLY para renderizar dashboards sin LLM.
    """
    slots = SlotConfig(filters=[], series=[], charts=[], narrative=[])

    # 1. KPI Cards - basado en kpis disponibles
    if payload.kpis:
        kpi_mappings = [
            ("Ventas Totales", "kpi.total_sales", "currency"),
            ("Órdenes", "kpi.total_orders", "number"),
            ("Ticket Promedio", "kpi.avg_order_value", "currency"),
            ("Unidades", "kpi.total_units", "number"),
            ("Interacciones", "kpi.total_interactions", "number"),
            ("Escalados", "kpi.escalated_count", "number"),
            ("Tasa Escalado", "kpi.escalation_rate", "percent"),
            # Inventario
            ("Productos Críticos", "kpi.critical_count", "number"),
            ("Productos Alerta", "kpi.warning_count", "number"),
            ("Stock OK", "kpi.ok_count", "number"),
            ("Total Productos", "kpi.total_products", "number"),
        ]
        for label, ref, fmt in kpi_mappings:
            if ref in payload.available_refs:
                slots.series.append(KpiCardConfig(
                    label=label,
                    value_ref=ref,
                    format=fmt
                ))

    # 2. Gráficos de Time Series
    if payload.time_series:
        for ts in payload.time_series:
            ref = f"ts.{ts.series_name}"
            slots.charts.append(ChartConfig(
                type="area_chart",
                title=f"Tendencia: {ts.series_name.replace('_', ' ').title()}",
                dataset_ref=ref,
                x_axis="date",
                y_axis="value",
                color="#3b82f6"
            ))

    # 3. Gráficos de Top Items (Bar Chart)
    if payload.top_items:
        for top in payload.top_items:
            ref = f"top.{top.ranking_name}"
            slots.charts.append(ChartConfig(
                type="bar_chart",
                title=f"Top {top.ranking_name.replace('_', ' ').title()}",
                dataset_ref=ref,
                x_axis="title",
                y_axis="value",
                color="#10b981"
            ))

    return slots


def get_demo_data() -> DataPayload:
    """Retorna datos de demo para testing sin DB/LLM"""
    from ..schemas.payload import KPIData, TimeSeriesData, TimeSeriesPoint, TopItemsData, TopItem, DatasetMeta
    from datetime import timedelta
    import random

    # Generar datos de ejemplo
    today = datetime.now()
    time_series_points = []
    for i in range(30):
        date = (today - timedelta(days=29-i)).strftime("%Y-%m-%d")
        value = random.randint(50000, 200000)
        time_series_points.append(TimeSeriesPoint(date=date, value=float(value)))

    return DataPayload(
        kpis=KPIData(
            total_sales=4567890.50,
            total_orders=234,
            avg_order_value=19521.32,
            total_units=567
        ),
        time_series=[
            TimeSeriesData(
                series_name="ventas_por_dia",
                points=time_series_points
            )
        ],
        top_items=[
            TopItemsData(
                ranking_name="productos_top",
                items=[
                    TopItem(rank=1, id="MLA123", title="Kit Inyectores Chevrolet", value=456780.0, extra={"units_sold": 45}),
                    TopItem(rank=2, id="MLA456", title="Bomba de Agua Ford", value=345670.0, extra={"units_sold": 32}),
                    TopItem(rank=3, id="MLA789", title="Filtro de Aceite Universal", value=234560.0, extra={"units_sold": 89}),
                    TopItem(rank=4, id="MLA012", title="Bujias NGK x4", value=189000.0, extra={"units_sold": 67}),
                    TopItem(rank=5, id="MLA345", title="Correa de Distribucion", value=156780.0, extra={"units_sold": 23}),
                ],
                metric="revenue"
            )
        ],
        datasets_meta=[
            DatasetMeta(query_id="kpi_sales_summary", row_count=1, execution_time_ms=50.0),
            DatasetMeta(query_id="ts_sales_by_day", row_count=30, execution_time_ms=120.0),
            DatasetMeta(query_id="top_products_by_revenue", row_count=5, execution_time_ms=80.0),
        ],
        available_refs=[
            "kpi.total_sales", "kpi.total_orders", "kpi.avg_order_value", "kpi.total_units",
            "ts.ventas_por_dia", "top.productos_top"
        ]
    )


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


# ============== Nodos del Grafo v2 (Router-as-CEO) ==============

@traced("Router")
def router_node(state: SupervisorState) -> Command[Literal["data_agent", "direct_response", "__end__"]]:
    """
    Nodo Router como CEO - decide Y ejecuta navegación directamente.
    Implementa el patrón Router-as-CEO de LangGraph 2025.

    Flujo:
    - CONVERSATIONAL → direct_response
    - DATA_ONLY/DASHBOARD → data_agent
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

        # Router como CEO - decide Y navega directamente
        if decision.response_type in [ResponseType.CONVERSATIONAL, ResponseType.CLARIFICATION]:
            step["goto"] = "direct_response"
            return Command(
                goto="direct_response",
                update={
                    "routing_decision": decision,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )

        # DATA_ONLY o DASHBOARD → data_agent
        step["goto"] = "data_agent"
        return Command(
            goto="data_agent",
            update={
                "routing_decision": decision,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        print(f"[Router] Error: {e}")
        step["error"] = str(e)
        # Fallback: ir a data_agent con dashboard
        fallback = RoutingDecision(
            response_type=ResponseType.DASHBOARD,
            needs_sql=True,
            needs_dashboard=True,
            needs_narrative=True,
            confidence=0.5,
            reasoning="Router fallback"
        )
        step["goto"] = "data_agent"
        return Command(
            goto="data_agent",
            update={
                "routing_decision": fallback,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DataAgent")
def data_agent_node(state: SupervisorState) -> Command[Literal["presentation", "reflection", "__end__"]]:
    """
    Nodo DataAgent que ejecuta queries.
    Flujo Router-as-CEO: data_agent → presentation → END (o → END si data_only)
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

        # Determinar siguiente paso basado en routing_decision
        decision = state.get("routing_decision")
        needs_dashboard = decision.needs_dashboard if decision else True

        if needs_dashboard:
            step["goto"] = "presentation"
            return Command(
                goto="presentation",
                update={
                    "data_payload": payload,
                    "last_error": None,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )
        else:
            # DATA_ONLY: terminar sin presentation
            step["goto"] = "end"
            return Command(
                goto=END,
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

        # Max retries alcanzado - terminar con error
        step["goto"] = "end"
        return Command(
            goto=END,
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
def presentation_node(state: SupervisorState) -> Command[Literal["__end__"]]:
    """
    Nodo PresentationAgent que genera el dashboard.
    Flujo Router-as-CEO: presentation → END
    """
    step = {
        "node": "presentation",
        "timestamp": datetime.utcnow().isoformat(),
    }

    if state.get("error") or not state.get("data_payload"):
        step["status"] = "skipped"
        step["goto"] = "end"
        return Command(
            goto=END,
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
        step["goto"] = "end"
        print(f"[Presentation] Dashboard: {spec.title}")

        return Command(
            goto=END,
            update={
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        step["error"] = str(e)
        step["status"] = "error"
        step["goto"] = "end"
        print(f"[Presentation] Error: {e}")

        return Command(
            goto=END,
            update={
                "error": f"Presentation error: {str(e)}",
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DirectResponse")
def direct_response_node(state: SupervisorState) -> Command[Literal["__end__"]]:
    """
    Nodo para respuestas directas (conversacionales).
    Flujo Router-as-CEO: direct_response → END
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
        step["goto"] = "end"
        return Command(
            goto=END,
            update={
                "direct_response": response,
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    step["status"] = "no_response"
    step["goto"] = "end"
    return Command(
        goto=END,
        update={"agent_steps": state.get("agent_steps", []) + [step]}
    )


# ============== Construcción del Grafo ==============

def build_insight_graph_v2(checkpointer=None):
    """
    Construye el grafo v2 con Router-as-CEO Pattern (LangGraph 2025).

    Args:
        checkpointer: Optional checkpointer for state persistence (PostgresSaver or MemorySaver)

    Flujo simplificado (Router como CEO):
    [Router] --> [DataAgent] --> [Presentation] --> [END]
         |            |
         |            +--> [Reflection] --> [DataAgent] (retry loop)
         |
         +--> [DirectResponse] --> [END]

    Cada nodo usa Command objects para routing dinámico.
    No hay supervisor intermediario.
    """
    workflow = StateGraph(SupervisorState)

    # Agregar nodos (sin supervisor - Router es el CEO)
    workflow.add_node("router", router_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("presentation", presentation_node)
    workflow.add_node("direct_response", direct_response_node)

    # Entry point: Router (CEO)
    workflow.set_entry_point("router")

    # Compilar con o sin checkpointer
    if checkpointer:
        return workflow.compile(checkpointer=checkpointer, name="InsightGraph-v2-RouterCEO")
    return workflow.compile(name="InsightGraph-v2-RouterCEO")


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
        "recursion_limit": 15,  # Limit graph iterations to prevent infinite loops
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


# ============== Compatibility Aliases ==============
# For backwards compatibility with v1 imports
run_insight_graph = run_insight_graph_v2
run_insight_graph_streaming = run_insight_graph_v2_streaming
get_insight_graph = get_insight_graph_v2

# Legacy state type alias
InsightState = SupervisorState

__all__ = [
    # Primary v2 exports
    "get_insight_graph_v2",
    "run_insight_graph_v2",
    "run_insight_graph_v2_streaming",
    "build_insight_graph_v2",
    # Compatibility aliases
    "get_insight_graph",
    "run_insight_graph",
    "run_insight_graph_streaming",
    "InsightState",
    # Utilities
    "build_visual_slots",
    "get_demo_data",
    "get_cache_stats",
    "invalidate_cache",
]
