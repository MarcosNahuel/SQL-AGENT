"""
DataAgent - Agente de Datos / SQL Engine
Updated: 2025-12-26

Responsabilidades:
- Recibir un QueryPlan del IntentClassifier
- Ejecutar queries SOLO del allowlist
- Retornar DataPayload con los datasets
- NO genera SQL, solo ejecuta templates predefinidos
"""
import os
import sys
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import date
from functools import wraps

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..db.supabase_client import get_db_client
from ..sql.allowlist import (
    get_query_template,
    validate_query_id,
    get_available_queries,
    build_params,
    QUERY_ALLOWLIST
)
from ..sql.schema_docs import BUSINESS_CONTEXT, SCHEMA_CONTEXT
from ..schemas.payload import (
    DataPayload,
    KPIData,
    TimeSeriesData,
    TimeSeriesPoint,
    TopItemsData,
    TopItem,
    TableData,
    DatasetMeta,
    ComparisonData,
    ComparisonPeriod
)
from ..schemas.intent import QueryPlan
from ..prompts.ultrathink import get_query_decision_prompt
from ..utils.date_parser import extract_comparison_dates, is_comparison_query


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0):
    """Decorator para reintentar llamadas LLM con backoff exponencial."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e)
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        if attempt < max_retries - 1:
                            print(f"[DataAgent Retry] Rate limit hit. Waiting {delay:.1f}s...")
                            time.sleep(delay)
                        else:
                            print(f"[DataAgent Retry] Max retries exceeded")
                    else:
                        raise e
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


class DataAgent:
    """
    Agente que ejecuta queries SQL de forma segura.

    Usa .with_structured_output() para garantizar JSON válido
    sin necesidad de parsers manuales (LangGraph 2025 standard).
    """

    def __init__(self):
        self.db = get_db_client()

        # Flag para usar OpenRouter como primario
        self.use_openrouter_primary = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"

        # LLM Gemini (fallback si OpenRouter es primario)
        self.llm_gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.3  # Temperatura moderada para variedad en respuestas
        )

        # LLM OpenRouter (primario si USE_OPENROUTER_PRIMARY=true)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.llm_openrouter = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.3,  # Temperatura moderada para variedad
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent"
                }
            )
        else:
            self.llm_openrouter = None

        # LLM con structured output para decisiones de queries (2025 standard)
        self._structured_llm = None

    def _get_structured_llm(self):
        """
        Obtiene LLM configurado con .with_structured_output(QueryPlan).
        Esto garantiza JSON válido sin parsers manuales (2025 standard).
        """
        if self._structured_llm is None:
            base_llm = self.llm_openrouter if (self.use_openrouter_primary and self.llm_openrouter) else self.llm_gemini
            self._structured_llm = base_llm.with_structured_output(QueryPlan)
        return self._structured_llm

    def _invoke_llm(self, messages: list):
        """Invoca el LLM con OpenRouter como primario si USE_OPENROUTER_PRIMARY=true"""
        # Si OpenRouter es primario, usarlo directamente
        if self.use_openrouter_primary and self.llm_openrouter:
            print(f"[DataAgent] Usando OpenRouter (google/gemini-3-flash-preview)...")
            try:
                return self.llm_openrouter.invoke(messages)
            except Exception as e:
                print(f"[DataAgent] OpenRouter error, fallback to Gemini: {e}")
                return self.llm_gemini.invoke(messages)

        # Si no, usar Gemini como primario con fallback a OpenRouter
        try:
            return self.llm_gemini.invoke(messages)
        except Exception as e:
            error_str = str(e)
            if self.llm_openrouter and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()):
                print(f"[DataAgent] Gemini rate limit, switching to OpenRouter...")
                return self.llm_openrouter.invoke(messages)
            raise e

    def _invoke_structured(self, messages: list) -> QueryPlan:
        """
        Invoca el LLM con structured output para obtener QueryPlan directamente.
        Garantiza JSON válido sin parsers manuales (2025 standard).
        """
        structured_llm = self._get_structured_llm()

        if self.use_openrouter_primary and self.llm_openrouter:
            print(f"[DataAgent] Usando structured output (OpenRouter)...")
            try:
                return structured_llm.invoke(messages)
            except Exception as e:
                print(f"[DataAgent] Structured output error, fallback to Gemini: {e}")
                # Fallback: usar Gemini con structured output
                fallback_llm = self.llm_gemini.with_structured_output(QueryPlan)
                return fallback_llm.invoke(messages)

        try:
            return structured_llm.invoke(messages)
        except Exception as e:
            error_str = str(e)
            if self.llm_openrouter and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str):
                print(f"[DataAgent] Gemini rate limit, switching to OpenRouter structured...")
                fallback_llm = self.llm_openrouter.with_structured_output(QueryPlan)
                return fallback_llm.invoke(messages)
            raise e

    def _decide_queries_heuristic(self, question: str) -> QueryPlan:
        """
        Fallback: usa heuristicas simples para decidir queries sin LLM.
        """
        q_lower = question.lower()
        query_ids = []

        # Agente AI / Interacciones
        if any(kw in q_lower for kw in ["agente", "ai", "interacci", "bot", "asistente"]):
            query_ids = ["ai_interactions_summary", "recent_ai_interactions"]
            if "escalad" in q_lower:
                query_ids.append("escalated_cases")

        # Escalados específicamente
        elif "escalad" in q_lower:
            query_ids = ["escalated_cases", "ai_interactions_summary"]

        # Análisis por MES específico (enero, febrero, etc.) - requiere datos mensuales + productos
        elif any(kw in q_lower for kw in ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]):
            query_ids = ["kpi_sales_summary", "sales_by_month", "top_products_by_revenue"]

        # Ciclo de ventas / Estacionalidad / Tendencia mensual
        elif any(kw in q_lower for kw in ["ciclo", "estacionalidad", "temporada", "patron", "patrón"]):
            query_ids = ["kpi_sales_summary", "sales_by_month", "ts_sales_by_day"]

        # Mejor/peor mes - requiere análisis mensual
        elif any(kw in q_lower for kw in ["mejor mes", "peor mes", "mes que mas", "mes que más", "cual mes", "cuál mes", "que mes", "qué mes"]):
            query_ids = ["kpi_sales_summary", "sales_by_month", "top_products_by_revenue"]

        # Insights / Analisis profundo - requiere KPIs + tendencias + productos
        elif any(kw in q_lower for kw in ["insight", "analisis profundo", "análisis profundo", "analiza todo", "resumen ejecutivo", "executive summary"]):
            query_ids = ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

        # Pareto / 80-20 / Concentracion - ventas por producto
        elif any(kw in q_lower for kw in ["pareto", "80/20", "80-20", "concentracion", "concentración", "abc"]):
            query_ids = ["kpi_sales_summary", "top_products_by_revenue", "ts_sales_by_day"]

        # Ticket promedio / Ticket alto / Ticket bajo
        elif any(kw in q_lower for kw in ["ticket", "promedio de compra", "valor promedio", "orden promedio"]):
            query_ids = ["kpi_sales_summary", "ts_sales_by_day", "recent_orders"]

        # Top productos / Mas vendidos (ANTES de inventario para priorizar)
        elif any(kw in q_lower for kw in ["mas vendido", "más vendido", "mas vendidos", "más vendidos", "top producto", "top productos", "mejores producto", "mejores productos"]):
            query_ids = ["kpi_sales_summary", "top_products_by_revenue", "sales_by_month"]

        # IMPORTANTE: Inventario ANTES de Ventas porque "inventario" contiene "venta" como substring!
        # Inventario / Stock - INCLUIR stock_reorder_analysis para gráficos
        elif any(kw in q_lower for kw in ["inventario", "stock", "existencia"]):
            if any(kw in q_lower for kw in ["bajo", "alerta", "falta", "critico", "crítico"]):
                query_ids = ["kpi_inventory_summary", "products_low_stock", "stock_reorder_analysis"]
            else:
                query_ids = ["kpi_inventory_summary", "stock_reorder_analysis", "stock_alerts"]

        # Productos (generico, sin "vendido") - INCLUIR top_products_by_sales para gráficos
        elif "producto" in q_lower and not any(kw in q_lower for kw in ["vendido", "venta", "revenue"]):
            query_ids = ["kpi_inventory_summary", "products_inventory", "top_products_by_sales"]

        # Ventas / Revenue (DESPUES de inventario)
        elif any(kw in q_lower for kw in ["venta", "factura", "ingreso", "revenue", "vendido", "vendieron", "facturado"]):
            query_ids = ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

        # Quiebre de stock / Reposición - necesita análisis de stock + serie temporal + top ventas
        elif any(kw in q_lower for kw in ["quebrar", "quiebre", "agotar", "agotarse", "agotando", "faltante", "reponer", "reposicion", "reposición"]):
            query_ids = ["kpi_sales_summary", "stock_reorder_analysis", "ts_top_product_sales"]

        # Aumentar stock / Ponderar productos - necesita inventario + análisis de stock + ventas
        elif any(kw in q_lower for kw in ["aumentar stock", "aumentar inventario", "ponderar", "priorizar", "debo comprar"]):
            query_ids = ["kpi_sales_summary", "stock_reorder_analysis", "ts_top_product_sales", "products_low_stock"]

        # Preventa
        elif any(kw in q_lower for kw in ["preventa", "consulta", "pregunta"]):
            query_ids = ["preventa_summary", "recent_preventa_queries"]

        # Default: mostrar KPIs + tendencias + top items para mayor variedad
        else:
            query_ids = ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

        import sys
        print(f"[DataAgent] Heuristic selected: {query_ids}", file=sys.stderr)
        return QueryPlan(query_ids=query_ids, params={})

    def decide_queries(self, question: str, date_from: Optional[str], date_to: Optional[str], chat_context: Optional[str] = None) -> QueryPlan:
        """
        Decide queries usando heurísticas primero (rápido).
        Solo usa LLM cuando hay referencias ambiguas que requieren contexto.
        """
        use_llm = os.getenv("DATA_AGENT_USE_LLM", "true").lower() == "true"
        q_lower = question.lower()

        # OPTIMIZACIÓN: SIEMPRE usar heurísticas si hay keywords claros
        # Independientemente del chat_context - el LLM es muy lento
        has_clear_keywords = any(kw in q_lower for kw in [
            "inventario", "stock", "venta", "ventas", "producto", "orden", "ordenes",
            "agente", "escalado", "preventa", "kpi", "resumen", "dashboard",
            "vendido", "facturado", "revenue", "ingresos", "ticket",
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
            "mes", "semana", "dia", "año", "hoy", "ayer", "ultimos", "reciente"
        ])

        # Detectar si hay referencias ambiguas que REQUIEREN contexto de chat
        has_ambiguous_refs = any(ref in q_lower for ref in [
            "eso", "esto", "aquello", "lo mismo", "esos datos", "lo anterior",
            "mas de eso", "y de eso", "que mas", "amplia", "detalla"
        ])

        # Si hay keywords claros Y no hay referencias ambiguas, usar heurísticas SIEMPRE
        if has_clear_keywords and not has_ambiguous_refs:
            print(f"[DataAgent] Keywords claros detectados, usando heurísticas rápidas (bypass LLM)", file=sys.stderr, flush=True)
            return self._decide_queries_heuristic(question)

        if not use_llm:
            print(f"[DataAgent] LLM disabled, usando heuristicas para: {question[:50]}", file=sys.stderr, flush=True)
            return self._decide_queries_heuristic(question)

        print(f"[DataAgent] LLM structured output para: {question[:50]}", file=sys.stderr, flush=True)
        if chat_context:
            print(f"[DataAgent] Usando contexto de conversación: {len(chat_context)} chars", file=sys.stderr, flush=True)

        available = get_available_queries()
        queries_list = "\n".join([f"- {qid}: {desc}" for qid, desc in available.items()])

        system_prompt = f"""Eres un experto en análisis de datos de e-commerce para MercadoLibre Argentina.

