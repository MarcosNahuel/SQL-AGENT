"""
DataAgent - Agente de Datos / SQL Engine

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
    DatasetMeta
)
from ..schemas.intent import QueryPlan
from ..prompts.ultrathink import get_query_decision_prompt


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
    """Agente que ejecuta queries SQL de forma segura"""

    def __init__(self):
        self.db = get_db_client()

        # Flag para usar OpenRouter como primario
        self.use_openrouter_primary = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"

        # LLM Gemini (fallback si OpenRouter es primario)
        self.llm_gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-thinking-exp"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.1  # Baja temperatura para decisiones deterministicas
        )

        # LLM OpenRouter (primario si USE_OPENROUTER_PRIMARY=true)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.llm_openrouter = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent"
                }
            )
        else:
            self.llm_openrouter = None

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

        # Top productos / Mas vendidos (ANTES de inventario para priorizar)
        elif any(kw in q_lower for kw in ["mas vendido", "más vendido", "mas vendidos", "más vendidos", "top producto", "top productos", "mejores producto", "mejores productos"]):
            query_ids = ["kpi_sales_summary", "top_products_by_revenue"]

        # Ventas / Revenue
        elif any(kw in q_lower for kw in ["venta", "factura", "ingreso", "revenue", "vendido", "vendieron", "facturado"]):
            query_ids = ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

        # Inventario / Stock (sin "vendido")
        elif any(kw in q_lower for kw in ["inventario", "stock", "existencia"]):
            if any(kw in q_lower for kw in ["bajo", "alerta", "reponer", "falta"]):
                query_ids = ["products_low_stock", "stock_alerts"]
            else:
                query_ids = ["products_inventory", "products_low_stock"]

        # Productos (generico, sin "vendido")
        elif "producto" in q_lower and not any(kw in q_lower for kw in ["vendido", "venta", "revenue"]):
            query_ids = ["products_inventory", "products_low_stock"]

        # Preventa
        elif any(kw in q_lower for kw in ["preventa", "consulta", "pregunta"]):
            query_ids = ["preventa_summary", "recent_preventa_queries"]

        # Default: mostrar KPIs de ventas
        else:
            query_ids = ["kpi_sales_summary", "recent_orders"]

        import sys
        print(f"[DataAgent] Heuristic selected: {query_ids}", file=sys.stderr)
        return QueryPlan(query_ids=query_ids, params={})

    def decide_queries(self, question: str, date_from: Optional[str], date_to: Optional[str]) -> QueryPlan:
        """
        Usa el LLM para decidir que queries ejecutar basado en la pregunta.
        El LLM SOLO puede elegir de la lista de queries disponibles.
        FORZANDO heurísticas para pruebas.
        """
        import sys
        # FORZAR heuristicas SIEMPRE para evitar problemas con el LLM
        print(f"[DataAgent] FORZANDO heuristicas para: {question[:50]}", file=sys.stderr, flush=True)
        return self._decide_queries_heuristic(question)

        # Codigo original comentado temporalmente
        demo_mode = os.getenv("DEMO_MODE", "false").strip().lower()

        available = get_available_queries()
        queries_list = "\n".join([f"- {qid}: {desc}" for qid, desc in available.items()])

        system_prompt = f"""Eres un experto en analisis de datos de e-commerce para MercadoLibre Argentina.

{BUSINESS_CONTEXT}

## QUERIES DISPONIBLES (SOLO puedes elegir de esta lista):
{queries_list}

## CONOCIMIENTO DEL ESQUEMA

### Tabla ml_orders (Ventas)
- SIEMPRE filtrar por status='paid' para ventas reales
- total_amount = monto final pagado (usar para reportes de ventas)
- date_created = fecha de la orden (usar para filtros temporales)
- shipping_type: fulfillment (Full), cross_docking (ME), drop_off, self_service

### Tabla ml_items (Productos)
- price * total_sold = revenue estimado del producto
- available_quantity < 10 = stock critico
- status='active' para productos activos

### Tablas de AI (agent_interactions, escalations)
- was_escalated=true indica casos que requirieron humano
- case_type clasifica: envio, producto, devolucion, garantia, reclamo
- source: 'preventa' (antes de comprar) o 'postventa' (despues)

## REGLAS DE SELECCION
1. SOLO responde con JSON valido (sin markdown)
2. SOLO usa query_ids de la lista de arriba
3. Elige las queries MAS RELEVANTES (max 3)
4. Para ventas: SIEMPRE incluir kpi_sales_summary

