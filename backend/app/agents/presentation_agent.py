"""
PresentationAgent - Agente de Presentacion

Responsabilidades:
- Recibir DataPayload con datasets disponibles
- Generar DashboardSpec con los slots fijos
- Generar narrativa/insights basados en los datos
- Validar que todos los refs existan en el payload
"""
import os
import json
import time
from typing import Optional, List, Callable, Any
from datetime import datetime
from functools import wraps

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..schemas.payload import DataPayload
from ..schemas.dashboard import (
    DashboardSpec,
    SlotConfig,
    KpiCardConfig,
    ChartConfig,
    TableConfig,
    NarrativeConfig
)
from ..prompts.ultrathink import get_narrative_prompt


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 60.0):
    """
    Decorator para reintentar llamadas LLM con backoff exponencial.
    Maneja errores 429 (rate limit) de Gemini API.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e)

                    # Check if it's a rate limit error
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                        # Extract retry delay from error if available
                        delay = base_delay * (2 ** attempt)

                        # Try to parse suggested delay from error message
                        import re
                        match = re.search(r'retry\s+in\s+(\d+(?:\.\d+)?)', error_str.lower())
                        if match:
                            suggested_delay = float(match.group(1))
                            delay = min(suggested_delay + 1, max_delay)

                        delay = min(delay, max_delay)

                        if attempt < max_retries - 1:
                            print(f"[Retry] Rate limit hit. Waiting {delay:.1f}s before retry {attempt + 2}/{max_retries}")
                            time.sleep(delay)
                        else:
                            print(f"[Retry] Max retries ({max_retries}) exceeded for rate limit")
                    else:
                        # Non-rate-limit error, don't retry
                        raise e

            # If we exhausted all retries, raise the last exception
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


class PresentationAgent:
    """Agente que genera la especificacion del dashboard"""

    def __init__(self):
        # Determinar si usar OpenRouter como primario
        self.use_openrouter_primary = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        # LLM OpenRouter (puede ser primario o fallback)
        if openrouter_key:
            self.llm_openrouter = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.7,
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent"
                }
            )
        else:
            self.llm_openrouter = None

        # LLM Gemini (fallback si OpenRouter es primario)
        self.llm_gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-thinking-exp"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.7
        )

    def _invoke_llm(self, messages: list) -> str:
        """Invoca el LLM - OpenRouter primario si esta configurado"""
        # Si OpenRouter es primario y esta disponible
        if self.use_openrouter_primary and self.llm_openrouter:
            try:
                print(f"[PresentationAgent] Usando OpenRouter (google/gemini-3-flash-preview)...")
                response = self.llm_openrouter.invoke(messages)
                return response.content
            except Exception as e:
                print(f"[PresentationAgent] OpenRouter error: {e}")
                # Fallback a Gemini
                print(f"[PresentationAgent] Fallback a Gemini...")
                response = self.llm_gemini.invoke(messages)
                return response.content
        else:
            # Gemini primario con OpenRouter fallback
            try:
                response = self.llm_gemini.invoke(messages)
                return response.content
            except Exception as e:
                error_str = str(e)
                if self.llm_openrouter and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower()):
                    print(f"[PresentationAgent] Gemini rate limit, switching to OpenRouter...")
                    response = self.llm_openrouter.invoke(messages)
                    return response.content
                raise e

    def _build_spec_heuristic(self, question: str, payload: DataPayload) -> DashboardSpec:
        """
        Construye el DashboardSpec usando heuristicas deterministicas.
        NO usa LLM para la estructura, solo para narrativa.
        """
        slots = SlotConfig()

        # 1. KPIs (si hay datos de KPI)
        if payload.kpis:
            # Mapeo de todos los KPIs posibles
            all_kpis = [
                # Ventas
                ("Ventas Totales", "kpi.total_sales", "currency"),
                ("Ordenes", "kpi.total_orders", "number"),
                ("Ticket Promedio", "kpi.avg_order_value", "currency"),
                ("Unidades", "kpi.total_units", "number"),
                # AI Interactions
                ("Total Interacciones", "kpi.total_interactions", "number"),
                ("Casos Escalados", "kpi.escalated_count", "number"),
                ("Tasa Escalamiento", "kpi.escalation_rate", "percent"),
                ("Auto-Respondidas", "kpi.auto_responded", "number"),
                ("Tasa Auto-Respuesta", "kpi.auto_response_rate", "percent"),
                # Preventa
                ("Consultas Totales", "kpi.total_queries", "number"),
                ("Respondidas", "kpi.answered", "number"),
                ("Pendientes", "kpi.pending", "number"),
                ("Tasa Respuesta", "kpi.answer_rate", "percent"),
            ]
            for label, ref, fmt in all_kpis:
                if ref in payload.available_refs:
                    slots.series.append(KpiCardConfig(
                        label=label,
                        value_ref=ref,
                        format=fmt
                    ))

        # 2. Graficos (basado en lo disponible)
        if payload.time_series:
            for ts in payload.time_series:
                ref = f"ts.{ts.series_name}"
                if ref in payload.available_refs or f"ts.{ts.series_name}" in payload.available_refs:
                    # Determinar tipo de grafico
                    chart_type = "line_chart"
                    if "revenue" in ts.series_name.lower():
                        chart_type = "area_chart"

                    slots.charts.append(ChartConfig(
                        type=chart_type,
                        title=self._format_title(ts.series_name),
                        dataset_ref=ref,
                        x_axis="date",
                        y_axis="value"
                    ))

        # 3. Rankings/Tops
        if payload.top_items:
            for top in payload.top_items:
                ref = f"top.{top.ranking_name}"
                if ref in payload.available_refs or f"top.{top.ranking_name}" in payload.available_refs:
                    slots.charts.append(ChartConfig(
                        type="bar_chart",
                        title=self._format_title(top.ranking_name),
                        dataset_ref=ref,
                        x_axis="title",
                        y_axis="value"
                    ))

        # 4. Tablas (si hay raw_data)
        if payload.raw_data:
            # Inferir columnas del primer row
            columns = list(payload.raw_data[0].keys()) if payload.raw_data else []
            slots.charts.append(TableConfig(
                title="Datos Detallados",
                dataset_ref="table.recent_orders",
                columns=columns[:5],  # Max 5 columnas
                max_rows=10
            ))

        # Generar titulo basado en la pregunta
        title = self._generate_title(question)

        return DashboardSpec(
            title=title,
            subtitle=f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            slots=slots,
            generated_at=datetime.utcnow().isoformat()
        )

    def _format_title(self, name: str) -> str:
        """Formatea un nombre de dataset a titulo legible"""
        return name.replace("_", " ").replace(".", " ").title()

    def _generate_title(self, question: str) -> str:
        """Genera un titulo para el dashboard basado en la pregunta"""
        q_lower = question.lower()
        if "venta" in q_lower:
            return "Dashboard de Ventas"
        elif "producto" in q_lower:
            return "Analisis de Productos"
        elif "orden" in q_lower or "pedido" in q_lower:
            return "Resumen de Ordenes"
        else:
            return "Dashboard de Insights"

    def _generate_demo_narrative(self, payload: DataPayload) -> List[NarrativeConfig]:
        """Genera narrativas estaticas para modo demo"""
        narratives = []

        # Headline basado en los datos disponibles
        if payload.kpis:
            kpis = payload.kpis
            # Ventas
            if kpis.total_orders is not None:
                avg_val = kpis.avg_order_value or 0
                narratives.append(NarrativeConfig(
                    type="headline",
                    text="Las ventas muestran un comportamiento estable con oportunidades de crecimiento."
                ))
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=f"Se registraron {kpis.total_orders} ordenes con un ticket promedio de ${avg_val:,.0f}."
                ))
            # AI Interactions
            elif kpis.total_interactions is not None:
                esc_rate = kpis.escalation_rate or 0
                narratives.append(NarrativeConfig(
                    type="headline",
                    text=f"El agente AI procesó {kpis.total_interactions} interacciones."
                ))
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=f"Tasa de escalamiento: {esc_rate:.1f}%. Auto-respuestas: {kpis.auto_responded or 0}."
                ))
            # Preventa
            elif kpis.total_queries is not None:
                ans_rate = kpis.answer_rate or 0
                narratives.append(NarrativeConfig(
                    type="headline",
                    text=f"Se recibieron {kpis.total_queries} consultas de preventa."
                ))
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=f"Tasa de respuesta: {ans_rate:.1f}%. Pendientes: {kpis.pending or 0}."
                ))

        if payload.top_items and payload.top_items[0].items:
            top_product = payload.top_items[0].items[0]
            narratives.append(NarrativeConfig(
                type="insight",
                text=f"Top item: '{top_product.title}' con valor ${top_product.value:,.0f}."
            ))

        if not narratives:
            narratives.append(NarrativeConfig(
                type="summary",
                text="Datos cargados correctamente."
            ))

        return narratives

    def generate_narrative(self, question: str, payload: DataPayload) -> tuple[List[NarrativeConfig], str]:
        """
        Usa el LLM para generar narrativa/insights basados en los datos.
        En DEMO_MODE retorna narrativas estaticas.

        Returns:
            Tuple de (narrativas, conclusion) para evitar estado compartido.
        """
        # Check for demo mode - skip LLM call
        if os.getenv("DEMO_MODE", "false").lower() == "true":
            narratives = self._generate_demo_narrative(payload)
            return narratives, ""

        # Preparar resumen de datos para el LLM
        data_summary = []

        if payload.kpis:
            kpis = payload.kpis
            kpi_parts = []
            if kpis.total_sales is not None:
                kpi_parts.append(f"Ventas=${kpis.total_sales:,.2f}")
            if kpis.total_orders is not None:
                kpi_parts.append(f"Ordenes={kpis.total_orders}")
            if kpis.avg_order_value is not None:
                kpi_parts.append(f"Ticket Promedio=${kpis.avg_order_value:,.2f}")
            if kpis.total_interactions is not None:
                kpi_parts.append(f"Interacciones AI={kpis.total_interactions}")
            if kpis.escalation_rate is not None:
                kpi_parts.append(f"Tasa Escalamiento={kpis.escalation_rate:.1f}%")
            if kpis.total_queries is not None:
                kpi_parts.append(f"Consultas Preventa={kpis.total_queries}")
            if kpi_parts:
                data_summary.append(f"KPIs: {', '.join(kpi_parts)}")

        if payload.time_series:
            for ts in payload.time_series:
                if ts.points:
                    first_val = ts.points[0].value if ts.points else 0
                    last_val = ts.points[-1].value if ts.points else 0
                    change = ((last_val - first_val) / first_val * 100) if first_val else 0
                    data_summary.append(f"Serie {ts.series_name}: {len(ts.points)} puntos, "
                                      f"cambio {change:+.1f}%")

        if payload.top_items:
            for top in payload.top_items:
                if top.items:
                    top_item = top.items[0]
                    data_summary.append(f"Top {top.ranking_name}: #1 es '{top_item.title}' "
                                      f"con ${top_item.value:,.2f}")

        # Usar prompt UltraThink mejorado
        system_prompt = get_narrative_prompt()

        user_msg = f"""Pregunta del usuario: "{question}"

