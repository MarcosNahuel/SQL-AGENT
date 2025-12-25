"""
Insight Graph - Orquestacion LangGraph con Router Inteligente

Flujo:
1. IntentRouter -> Clasifica y decide que agentes invocar
2. DataAgent -> Ejecuta queries SQL (si necesario)
3. PresentationAgent -> Genera DashboardSpec + Narrativa (si necesario)
4. DirectResponse -> Responde sin agentes (conversacional/clarificacion)
"""
from typing import TypedDict, Optional, Any, Literal
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from ..memory.checkpointer import get_checkpointer_manager
from ..agents.data_agent import DataAgent
from ..agents.presentation_agent import PresentationAgent
from ..agents.intent_router import IntentRouter, RoutingDecision, ResponseType, get_intent_router
from ..schemas.intent import QueryRequest
from ..schemas.payload import DataPayload
from ..schemas.dashboard import DashboardSpec, SlotConfig, NarrativeConfig, KpiCardConfig, ChartConfig
from .cache import cached_node, get_cache_stats, invalidate_cache
from ..observability.langsmith import traced, get_langsmith_callback, is_langsmith_enabled


def build_visual_slots(payload: DataPayload) -> SlotConfig:
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


class InsightState(TypedDict):
    """Estado del grafo de insights"""
    # Input
    question: str
    date_from: Optional[str]
    date_to: Optional[str]
    filters: Optional[dict]

    # Routing
    routing_decision: Optional[RoutingDecision]

    # Intermediate
    data_payload: Optional[DataPayload]

    # Output
    dashboard_spec: Optional[DashboardSpec]
    direct_response: Optional[str]  # Para respuestas conversacionales

    # Metadata
    error: Optional[str]
    trace_id: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


# Inicializar agentes (singleton para reutilizar)
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


# ============== NODOS DEL GRAFO ==============

@traced("Router")
def run_router_node(state: InsightState) -> InsightState:
    """Nodo que ejecuta el IntentRouter para decidir flujo"""
    try:
        router = get_intent_router()
        decision = router.route(state["question"])
        state["routing_decision"] = decision
        print(f"[Graph] Router decision: {decision.response_type.value} "
              f"(SQL={decision.needs_sql}, Dashboard={decision.needs_dashboard})")
    except Exception as e:
        # Si falla el router, asumir dashboard completo
        print(f"[Graph] Router error, defaulting to dashboard: {e}")
        state["routing_decision"] = RoutingDecision(
            response_type=ResponseType.DASHBOARD,
            needs_sql=True,
            needs_dashboard=True,
            needs_narrative=True,
            confidence=0.5,
            reasoning="Router fallback due to error"
        )
    return state


@traced("DirectResponse")
def run_direct_response_node(state: InsightState) -> InsightState:
    """Nodo para respuestas directas (sin SQL ni dashboard)"""
    decision = state.get("routing_decision")
    if decision and decision.direct_response:
        state["direct_response"] = decision.direct_response
        # Crear un DashboardSpec minimo para la UI
        state["dashboard_spec"] = DashboardSpec(
            title="SQL Agent",
            subtitle="Asistente de datos",
            conclusion=decision.direct_response,
            slots=SlotConfig(
                filters=[],
                series=[],
                charts=[],
                narrative=[
                    NarrativeConfig(type="summary", text=decision.direct_response)
                ]
            )
        )
        state["completed_at"] = datetime.utcnow().isoformat()
        print(f"[Graph] Direct response: {decision.response_type.value}")
    return state


@traced("DataAgent")
def run_data_agent_node(state: InsightState) -> InsightState:
    """Nodo que ejecuta el DataAgent"""
    try:
        agent = get_data_agent()
        payload = agent.run(
            question=state["question"],
            date_from=state.get("date_from"),
            date_to=state.get("date_to")
        )
        state["data_payload"] = payload
        print(f"[Graph] DataAgent completado: {len(payload.available_refs)} refs disponibles")
    except Exception as e:
        state["error"] = f"Error en DataAgent: {str(e)}"
        print(f"[Graph] Error en DataAgent: {e}")
    return state


