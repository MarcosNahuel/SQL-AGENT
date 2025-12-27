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
from ..agents.clarification_agent import ClarificationAgent, ClarificationAnalysis, get_clarification_agent
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


# ============== Estado del Grafo (usando InsightStateV2 con memoria) ==============
# NOTA: Se usa InsightStateV2 de schemas.agent_state que incluye:
# - messages: Annotated[List[AnyMessage], add_messages] para memoria
# - Todos los campos necesarios para routing, data, presentation


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
def router_node(state: InsightStateV2) -> Command[Literal["data_agent", "handle_direct_response", "clarification_agent", "__end__"]]:
    """
    Nodo Router como CEO - decide Y ejecuta navegación directamente.
    Implementa el patrón Router-as-CEO de LangGraph 2025.

    MEMORIA: Registra la pregunta del usuario en el historial de mensajes.

    Flujo:
    - CONVERSATIONAL → direct_response
    - CLARIFICATION → clarification_agent (LLM-based dynamic clarification)
    - DATA_ONLY/DASHBOARD → data_agent
    """
    print(f"[router_node] INICIANDO para: {state.get('question', '')[:50]}", file=sys.stderr, flush=True)
    step = {
        "node": "router",
        "timestamp": datetime.utcnow().isoformat(),
    }

    # MEMORIA: Agregar pregunta del usuario al historial
    user_message = HumanMessage(content=state["question"])

    try:
        print(f"[router_node] Obteniendo IntentRouter...", file=sys.stderr, flush=True)
        router = get_intent_router()
        print(f"[router_node] Llamando a router.route()...", file=sys.stderr, flush=True)
        decision = router.route(state["question"])
        print(f"[router_node] Decisión recibida: {decision.response_type.value}", file=sys.stderr, flush=True)
        step["response_type"] = decision.response_type.value
        step["domain"] = decision.domain

        print(f"[Router] Decision: {decision.response_type.value}, Domain: {decision.domain}")

        # Router como CEO - decide Y navega directamente
        if decision.response_type == ResponseType.CONVERSATIONAL:
            step["goto"] = "handle_direct_response"
            return Command(
                goto="handle_direct_response",
                update={
                    "messages": [user_message],  # MEMORIA: add_messages reducer appends
                    "routing_decision": decision,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )

        # CLARIFICATION -> usar ClarificationAgent para respuesta dinamica
        if decision.response_type == ResponseType.CLARIFICATION:
            step["goto"] = "clarification_agent"
            return Command(
                goto="clarification_agent",
                update={
                    "messages": [user_message],  # MEMORIA: add_messages reducer appends
                    "routing_decision": decision,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )

        # DATA_ONLY o DASHBOARD → data_agent
        step["goto"] = "data_agent"
        return Command(
            goto="data_agent",
            update={
                "messages": [user_message],  # MEMORIA: add_messages reducer appends
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
                "messages": [user_message],  # MEMORIA: add_messages reducer appends
                "routing_decision": fallback,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DataAgent")
def data_agent_node(state: InsightStateV2) -> Command[Literal["presentation", "reflection", "__end__"]]:
    """
    Nodo DataAgent que ejecuta queries.
    Flujo Router-as-CEO: data_agent → presentation → END (o → END si data_only)

    MEMORIA: Registra resumen de datos encontrados en el historial.
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
            date_to=state.get("date_to"),
            chat_context=state.get("chat_context")  # Contexto de conversación
        )

        step["refs_count"] = len(payload.available_refs)
        step["status"] = "success"
        print(f"[DataAgent] Completado: {len(payload.available_refs)} refs")

        # MEMORIA: Crear resumen de los datos encontrados
        data_summary = f"Datos encontrados: {len(payload.available_refs)} datasets"
        if payload.kpis and payload.kpis.total_sales is not None:
            data_summary += f", Ventas=${payload.kpis.total_sales:,.0f}"
        if payload.kpis and payload.kpis.total_orders is not None:
            data_summary += f", Órdenes={payload.kpis.total_orders}"
        data_message = AIMessage(content=data_summary)

        # Determinar siguiente paso basado en routing_decision
        decision = state.get("routing_decision")
        needs_dashboard = decision.needs_dashboard if decision else True

        if needs_dashboard:
            step["goto"] = "presentation"
            return Command(
                goto="presentation",
                update={
                    "messages": [data_message],  # MEMORIA: add_messages reducer appends
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
                    "messages": [data_message],  # MEMORIA: add_messages reducer appends
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
        error_message = AIMessage(content=f"Error al procesar: {error_msg}")
        step["goto"] = "end"
        return Command(
            goto=END,
            update={
                "messages": [error_message],  # MEMORIA: add_messages reducer appends
                "error": f"Max retries ({max_retries}) exceeded: {error_msg}",
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("Reflection")
def reflection_node(state: InsightStateV2) -> Command[Literal["data_agent"]]:
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
def presentation_node(state: InsightStateV2) -> Command[Literal["__end__"]]:
    """
    Nodo PresentationAgent que genera el dashboard.
    Flujo Router-as-CEO: presentation → END

    MEMORIA: Registra la conclusión/respuesta final en el historial.
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
            payload=state["data_payload"],
            chat_context=state.get("chat_context")  # Pasar contexto de conversación
        )

        step["status"] = "success"
        step["title"] = spec.title
        step["goto"] = "end"
        print(f"[Presentation] Dashboard: {spec.title}")

        # MEMORIA: Agregar conclusión al historial
        conclusion = spec.conclusion if spec.conclusion else spec.title
        response_message = AIMessage(content=conclusion)

        return Command(
            goto=END,
            update={
                "messages": [response_message],  # MEMORIA: add_messages reducer appends
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        step["error"] = str(e)
        step["status"] = "error"
        step["goto"] = "end"
        print(f"[Presentation] Error: {e}")

        error_message = AIMessage(content=f"Error generando dashboard: {str(e)}")
        return Command(
            goto=END,
            update={
                "messages": [error_message],  # MEMORIA: add_messages reducer appends
                "error": f"Presentation error: {str(e)}",
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )


@traced("DirectResponse")
def direct_response_node(state: InsightStateV2) -> Command[Literal["__end__"]]:
    """
    Nodo para respuestas directas (conversacionales).
    Flujo Router-as-CEO: direct_response → END

    MEMORIA: Registra la respuesta conversacional en el historial.
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

        # MEMORIA: Agregar respuesta al historial
        response_message = AIMessage(content=response)

        step["status"] = "success"
        step["goto"] = "end"
        return Command(
            goto=END,
            update={
                "messages": [response_message],  # MEMORIA: add_messages reducer appends
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


@traced("ClarificationAgent")
def clarification_agent_node(state: InsightStateV2) -> Command[Literal["data_agent", "__end__"]]:
    """
    Nodo ClarificationAgent - usa LLM para generar clarificaciones dinamicas.

    A diferencia del sistema determinista anterior, este nodo:
    1. Analiza semanticamente si la pregunta realmente necesita clarificacion
    2. Si NO necesita clarificacion, infiere la intencion y continua a data_agent
    3. Si SI necesita clarificacion, genera pregunta contextual y termina

    MEMORIA: Registra la respuesta/clarificacion en el historial.
    """
    step = {
        "node": "clarification_agent",
        "timestamp": datetime.utcnow().isoformat(),
    }

    question = state["question"]
    decision = state.get("routing_decision")

    # Obtener el tipo de ambiguedad detectada por heuristicas (si existe)
    detected_ambiguity = None
    if decision and decision.clarification:
        # Extraer tipo de ambiguedad del reasoning
        if "multi_domain" in decision.reasoning:
            detected_ambiguity = "multi_domain"
        elif "too_short" in decision.reasoning:
            detected_ambiguity = "too_short"
        elif "pronoun" in decision.reasoning:
            detected_ambiguity = "pronoun_without_context"

    try:
        agent = get_clarification_agent()
        analysis = agent.analyze(question, detected_ambiguity)

        step["needs_clarification"] = analysis.needs_clarification
        step["reasoning"] = analysis.reasoning[:100]

        if not analysis.needs_clarification:
            # El LLM determino que NO necesita clarificacion - inferir e ir a data_agent
            print(f"[ClarificationAgent] No clarification needed, inferred: {analysis.inferred_intent}")
            step["status"] = "inferred"
            step["goto"] = "data_agent"

            # Actualizar routing_decision con la intencion inferida
            if decision:
                decision.response_type = ResponseType.DASHBOARD
                decision.needs_sql = True
                decision.needs_dashboard = True
                decision.domain = analysis.inferred_domain or "sales"
                decision.reasoning = f"Inferred by ClarificationAgent: {analysis.reasoning}"

            infer_message = AIMessage(content=f"Entendido: {analysis.inferred_intent or question}")

            return Command(
                goto="data_agent",
                update={
                    "messages": [infer_message],
                    "routing_decision": decision,
                    "agent_steps": state.get("agent_steps", []) + [step]
                }
            )

        # SI necesita clarificacion - generar respuesta contextual y terminar
        print(f"[ClarificationAgent] Clarification needed: {analysis.clarification_question}")
        step["status"] = "clarification_generated"
        step["goto"] = "end"

        # Construir respuesta con la clarificacion
        clarification_response = analysis.understood_context or ""
        if clarification_response:
            clarification_response += "\n\n"
        clarification_response += analysis.clarification_question or "Podrias ser mas especifico?"

        if analysis.options:
            clarification_response += "\n\nOpciones sugeridas:\n"
            for i, opt in enumerate(analysis.options, 1):
                clarification_response += f"  {i}. {opt}\n"

        # Crear dashboard spec con la clarificacion
        spec = DashboardSpec(
            title="Clarificacion necesaria",
            subtitle="El agente necesita mas contexto",
            conclusion=analysis.clarification_question,
            slots=SlotConfig(
                filters=[],
                series=[],
                charts=[],
                narrative=[NarrativeConfig(type="callout", text=clarification_response)]
            )
        )

        response_message = AIMessage(content=clarification_response)

        return Command(
            goto=END,
            update={
                "messages": [response_message],
                "direct_response": clarification_response,
                "dashboard_spec": spec,
                "agent_steps": state.get("agent_steps", []) + [step]
            }
        )

    except Exception as e:
        print(f"[ClarificationAgent] Error: {e}")
        step["error"] = str(e)
        step["status"] = "error"
        step["goto"] = "data_agent"

        # En caso de error, continuar a data_agent (mejor intentar que fallar)
        return Command(
            goto="data_agent",
            update={
                "agent_steps": state.get("agent_steps", []) + [step]
            }
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
         +--> [ClarificationAgent] --> [DataAgent] (si infiere intencion)
         |                         \-> [END] (si necesita clarificacion)
         |
         +--> [DirectResponse] --> [END]

    Cada nodo usa Command objects para routing dinámico.
    No hay supervisor intermediario.
    """
    workflow = StateGraph(InsightStateV2)

    # Agregar nodos (sin supervisor - Router es el CEO)
    workflow.add_node("router", router_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("presentation", presentation_node)
    workflow.add_node("handle_direct_response", direct_response_node)
    workflow.add_node("clarification_agent", clarification_agent_node)

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
) -> InsightStateV2:
    """
    Ejecuta el grafo v2 de forma síncrona.

    Args:
        request: Query request with question and filters
        trace_id: Trace ID for observability
        thread_id: Thread ID for checkpointer persistence (enables conversation memory)
    """
    trace = trace_id or str(uuid.uuid4())[:8]
    thread = thread_id or f"thread-{trace}"

    # Usar factory function para crear estado con todos los campos requeridos
    initial_state = create_initial_state(
        question=request.question,
        date_from=request.date_from.isoformat() if request.date_from else None,
        date_to=request.date_to.isoformat() if request.date_to else None,
        filters=request.filters,
        trace_id=trace,
        chat_context=request.chat_context  # Contexto de conversación
    )

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

    # Usar factory function para crear estado con memoria y contexto
    initial_state = create_initial_state(
        question=request.question,
        date_from=request.date_from.isoformat() if request.date_from else None,
        date_to=request.date_to.isoformat() if request.date_to else None,
        filters=request.filters,
        trace_id=trace,
        chat_context=request.chat_context  # Contexto de conversación
    )

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
        "handle_direct_response": "💬 Preparando respuesta...",
        "clarification_agent": "🤔 Analizando si necesito mas contexto..."
    }
    return messages.get(node_name, f"⚙️ {node_name}...")


def _build_result(state: InsightStateV2) -> dict:
    """Construye el resultado final para SSE. Updated 2025-12-26."""
    spec = state.get("dashboard_spec")
    payload = state.get("data_payload")

    return {
        "success": state.get("error") is None,
        "dashboard_spec": spec.model_dump() if spec and hasattr(spec, 'model_dump') else (spec.dict() if spec else None),
        "data_payload": {
            "kpis": payload.kpis.model_dump() if payload and payload.kpis and hasattr(payload.kpis, 'model_dump') else (payload.kpis.dict() if payload and payload.kpis else None),
            "time_series": [ts.model_dump() if hasattr(ts, 'model_dump') else ts.dict() for ts in payload.time_series] if payload and payload.time_series else [],
            "top_items": [ti.model_dump() if hasattr(ti, 'model_dump') else ti.dict() for ti in payload.top_items] if payload and payload.top_items else [],
            "tables": [t.model_dump() if hasattr(t, 'model_dump') else t.dict() for t in payload.tables] if payload and payload.tables else [],
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
# Legacy alias - ahora usa InsightStateV2 con memoria
InsightState = InsightStateV2

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