## GUIA RAPIDA:
- Ventas/facturacion: kpi_sales_summary, ts_sales_by_day, top_products_by_revenue
- Stock/inventario: products_inventory, products_low_stock, stock_alerts
- Agente AI/bot: ai_interactions_summary, recent_ai_interactions, escalated_cases
- Escalados/pendientes: escalated_cases, interactions_by_case_type
- Preventa: preventa_summary, recent_preventa_queries

FORMATO JSON (sin markdown):
{{"query_ids": ["query_id1", "query_id2"], "params": {{"limit": 10}}}}
"""

        user_msg = f"""Pregunta del usuario: "{question}"
Rango de fechas: {date_from or 'ultimos 30 dias'} a {date_to or 'hoy'}

Responde SOLO con el JSON de queries a ejecutar."""

        try:
            # Usar metodo con retry para manejar rate limits
            response = self._invoke_llm([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_msg)
            ])
        except Exception as llm_error:
            print(f"[DataAgent] LLM error, fallback to heuristics: {llm_error}")
            return self._decide_queries_heuristic(question)

        # Parsear respuesta
        import json
        import re
        try:
            # Obtener contenido
            raw_content = response.content
            print(f"[DataAgent] Raw content type: {type(raw_content)}")

            # Si es lista, buscar el primer elemento con 'text'
            if isinstance(raw_content, list):
                for part in raw_content:
                    if isinstance(part, dict) and "text" in part:
                        content = part["text"]
                        break
                    elif hasattr(part, "text"):
                        content = part.text
                        break
                    else:
                        content = str(part)
            elif isinstance(raw_content, dict) and "text" in raw_content:
                content = raw_content["text"]
            elif hasattr(raw_content, "text"):
                content = raw_content.text
            else:
                content = str(raw_content)

            content = content.strip()
            print(f"[DataAgent] Extracted content: {content[:200]}")

            # Limpiar posibles markdown
            if "```" in content:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    content = match.group(1).strip()

            # Reemplazar comillas simples por dobles
            content = content.replace("'", '"')

            plan_data = json.loads(content)

            # Validar que todas las queries existen
            valid_ids = [qid for qid in plan_data.get("query_ids", []) if validate_query_id(qid)]

            print(f"[DataAgent] Queries validas encontradas: {valid_ids}")

            if not valid_ids:
                # Fallback a queries default
                valid_ids = ["kpi_sales_summary", "ts_sales_by_day"]

            return QueryPlan(
                query_ids=valid_ids,
                params=plan_data.get("params", {})
            )
        except Exception as e:
            print(f"Error parseando respuesta LLM: {e}")
            print(f"Contenido recibido: {content[:300] if content else 'None'}")
            # Fallback seguro
            return QueryPlan(
                query_ids=["kpi_sales_summary", "ts_sales_by_day"],
                params={}
            )

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
                    if payload.raw_data is None:
                        payload.raw_data = []
                    payload.raw_data.extend(rows)
                    payload.available_refs.append(output_ref or f"table.{query_id}")

            except Exception as e:
                print(f"Error ejecutando query {query_id}: {e}")
                # Continuar con las demas queries

        return payload

    def run(self, question: str, date_from: Optional[str] = None, date_to: Optional[str] = None) -> DataPayload:
        """
        Entry point principal del DataAgent.
        1. Decide que queries ejecutar
        2. Ejecuta el plan
        3. Retorna el payload
        """
        import sys
        print(f"[DataAgent.run] Question: {question[:50]}, date_from={date_from}, date_to={date_to}", file=sys.stderr, flush=True)

        # Paso 1: Decidir queries
        plan = self.decide_queries(question, date_from, date_to)
        print(f"[DataAgent] Plan decidido: {plan.query_ids}", file=sys.stderr, flush=True)

        # Paso 2: Ejecutar
        payload = self.execute_plan(plan, date_from, date_to)
        print(f"[DataAgent] Payload generado con refs: {payload.available_refs}", file=sys.stderr, flush=True)
        print(f"[DataAgent] Payload top_items: {len(payload.top_items) if payload.top_items else 0}", file=sys.stderr, flush=True)
        print(f"[DataAgent] Payload kpis: {payload.kpis}", file=sys.stderr, flush=True)

        return payload