@traced("PresentationAgent")
def run_presentation_agent_node(state: InsightState) -> InsightState:
    """Nodo que ejecuta el PresentationAgent"""
    if state.get("error"):
        return state

    if not state.get("data_payload"):
        state["error"] = "No hay datos para presentar"
        return state

    try:
        agent = get_presentation_agent()
        spec = agent.run(
            question=state["question"],
            payload=state["data_payload"]
        )
        state["dashboard_spec"] = spec
        state["completed_at"] = datetime.utcnow().isoformat()
        print(f"[Graph] PresentationAgent completado: {spec.title}")
    except Exception as e:
        state["error"] = f"Error en PresentationAgent: {str(e)}"
        print(f"[Graph] Error en PresentationAgent: {e}")

    return state


def route_after_router(state: InsightState) -> Literal["DirectResponse", "DataAgent"]:
    """Decide siguiente nodo basado en routing decision"""
    decision = state.get("routing_decision")

    if not decision:
        return "DataAgent"  # Fallback

    # Si es conversacional o clarificacion, respuesta directa
    if decision.response_type in [ResponseType.CONVERSATIONAL, ResponseType.CLARIFICATION]:
        return "DirectResponse"

    # Si necesita SQL, ir a DataAgent
    if decision.needs_sql:
        return "DataAgent"

    return "DirectResponse"


def route_after_data(state: InsightState) -> Literal["PresentationAgent", "__end__"]:
    """Decide si generar dashboard o terminar"""
    if state.get("error"):
        return END

    decision = state.get("routing_decision")

    # Si necesita dashboard, ir a PresentationAgent
    if decision and decision.needs_dashboard:
        return "PresentationAgent"

    # Si solo necesita datos (DATA_ONLY), generar respuesta simple
    if decision and decision.response_type == ResponseType.DATA_ONLY:
        # Generar spec simplificado sin graficos
        if state.get("data_payload"):
            payload = state["data_payload"]
            kpis = payload.kpis

            # Crear respuesta con KPIs en narrativa
            summary_parts = []

            if kpis:
                if hasattr(kpis, 'total_sales') and kpis.total_sales:
                    summary_parts.append(f"Ventas totales: ${kpis.total_sales:,.0f}")
                if hasattr(kpis, 'total_orders') and kpis.total_orders:
                    summary_parts.append(f"Ordenes: {kpis.total_orders:,}")
                if hasattr(kpis, 'avg_order_value') and kpis.avg_order_value:
                    summary_parts.append(f"Ticket promedio: ${kpis.avg_order_value:,.0f}")

            # Si hay top_items, agregar resumen
            if payload.top_items:
                for ranking in payload.top_items:
                    if ranking.items:
                        top_item = ranking.items[0]
                        summary_parts.append(f"Top {ranking.ranking_name}: {top_item.title} (${top_item.value:,.0f})")

            # Si hay tablas (ej: stock alerts), agregar resumen
            if payload.raw_data:
                critical_items = [r for r in payload.raw_data if r.get('severity') == 'critical' or r.get('status') == 'CRITICO']
                if critical_items:
                    summary_parts.append(f"Alertas criticas de stock: {len(critical_items)} productos")

            conclusion = ". ".join(summary_parts) if summary_parts else "Datos obtenidos exitosamente"

            # Generar slots visuales basados en el payload
            visual_slots = build_visual_slots(payload)
            visual_slots.narrative = [NarrativeConfig(type="summary", text=conclusion)]

            state["dashboard_spec"] = DashboardSpec(
                title="Resumen de Datos",
                subtitle=state["question"],
                conclusion=conclusion,
                slots=visual_slots
            )
            state["completed_at"] = datetime.utcnow().isoformat()
        return END

    return "PresentationAgent"