Datos disponibles:
{chr(10).join(data_summary)}

Genera insights basados en estos datos."""

        try:
            # Usar metodo con retry para manejar rate limits
            raw_content = self._invoke_llm([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_msg)
            ])

            # Parsear respuesta (manejar diferentes formatos)
            import re
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
            else:
                content = str(raw_content)

            content = content.strip()
            if "```" in content:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    content = match.group(1).strip()

            narrative_data = json.loads(content)

            narratives = []

            # Conclusion directa (respuesta a la pregunta) - PRIMERO
            if narrative_data.get("conclusion"):
                narratives.append(NarrativeConfig(
                    type="headline",
                    text=narrative_data["conclusion"]
                ))

            # Summary ejecutivo
            if narrative_data.get("summary"):
                narratives.append(NarrativeConfig(
                    type="summary",
                    text=narrative_data["summary"]
                ))

            # Insights detallados
            for insight in narrative_data.get("insights", []):
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=insight
                ))

            # Recomendacion accionable
            if narrative_data.get("recommendation"):
                narratives.append(NarrativeConfig(
                    type="callout",
                    text=f"💡 {narrative_data['recommendation']}"
                ))

            # Retornar tupla (narrativas, conclusion) - evita race condition
            conclusion = narrative_data.get("conclusion", "")
            return narratives, conclusion

        except Exception as e:
            print(f"Error generando narrativa: {e}")
            return [NarrativeConfig(
                type="summary",
                text="Datos cargados correctamente. Revisa los graficos para mas detalles."
            )], ""

    def validate_refs(self, spec: DashboardSpec, available_refs: List[str]) -> DashboardSpec:
        """
        Valida que todas las refs en el spec existan en el payload.
        Remueve componentes con refs invalidas.
        """
        # Filtrar KPIs
        valid_series = [
            kpi for kpi in spec.slots.series
            if kpi.value_ref in available_refs
        ]
        spec.slots.series = valid_series

        # Filtrar charts
        valid_charts = []
        for chart in spec.slots.charts:
            if isinstance(chart, (ChartConfig, TableConfig)):
                # Verificar que el ref base existe
                ref_base = chart.dataset_ref.split(".")[0] + "."
                if any(ref.startswith(ref_base) or ref == chart.dataset_ref for ref in available_refs):
                    valid_charts.append(chart)
        spec.slots.charts = valid_charts

        return spec

    def run(self, question: str, payload: DataPayload) -> DashboardSpec:
        """
        Entry point principal del PresentationAgent.
        1. Construye el spec con heuristicas
        2. Genera narrativa con LLM (ULTRATHINK)
        3. Valida refs
        4. Asegura minimo 2 graficos
        5. Retorna spec final con conclusion
        """
        # Paso 1: Construir spec
        spec = self._build_spec_heuristic(question, payload)
        print(f"[PresentationAgent] Spec base generado: {len(spec.slots.series)} KPIs, "
              f"{len(spec.slots.charts)} charts")

        # Paso 2: Generar narrativa con ULTRATHINK (retorna tupla para evitar race condition)
        narratives, conclusion = self.generate_narrative(question, payload)
        spec.slots.narrative = narratives
        print(f"[PresentationAgent] Narrativa generada: {len(narratives)} bloques")

        # Paso 3: Validar refs
        spec = self.validate_refs(spec, payload.available_refs)

        # Paso 4: Asegurar minimo 2 graficos distintos
        spec = self._ensure_two_charts(spec, payload)
        print(f"[PresentationAgent] Spec validado: {len(spec.slots.series)} KPIs, "
              f"{len(spec.slots.charts)} charts validos")

        # Paso 5: Agregar conclusion al spec (usando variable local, no instancia)
        spec.conclusion = conclusion if conclusion else self._generate_quick_conclusion(question, payload)

        return spec

    def _ensure_two_charts(self, spec: DashboardSpec, payload: DataPayload) -> DashboardSpec:
        """
        Asegura que el dashboard tenga al menos 2 graficos de tipos distintos.
        Si solo hay 1, intenta generar otro complementario.
        """
        charts = spec.slots.charts
        chart_types = set()

        for chart in charts:
            if hasattr(chart, 'type') and chart.type != 'table':
                chart_types.add(chart.type)

        # Si ya tenemos 2+ graficos de tipos distintos, OK
        if len(chart_types) >= 2 and len([c for c in charts if hasattr(c, 'type') and c.type != 'table']) >= 2:
            return spec

        # Necesitamos agregar graficos complementarios
        has_line = 'line_chart' in chart_types or 'area_chart' in chart_types
        has_bar = 'bar_chart' in chart_types

        # Si tenemos time_series pero no grafico de linea, agregar
        if not has_line and payload.time_series:
            ts = payload.time_series[0]
            spec.slots.charts.insert(0, ChartConfig(
                type="area_chart",
                title=f"Tendencia: {self._format_title(ts.series_name)}",
                dataset_ref=f"ts.{ts.series_name}",
                x_axis="date",
                y_axis="value",
                color="#3b82f6"
            ))

        # Si tenemos top_items pero no grafico de barras, agregar
        if not has_bar and payload.top_items:
            top = payload.top_items[0]
            spec.slots.charts.append(ChartConfig(
                type="bar_chart",
                title=f"Ranking: {self._format_title(top.ranking_name)}",
                dataset_ref=f"top.{top.ranking_name}",
                x_axis="title",
                y_axis="value",
                color="#10b981"
            ))

        return spec

    def _generate_quick_conclusion(self, question: str, payload: DataPayload) -> str:
        """Genera una conclusion rapida basada en los datos si el LLM no la genero"""
        if payload.kpis:
            if payload.kpis.total_sales:
                return f"Ventas totales: ${payload.kpis.total_sales:,.0f} con {payload.kpis.total_orders or 0} ordenes"
            if payload.kpis.total_interactions:
                return f"El agente AI proceso {payload.kpis.total_interactions} interacciones"
            if payload.kpis.total_queries:
                return f"Se registraron {payload.kpis.total_queries} consultas de preventa"
        return "Datos procesados correctamente"