{BUSINESS_CONTEXT}

## QUERIES DISPONIBLES (SOLO puedes elegir de esta lista):
{queries_list}

## CONOCIMIENTO DEL ESQUEMA

### Tabla ml_orders (Ventas)
- SIEMPRE filtrar por status='paid' para ventas reales
- total_amount = monto final pagado
- date_created = fecha de la orden

### Tabla ml_items (Productos)
- available_quantity < 10 = stock crítico
- status='active' para productos activos

### Tablas de AI (agent_interactions, escalations)
- was_escalated=true indica casos que requirieron humano

## REGLAS DE SELECCIÓN
1. SOLO usa query_ids de la lista de arriba
2. Elige las queries MÁS RELEVANTES (máx 3)
3. Para ventas: SIEMPRE incluir kpi_sales_summary
4. Para inventario: SIEMPRE incluir kpi_inventory_summary

## GUÍA RÁPIDA:
- Ventas/facturación: kpi_sales_summary, ts_sales_by_day, top_products_by_revenue
- Stock/inventario: kpi_inventory_summary, stock_reorder_analysis, stock_alerts
- Stock crítico/bajo: kpi_inventory_summary, products_low_stock, stock_reorder_analysis
- Agente AI/bot: ai_interactions_summary, recent_ai_interactions, escalated_cases