# Construir el grafo
def build_insight_graph(checkpointer=None):
    """
    Construye el grafo de LangGraph con Router Inteligente y persistencia.

    Flujo:
    [Router] --> [DirectResponse] --> END (conversacional)
         |
         +--> [DataAgent] --> [PresentationAgent] --> END (dashboard)
                   |
                   +--> END (data_only, sin graficos)

    Args:
        checkpointer: PostgresSaver o MemorySaver para persistencia de estado.
                     Si None, usa el manager global.
    """
    workflow = StateGraph(InsightState)

    # Agregar nodos
    workflow.add_node("Router", run_router_node)
    workflow.add_node("DirectResponse", run_direct_response_node)
    workflow.add_node("DataAgent", run_data_agent_node)
    workflow.add_node("PresentationAgent", run_presentation_agent_node)

    # Entry point: Router
    workflow.set_entry_point("Router")

    # Router -> DirectResponse o DataAgent
    workflow.add_conditional_edges(
        "Router",
        route_after_router,
        {
            "DirectResponse": "DirectResponse",
            "DataAgent": "DataAgent"
        }
    )

    # DirectResponse -> END
    workflow.add_edge("DirectResponse", END)

    # DataAgent -> PresentationAgent o END
    workflow.add_conditional_edges(
        "DataAgent",
        route_after_data,
        {
            "PresentationAgent": "PresentationAgent",
            END: END
        }
    )

    # PresentationAgent -> END
    workflow.add_edge("PresentationAgent", END)

    # Compilar con checkpointer para persistencia
    if checkpointer is None:
        manager = get_checkpointer_manager()
        checkpointer = manager.checkpointer

    if checkpointer:
        print(f"[Graph] Compilando con checkpointer: {type(checkpointer).__name__}")
        return workflow.compile(checkpointer=checkpointer, name="InsightGraph-v2")
    else:
        print("[Graph] Compilando sin checkpointer (memoria no persistente)")
        return workflow.compile(name="InsightGraph-v2")


# Grafo compilado (singleton)
_compiled_graph = None
_graph_initialized = False


def get_insight_graph(force_rebuild: bool = False):
    """
    Obtiene el grafo compilado con checkpointer para persistencia.

    Args:
        force_rebuild: Forzar reconstrucción del grafo

    Returns:
        Grafo compilado con o sin checkpointer
    """
    global _compiled_graph, _graph_initialized

    if _compiled_graph is None or force_rebuild:
        # Obtener checkpointer del manager
        manager = get_checkpointer_manager()

        # Si el manager no está inicializado, inicializar sync
        if manager.checkpointer is None and not _graph_initialized:
            print("[Graph] Inicializando checkpointer sync...")
            manager.initialize_sync()
            _graph_initialized = True

        _compiled_graph = build_insight_graph(checkpointer=manager.checkpointer)

    return _compiled_graph


def rebuild_graph_with_checkpointer():
    """
    Reconstruye el grafo con el checkpointer actual.
    Útil después de inicializar el checkpointer async.
    """
    global _compiled_graph
    _compiled_graph = None
    return get_insight_graph(force_rebuild=True)


def _build_run_config(trace_id: str, thread_id: Optional[str] = None) -> RunnableConfig:
    """
    Construye config para invocación del grafo.

    Args:
        trace_id: ID de trazabilidad para LangSmith
        thread_id: ID del hilo de conversación para persistencia

    Returns:
        RunnableConfig con thread_id en configurable
    """
    config: RunnableConfig = {
        "run_name": f"InsightGraph-{trace_id}",
        "tags": ["sql-agent", "insight-graph"],
        "metadata": {
            "trace_id": trace_id,
            "graph_name": "InsightGraph",
            "version": "2.0"
        }
    }

    # Agregar thread_id para persistencia si está disponible
    if thread_id:
        config["configurable"] = {
            "thread_id": thread_id,
            "checkpoint_ns": ""  # Namespace vacío por defecto
        }

    return config


def get_demo_data() -> DataPayload:
    """Retorna datos de demo para testing sin DB/LLM"""
    from ..schemas.payload import KPIData, TimeSeriesData, TimeSeriesPoint, TopItemsData, TopItem, DatasetMeta
    from datetime import datetime, timedelta
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


async def run_insight_graph_streaming(
    request: QueryRequest,
    trace_id: Optional[str] = None,
    thread_id: Optional[str] = None
):
    """
    Version streaming del grafo que genera eventos SSE.
    Yields eventos JSON con el progreso del analisis.
    Usa el Router Inteligente para decidir el flujo.

    Args:
        request: QueryRequest con la pregunta y filtros
        trace_id: ID de trazabilidad para LangSmith
        thread_id: ID del hilo de conversación para persistencia
    """
    import uuid
    import os
    import json
    import asyncio

    # Preparar estado inicial
    trace = trace_id or str(uuid.uuid4())[:8]
    thread = thread_id or str(uuid.uuid4())

    # Log para debugging
    print(f"[Graph Streaming] Iniciando con trace_id={trace}, thread_id={thread}")

    # Evento: Inicio
    yield json.dumps({
        "event": "start",
        "trace_id": trace,
        "thread_id": thread,
        "message": "🔍 Analizando tu pregunta...",
        "step": "init",
        "timestamp": datetime.utcnow().isoformat()
    })
    await asyncio.sleep(0.1)

    # Paso 1: Router - Clasificar intent
    yield json.dumps({
        "event": "progress",
        "message": "🧠 Clasificando tu consulta...",
        "step": "router",
        "detail": f"Pregunta: {request.question[:50]}..."
    })

    router = get_intent_router()
    decision = router.route(request.question)

    yield json.dumps({
        "event": "progress",
        "message": f"📋 Tipo detectado: {decision.response_type.value}",
        "step": "router_complete",
        "detail": decision.reasoning
    })
    await asyncio.sleep(0.1)

    # Paso 2: Si es conversacional o clarificacion, responder directo
    if decision.response_type in [ResponseType.CONVERSATIONAL, ResponseType.CLARIFICATION]:
        yield json.dumps({
            "event": "progress",
            "message": "💬 Generando respuesta...",
            "step": "direct_response"
        })

        spec = DashboardSpec(
            title="SQL Agent",
            subtitle="Asistente de datos",
            conclusion=decision.direct_response or "",
            slots=SlotConfig(
                filters=[],
                series=[],
                charts=[],
                narrative=[
                    NarrativeConfig(type="summary", text=decision.direct_response or "")
                ]
            )
        )

        yield json.dumps({
            "event": "complete",
            "message": "✨ Respuesta lista",
            "trace_id": trace,
            "result": {
                "success": True,
                "dashboard_spec": spec.model_dump() if hasattr(spec, 'model_dump') else spec.dict(),
                "data_payload": {"kpis": None, "time_series": [], "top_items": [], "tables": []},
                "data_meta": {"available_refs": [], "datasets_count": 0, "has_kpis": False, "has_time_series": False, "has_top_items": False}
            }
        })
        return

    # Paso 3: Necesita SQL - Ejecutar DataAgent
    data_payload = None

    # Check for demo mode
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        yield json.dumps({
            "event": "progress",
            "message": "📊 Modo demo - usando datos de ejemplo...",
            "step": "demo"
        })
        await asyncio.sleep(0.5)
        data_payload = get_demo_data()
    else:
        yield json.dumps({
            "event": "progress",
            "message": "📡 Conectando con base de datos...",
            "step": "data_connect"
        })
        await asyncio.sleep(0.1)

        try:
            agent = get_data_agent()

            yield json.dumps({
                "event": "progress",
                "message": "🔎 Ejecutando consultas SQL...",
                "step": "data_query",
                "detail": f"Dominio: {decision.domain or 'general'}"
            })

            data_payload = agent.run(
                question=request.question,
                date_from=request.date_from.isoformat() if request.date_from else None,
                date_to=request.date_to.isoformat() if request.date_to else None
            )

            yield json.dumps({
                "event": "progress",
                "message": f"✅ Datos obtenidos: {len(data_payload.available_refs)} datasets",
                "step": "data_complete",
                "detail": ", ".join(data_payload.available_refs[:5])
            })
            await asyncio.sleep(0.1)

        except Exception as e:
            yield json.dumps({
                "event": "error",
                "message": f"❌ Error obteniendo datos: {str(e)}",
                "step": "data_error"
            })
            return

    # Paso 4: Si solo necesita datos (DATA_ONLY), responder sin dashboard
    if decision.response_type == ResponseType.DATA_ONLY:
        yield json.dumps({
            "event": "progress",
            "message": "📝 Generando resumen de datos...",
            "step": "data_summary"
        })

        kpi_text = []
        if data_payload.kpis:
            kpis = data_payload.kpis
            if hasattr(kpis, 'total_sales') and kpis.total_sales:
                kpi_text.append(f"Ventas totales: ${kpis.total_sales:,.0f}")
            if hasattr(kpis, 'total_orders') and kpis.total_orders:
                kpi_text.append(f"Ordenes: {kpis.total_orders:,}")
            if hasattr(kpis, 'avg_order_value') and kpis.avg_order_value:
                kpi_text.append(f"Ticket promedio: ${kpis.avg_order_value:,.0f}")

        # Generar slots visuales basados en el payload (KPIs, Charts)
        visual_slots = build_visual_slots(data_payload)
        # Agregar narrativa
        visual_slots.narrative = [NarrativeConfig(type="summary", text=". ".join(kpi_text))] if kpi_text else []

        spec = DashboardSpec(
            title="Resumen de Datos",
            subtitle=request.question,
            conclusion=". ".join(kpi_text) if kpi_text else "Datos obtenidos",
            slots=visual_slots
        )
        print(f"[DATA_ONLY] Generated spec with {len(visual_slots.series)} KPIs, {len(visual_slots.charts)} charts")

        yield json.dumps({
            "event": "complete",
            "message": "✨ Datos listos",
            "trace_id": trace,
            "result": {
                "success": True,
                "dashboard_spec": spec.model_dump() if hasattr(spec, 'model_dump') else spec.dict(),
                "data_payload": {
                    "kpis": data_payload.kpis.model_dump() if data_payload.kpis and hasattr(data_payload.kpis, 'model_dump') else (data_payload.kpis.dict() if data_payload.kpis else None),
                    "time_series": [ts.model_dump() if hasattr(ts, 'model_dump') else ts.dict() for ts in data_payload.time_series] if data_payload.time_series else [],
                    "top_items": [ti.model_dump() if hasattr(ti, 'model_dump') else ti.dict() for ti in data_payload.top_items] if data_payload.top_items else [],
                    "tables": []
                },
                "data_meta": {
                    "available_refs": data_payload.available_refs,
                    "datasets_count": len(data_payload.datasets_meta) if data_payload.datasets_meta else 0,
                    "has_kpis": data_payload.kpis is not None,
                    "has_time_series": bool(data_payload.time_series),
                    "has_top_items": bool(data_payload.top_items)
                }
            }
        })
        return

    # Paso 5: Necesita Dashboard - Ejecutar PresentationAgent
    yield json.dumps({
        "event": "progress",
        "message": "🤖 Activando UltraThink para analisis profundo...",
        "step": "presentation_start"
    })
    await asyncio.sleep(0.1)

    yield json.dumps({
        "event": "progress",
        "message": "💭 Razonando sobre los datos y generando insights...",
        "step": "ultrathink",
        "detail": "Analizando patrones, tendencias y anomalias"
    })

    try:
        pres_agent = get_presentation_agent()
        spec = pres_agent.run(
            question=request.question,
            payload=data_payload
        )

        yield json.dumps({
            "event": "progress",
            "message": f"📈 Dashboard generado: {spec.title}",
            "step": "presentation_complete",
            "detail": f"{len(spec.slots.series)} KPIs, {len(spec.slots.charts)} graficos"
        })
        await asyncio.sleep(0.1)

    except Exception as e:
        yield json.dumps({
            "event": "error",
            "message": f"❌ Error generando dashboard: {str(e)}",
            "step": "presentation_error"
        })
        return

    # Evento: Resultado final
    yield json.dumps({
        "event": "complete",
        "message": "✨ Analisis completado",
        "trace_id": trace,
        "result": {
            "success": True,
            "dashboard_spec": spec.model_dump() if hasattr(spec, 'model_dump') else spec.dict(),
            "data_payload": {
                "kpis": data_payload.kpis.model_dump() if data_payload.kpis and hasattr(data_payload.kpis, 'model_dump') else (data_payload.kpis.dict() if data_payload.kpis else None),
                "time_series": [ts.model_dump() if hasattr(ts, 'model_dump') else ts.dict() for ts in data_payload.time_series] if data_payload.time_series else [],
                "top_items": [ti.model_dump() if hasattr(ti, 'model_dump') else ti.dict() for ti in data_payload.top_items] if data_payload.top_items else [],
                "tables": []
            },
            "data_meta": {
                "available_refs": data_payload.available_refs,
                "datasets_count": len(data_payload.datasets_meta) if data_payload.datasets_meta else 0,
                "has_kpis": data_payload.kpis is not None,
                "has_time_series": bool(data_payload.time_series),
                "has_top_items": bool(data_payload.top_items)
            }
        }
    })