## IMPORTANTE PARA GRÁFICOS:
- SIEMPRE incluir al menos UNA query de tipo "top_items" o "time_series" para generar gráficos
- stock_reorder_analysis genera gráfico de barras (top_items)
- ts_top_product_sales genera gráfico de línea temporal
"""

        # Construir mensaje con contexto de conversación si existe
        context_section = ""
        if chat_context:
            context_section = f"""
## CONTEXTO DE CONVERSACIÓN ANTERIOR:
{chat_context}

"""

        user_msg = f"""{context_section}Pregunta ACTUAL del usuario: "{question}"
Rango de fechas: {date_from or 'últimos 30 días'} a {date_to or 'hoy'}

IMPORTANTE: Usa el contexto de conversación para entender mejor la pregunta.
Si el usuario dice "mostrame eso" o "y del inventario?", debes inferir de qué habla basándote en el contexto.

Selecciona las queries a ejecutar."""

        try:
            # Usar structured output - garantiza QueryPlan válido sin parsing manual
            plan: QueryPlan = self._invoke_structured([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_msg)
            ])

            # Validar que todas las queries existen en el allowlist
            valid_ids = [qid for qid in plan.query_ids if validate_query_id(qid)]
            print(f"[DataAgent] Queries válidas (structured output): {valid_ids}")

            if not valid_ids:
                # Fallback a queries default
                valid_ids = ["kpi_sales_summary", "ts_sales_by_day"]

            return QueryPlan(query_ids=valid_ids, params=plan.params)

        except Exception as e:
            print(f"[DataAgent] Structured output error, fallback to heuristics: {e}")
            return self._decide_queries_heuristic(question)

    def execute_plan(self, plan: QueryPlan, date_from: Optional[str] = None, date_to: Optional[str] = None) -> DataPayload:
        """
        Ejecuta un QueryPlan y retorna el DataPayload consolidado.
        """
        payload = DataPayload(
            datasets_meta=[],
            available_refs=[]
        )

        # Merge params con fechas
        base_params = {
            "date_from": date_from or plan.params.get("date_from"),
            "date_to": date_to or plan.params.get("date_to"),
            **plan.params
        }

        for query_id in plan.query_ids:
            try:
                rows, meta = self.db.execute_safe_query(query_id, base_params)
                payload.datasets_meta.append(meta)

                print(f"[execute_plan] query_id={query_id}, rows_count={len(rows) if rows else 0}", file=sys.stderr, flush=True)

                # Procesar segun tipo de output
                query_config = get_query_template(query_id)
                output_type = query_config.get("output_type")
                output_ref = query_config.get("output_ref")
                print(f"[execute_plan] output_type={output_type}, output_ref={output_ref}", file=sys.stderr, flush=True)

                if output_type == "kpi" and rows:
                    # Guardar KPIs dinamicamente segun el query
                    kpi_data = rows[0]
                    if payload.kpis is None:
                        payload.kpis = KPIData(**kpi_data)
                    else:
                        # Merge con KPIs existentes
                        for k, v in kpi_data.items():
                            setattr(payload.kpis, k, v)
                    # Agregar refs dinamicos basados en las keys del resultado
                    for key in kpi_data.keys():
                        ref = f"kpi.{key}"
                        if ref not in payload.available_refs:
                            payload.available_refs.append(ref)

                elif output_type == "time_series" and rows:
                    ts = TimeSeriesData(
                        series_name=output_ref.split(".")[-1] if output_ref else query_id,
                        points=[
                            TimeSeriesPoint(
                                date=str(row.get("date", "")),
                                value=float(row.get("value", 0))
                            )
                            for row in rows
                        ]
                    )
                    if payload.time_series is None:
                        payload.time_series = []
                    payload.time_series.append(ts)
                    payload.available_refs.append(output_ref or f"ts.{query_id}")

                elif output_type == "top_items" and rows:
                    print(f"[execute_plan] Processing top_items with {len(rows)} rows", file=sys.stderr, flush=True)
                    top = TopItemsData(
                        ranking_name=output_ref.split(".")[-1] if output_ref else query_id,
                        items=[
                            TopItem(
                                rank=int(row.get("rank", i + 1)),
                                id=str(row.get("id", "")),
                                title=str(row.get("title", "")),
                                value=float(row.get("value", 0) or 0),
                                extra={"units_sold": row.get("units_sold")} if "units_sold" in row else None
                            )
                            for i, row in enumerate(rows)
                        ],
                        metric="revenue"
                    )
                    print(f"[execute_plan] Created TopItemsData with {len(top.items)} items", file=sys.stderr, flush=True)
                    if payload.top_items is None:
                        payload.top_items = []
                    payload.top_items.append(top)
                    print(f"[execute_plan] payload.top_items now has {len(payload.top_items)} entries", file=sys.stderr, flush=True)
                    payload.available_refs.append(output_ref or f"top.{query_id}")

                elif output_type == "table":
                    # Determinar nombre de la tabla desde el ref
                    table_name = query_id
                    if output_ref and output_ref.startswith("table."):
                        table_name = output_ref.split(".")[1]

                    # Crear TableData y agregar a tables
                    table_data = TableData(name=table_name, rows=rows)
                    if payload.tables is None:
                        payload.tables = []
                    payload.tables.append(table_data)

                    # También mantener raw_data para compatibilidad
                    if payload.raw_data is None:
                        payload.raw_data = []
                    payload.raw_data.extend(rows)
                    payload.available_refs.append(output_ref or f"table.{query_id}")

            except Exception as e:
                print(f"Error ejecutando query {query_id}: {e}")
                # Continuar con las demas queries

        return payload

    def _calculate_delta_pct(self, current: Optional[float], previous: Optional[float]) -> Optional[float]:
        """Calcula el porcentaje de cambio entre dos valores."""
        if current is None or previous is None or previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 2)

    def run(self, question: str, date_from: Optional[str] = None, date_to: Optional[str] = None, chat_context: Optional[str] = None) -> DataPayload:
        """
        Entry point principal del DataAgent.
        1. Detecta si es comparación entre periodos
        2. Decide que queries ejecutar (usando contexto de conversación)
        3. Ejecuta el plan (2 veces si es comparación)
        4. Retorna el payload con datos de comparación si aplica
        """
        import sys
        print(f"[DataAgent.run] Question: {question[:50]}, date_from={date_from}, date_to={date_to}", file=sys.stderr, flush=True)
        if chat_context:
            print(f"[DataAgent.run] Chat context: {chat_context[:100]}...", file=sys.stderr, flush=True)

        # Detectar si es una comparación
        comparison_info = extract_comparison_dates(question)

        if comparison_info.is_comparison and comparison_info.previous_period:
            print(f"[DataAgent] COMPARACION detectada: {comparison_info.current_period.label} vs {comparison_info.previous_period.label}", file=sys.stderr, flush=True)

            # Paso 1: Decidir queries (con contexto de conversación)
            plan = self.decide_queries(question, date_from, date_to, chat_context)
            print(f"[DataAgent] Plan decidido: {plan.query_ids}", file=sys.stderr, flush=True)

            # Paso 2: Ejecutar para periodo ACTUAL
            current_date_from = comparison_info.current_period.date_from
            current_date_to = comparison_info.current_period.date_to
            print(f"[DataAgent] Ejecutando periodo ACTUAL: {current_date_from} a {current_date_to}", file=sys.stderr, flush=True)
            payload_current = self.execute_plan(plan, current_date_from, current_date_to)

            # Paso 3: Ejecutar para periodo ANTERIOR
            prev_date_from = comparison_info.previous_period.date_from
            prev_date_to = comparison_info.previous_period.date_to
            print(f"[DataAgent] Ejecutando periodo ANTERIOR: {prev_date_from} a {prev_date_to}", file=sys.stderr, flush=True)
            payload_previous = self.execute_plan(plan, prev_date_from, prev_date_to)

            # Paso 4: Construir estructura de comparación
            current_kpis = payload_current.kpis
            previous_kpis = payload_previous.kpis

            # Calcular deltas
            delta_sales = None
            delta_sales_pct = None
            delta_orders = None
            delta_orders_pct = None
            delta_avg_order = None
            delta_avg_order_pct = None
            delta_units = None
            delta_units_pct = None

            if current_kpis and previous_kpis:
                if current_kpis.total_sales is not None and previous_kpis.total_sales is not None:
                    delta_sales = round(current_kpis.total_sales - previous_kpis.total_sales, 2)
                    delta_sales_pct = self._calculate_delta_pct(current_kpis.total_sales, previous_kpis.total_sales)

                if current_kpis.total_orders is not None and previous_kpis.total_orders is not None:
                    delta_orders = current_kpis.total_orders - previous_kpis.total_orders
                    delta_orders_pct = self._calculate_delta_pct(float(current_kpis.total_orders), float(previous_kpis.total_orders))

                if current_kpis.avg_order_value is not None and previous_kpis.avg_order_value is not None:
                    delta_avg_order = round(current_kpis.avg_order_value - previous_kpis.avg_order_value, 2)
                    delta_avg_order_pct = self._calculate_delta_pct(current_kpis.avg_order_value, previous_kpis.avg_order_value)

                if current_kpis.total_units is not None and previous_kpis.total_units is not None:
                    delta_units = current_kpis.total_units - previous_kpis.total_units
                    delta_units_pct = self._calculate_delta_pct(float(current_kpis.total_units), float(previous_kpis.total_units))

            comparison_data = ComparisonData(
                is_comparison=True,
                current_period=ComparisonPeriod(
                    label=comparison_info.current_period.label,
                    date_from=current_date_from,
                    date_to=current_date_to,
                    kpis=current_kpis
                ),
                previous_period=ComparisonPeriod(
                    label=comparison_info.previous_period.label,
                    date_from=prev_date_from,
                    date_to=prev_date_to,
                    kpis=previous_kpis
                ),
                delta_sales=delta_sales,
                delta_sales_pct=delta_sales_pct,
                delta_orders=delta_orders,
                delta_orders_pct=delta_orders_pct,
                delta_avg_order=delta_avg_order,
                delta_avg_order_pct=delta_avg_order_pct,
                delta_units=delta_units,
                delta_units_pct=delta_units_pct
            )

            # El payload final usa los KPIs del periodo actual pero incluye comparison
            payload_current.comparison = comparison_data
            payload_current.available_refs.append("comparison")

            print(f"[DataAgent] Comparación calculada:", file=sys.stderr, flush=True)
            print(f"  - Ventas actuales: {current_kpis.total_sales if current_kpis else 'N/A'}", file=sys.stderr, flush=True)
            print(f"  - Ventas anteriores: {previous_kpis.total_sales if previous_kpis else 'N/A'}", file=sys.stderr, flush=True)
            print(f"  - Delta: {delta_sales} ({delta_sales_pct}%)", file=sys.stderr, flush=True)

            return payload_current

        # Flujo normal (sin comparación)
        print(f"[DataAgent] Flujo normal (sin comparación)", file=sys.stderr, flush=True)

        # Paso 1: Decidir queries (con contexto de conversación)
        plan = self.decide_queries(question, date_from, date_to, chat_context)
        print(f"[DataAgent] Plan decidido: {plan.query_ids}", file=sys.stderr, flush=True)

        # Paso 2: Ejecutar
        payload = self.execute_plan(plan, date_from, date_to)
        print(f"[DataAgent] Payload generado con refs: {payload.available_refs}", file=sys.stderr, flush=True)
        print(f"[DataAgent] Payload top_items: {len(payload.top_items) if payload.top_items else 0}", file=sys.stderr, flush=True)
        print(f"[DataAgent] Payload kpis: {payload.kpis}", file=sys.stderr, flush=True)

        return payload