def run_insight_graph(
    request: QueryRequest,
    trace_id: Optional[str] = None,
    thread_id: Optional[str] = None
) -> InsightState:
    """
    Entry point principal para ejecutar el grafo completo.
    Usa el Router Inteligente para decidir el flujo.

    Args:
        request: QueryRequest con la pregunta y filtros
        trace_id: ID de trazabilidad opcional para LangSmith
        thread_id: ID del hilo de conversación para persistencia

    Returns:
        InsightState con el resultado completo
    """
    import uuid
    import os

    # Generar IDs si no se proveen
    trace = trace_id or str(uuid.uuid4())[:8]
    thread = thread_id or str(uuid.uuid4())

    # Preparar estado inicial
    initial_state: InsightState = {
        "question": request.question,
        "date_from": request.date_from.isoformat() if request.date_from else None,
        "date_to": request.date_to.isoformat() if request.date_to else None,
        "filters": request.filters,
        "routing_decision": None,
        "data_payload": None,
        "dashboard_spec": None,
        "direct_response": None,
        "error": None,
        "trace_id": trace,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None
    }

    print(f"[Graph] Iniciando con trace_id={trace}, thread_id={thread}")
    print(f"[Graph] Pregunta: {request.question}")

    # Check for demo mode
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        print("[Graph] DEMO MODE - usando datos de ejemplo")
        initial_state["data_payload"] = get_demo_data()
        # Run only presentation agent
        try:
            agent = get_presentation_agent()
            spec = agent.run(
                question=initial_state["question"],
                payload=initial_state["data_payload"]
            )
            initial_state["dashboard_spec"] = spec
            initial_state["completed_at"] = datetime.utcnow().isoformat()
            print(f"[Graph] Demo completado: {spec.title}")
        except Exception as e:
            initial_state["error"] = f"Error en demo mode: {str(e)}"
            print(f"[Graph] Error en demo: {e}")
        return initial_state

    # Ejecutar grafo normal con persistencia
    graph = get_insight_graph()
    run_config = _build_run_config(trace, thread_id=thread)
    result = graph.invoke(initial_state, config=run_config)

    print(f"[Graph] Completado. Error: {result.get('error')}")

    return result
