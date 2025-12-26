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
    NarrativeConfig,
    ComparisonChartConfig
)
from ..schemas.intent import NarrativeOutput
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
    """
    Agente que genera la especificacion del dashboard.

    Usa .with_structured_output() para garantizar JSON válido
    sin necesidad de parsers manuales (LangGraph 2025 standard).
    """

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
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.7
        )

        # LLM con structured output para narrativa (2025 standard)
        self._structured_llm = None

    def _get_structured_llm(self):
        """
        Obtiene LLM configurado con .with_structured_output(NarrativeOutput).
        Esto garantiza JSON válido sin parsers manuales (2025 standard).
        """
        if self._structured_llm is None:
            base_llm = self.llm_openrouter if (self.use_openrouter_primary and self.llm_openrouter) else self.llm_gemini
            self._structured_llm = base_llm.with_structured_output(NarrativeOutput)
        return self._structured_llm

    def _invoke_structured(self, messages: list) -> NarrativeOutput:
        """
        Invoca el LLM con structured output para obtener NarrativeOutput directamente.
        Garantiza JSON válido sin parsers manuales (2025 standard).
        """
        structured_llm = self._get_structured_llm()

        if self.use_openrouter_primary and self.llm_openrouter:
            print(f"[PresentationAgent] Usando structured output (OpenRouter)...")
            try:
                return structured_llm.invoke(messages)
            except Exception as e:
                print(f"[PresentationAgent] Structured output error, fallback to Gemini: {e}")
                fallback_llm = self.llm_gemini.with_structured_output(NarrativeOutput)
                return fallback_llm.invoke(messages)

        try:
            return structured_llm.invoke(messages)
        except Exception as e:
            error_str = str(e)
            if self.llm_openrouter and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str):
                print(f"[PresentationAgent] Gemini rate limit, switching to OpenRouter structured...")
                fallback_llm = self.llm_openrouter.with_structured_output(NarrativeOutput)
                return fallback_llm.invoke(messages)
            raise e

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

    # NOTA: _parse_json_robust eliminado en v2.5
    # Ya no se necesita parsing manual de JSON gracias a .with_structured_output()
    # Ver: _invoke_structured() que usa NarrativeOutput directamente

    def _build_spec_heuristic(self, question: str, payload: DataPayload) -> DashboardSpec:
        """
        Construye el DashboardSpec usando heuristicas deterministicas.
        NO usa LLM para la estructura, solo para narrativa.
        """
        slots = SlotConfig()

        # === MODO COMPARACION ===
        if payload.comparison and payload.comparison.is_comparison:
            comp = payload.comparison
            # Añadir grafico de comparacion de barras para las metricas principales
            metrics_available = []
            if comp.delta_sales is not None:
                metrics_available.append("total_sales")
            if comp.delta_orders is not None:
                metrics_available.append("total_orders")
            if comp.delta_avg_order is not None:
                metrics_available.append("avg_order_value")
            if comp.delta_units is not None:
                metrics_available.append("total_units")

            if metrics_available:
                slots.charts.append(ComparisonChartConfig(
                    type="comparison_bar",
                    title=f"Comparativa: {comp.current_period.label} vs {comp.previous_period.label}",
                    current_label=comp.current_period.label,
                    previous_label=comp.previous_period.label,
                    metrics=metrics_available,
                    dataset_ref="comparison"
                ))

            # Generar KPI cards con deltas de comparacion
            kpi_configs = [
                ("Ventas", "kpi.total_sales", "currency", comp.delta_sales_pct),
                ("Ordenes", "kpi.total_orders", "number", comp.delta_orders_pct),
                ("Ticket Promedio", "kpi.avg_order_value", "currency", comp.delta_avg_order_pct),
                ("Unidades", "kpi.total_units", "number", comp.delta_units_pct),
            ]

            for label, ref, fmt, delta in kpi_configs:
                if ref in payload.available_refs:
                    trend = None
                    if delta is not None:
                        trend = "up" if delta > 0 else "down" if delta < 0 else "neutral"
                    slots.series.append(KpiCardConfig(
                        label=label,
                        value_ref=ref,
                        format=fmt,
                        delta_ref=f"comparison.delta_{ref.split('.')[-1]}_pct" if delta is not None else None
                    ))

            # Generar titulo de comparacion
            title = f"Comparativa: {comp.current_period.label} vs {comp.previous_period.label}"

            # También añadir graficos normales si hay time_series
            if payload.time_series:
                for ts in payload.time_series:
                    ref = f"ts.{ts.series_name}"
                    if ref in payload.available_refs:
                        slots.charts.append(ChartConfig(
                            type="line_chart",
                            title=f"Tendencia: {self._format_title(ts.series_name)}",
                            dataset_ref=ref,
                            x_axis="date",
                            y_axis="value"
                        ))

            # Añadir top products si hay
            if payload.top_items:
                for top in payload.top_items:
                    ref = f"top.{top.ranking_name}"
                    if ref in payload.available_refs:
                        slots.charts.append(ChartConfig(
                            type="bar_chart",
                            title=self._format_title(top.ranking_name),
                            dataset_ref=ref,
                            x_axis="title",
                            y_axis="value"
                        ))

            return DashboardSpec(
                title=title,
                subtitle=f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                slots=slots,
                generated_at=datetime.utcnow().isoformat()
            )

        # === MODO NORMAL (sin comparacion) ===
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

    def _generate_smart_narrative(self, payload: DataPayload) -> List[NarrativeConfig]:
        """
        Genera narrativas profesionales basadas en analisis de datos.
        Funciona sin LLM - analiza patrones, tendencias y anomalias.
        """
        narratives = []
        insights = []

        # === ANALISIS DE COMPARACION (si existe) ===
        if payload.comparison and payload.comparison.is_comparison:
            comp = payload.comparison
            curr = comp.current_period
            prev = comp.previous_period

            # Headline de comparación
            narratives.append(NarrativeConfig(
                type="headline",
                text=f"Comparativa: {curr.label} vs {prev.label}"
            ))

            # Analisis de ventas
            if comp.delta_sales is not None and comp.delta_sales_pct is not None:
                direction = "crecieron" if comp.delta_sales > 0 else "disminuyeron"
                emoji = "📈" if comp.delta_sales > 0 else "📉"
                abs_delta = abs(comp.delta_sales)
                abs_pct = abs(comp.delta_sales_pct)

                curr_sales = curr.kpis.total_sales if curr.kpis else 0
                prev_sales = prev.kpis.total_sales if prev.kpis else 0

                insights.append(
                    f"{emoji} Las ventas {direction} un {abs_pct:.1f}% "
                    f"(${curr_sales:,.0f} vs ${prev_sales:,.0f}), "
                    f"una diferencia de ${abs_delta:,.0f}."
                )

                # Evaluación del cambio
                if abs_pct > 30:
                    if comp.delta_sales > 0:
                        insights.append("🚀 Crecimiento excepcional. Analizar factores de éxito para replicar.")
                    else:
                        insights.append("⚠️ Caída significativa. Requiere acción inmediata.")
                elif abs_pct > 10:
                    if comp.delta_sales > 0:
                        insights.append("✅ Buen crecimiento sostenido respecto al periodo anterior.")
                    else:
                        insights.append("📊 Caída moderada. Revisar estrategia comercial.")

            # Analisis de ordenes
            if comp.delta_orders is not None and comp.delta_orders_pct is not None:
                curr_orders = curr.kpis.total_orders if curr.kpis else 0
                prev_orders = prev.kpis.total_orders if prev.kpis else 0
                direction = "aumentaron" if comp.delta_orders > 0 else "disminuyeron"
                abs_pct = abs(comp.delta_orders_pct)

                insights.append(
                    f"Las órdenes {direction} un {abs_pct:.1f}% "
                    f"({curr_orders:,} vs {prev_orders:,})."
                )

            # Analisis de ticket promedio
            if comp.delta_avg_order is not None and comp.delta_avg_order_pct is not None:
                curr_avg = curr.kpis.avg_order_value if curr.kpis else 0
                prev_avg = prev.kpis.avg_order_value if prev.kpis else 0
                direction = "subió" if comp.delta_avg_order > 0 else "bajó"
                abs_pct = abs(comp.delta_avg_order_pct)

                if abs_pct > 5:
                    insights.append(
                        f"El ticket promedio {direction} un {abs_pct:.1f}% "
                        f"(${curr_avg:,.0f} vs ${prev_avg:,.0f})."
                    )

            # Analisis de unidades
            if comp.delta_units is not None and comp.delta_units_pct is not None:
                curr_units = curr.kpis.total_units if curr.kpis else 0
                prev_units = prev.kpis.total_units if prev.kpis else 0
                direction = "aumentaron" if comp.delta_units > 0 else "disminuyeron"
                abs_pct = abs(comp.delta_units_pct)

                insights.append(
                    f"Las unidades vendidas {direction} un {abs_pct:.1f}% "
                    f"({curr_units:,} vs {prev_units:,})."
                )

            # Agregar insights de comparación
            for insight in insights[:5]:  # Máximo 5 insights
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=insight
                ))

            # Recomendación basada en comparación
            if comp.delta_sales_pct is not None:
                if comp.delta_sales_pct < -10:
                    narratives.append(NarrativeConfig(
                        type="callout",
                        text="📊 Recomendación: Revisar causas de la caída. Considerar promociones, revisión de precios o refuerzo de marketing."
                    ))
                elif comp.delta_sales_pct > 20:
                    narratives.append(NarrativeConfig(
                        type="callout",
                        text="🎯 Recomendación: Capitalizar el momentum positivo. Expandir inventario de productos estrella."
                    ))
                else:
                    narratives.append(NarrativeConfig(
                        type="callout",
                        text="💡 Recomendación: Rendimiento estable. Enfocarse en optimización y eficiencia."
                    ))

            return narratives

        # === ANALISIS DE KPIs (sin comparación) ===
        if payload.kpis:
            kpis = payload.kpis

            # Ventas - Analisis completo
            if kpis.total_sales is not None and kpis.total_orders is not None:
                total_sales = kpis.total_sales
                total_orders = kpis.total_orders
                avg_ticket = kpis.avg_order_value or (total_sales / total_orders if total_orders > 0 else 0)
                units = kpis.total_units or 0

                # Calcular metricas derivadas
                units_per_order = units / total_orders if total_orders > 0 else 0
                revenue_per_unit = total_sales / units if units > 0 else 0

                # Headline principal
                narratives.append(NarrativeConfig(
                    type="headline",
                    text=f"Facturacion de ${total_sales:,.0f} en {total_orders:,} ordenes procesadas."
                ))

                # Insight de ticket promedio
                if avg_ticket > 100000:
                    insights.append(f"Ticket promedio alto (${avg_ticket:,.0f}) indica productos de alto valor o compras en bulk.")
                elif avg_ticket > 50000:
                    insights.append(f"Ticket promedio saludable de ${avg_ticket:,.0f} con buena conversion.")
                else:
                    insights.append(f"Ticket promedio de ${avg_ticket:,.0f}. Considerar estrategias de upselling.")

                # Insight de unidades
                if units > 0:
                    if units_per_order > 2:
                        insights.append(f"Promedio de {units_per_order:.1f} unidades/orden sugiere compras multiples o bundles efectivos.")
                    else:
                        insights.append(f"{units:,} unidades vendidas. Oportunidad de incrementar items por carrito.")

            # AI Interactions
            elif kpis.total_interactions is not None:
                interactions = kpis.total_interactions
                esc_rate = kpis.escalation_rate or 0
                auto_resp = kpis.auto_responded or 0

                narratives.append(NarrativeConfig(
                    type="headline",
                    text=f"Agente AI proceso {interactions:,} interacciones con {100-esc_rate:.1f}% resolucion automatica."
                ))

                if esc_rate < 10:
                    insights.append(f"Excelente tasa de escalamiento ({esc_rate:.1f}%). El AI resuelve la mayoria de consultas.")
                elif esc_rate < 25:
                    insights.append(f"Tasa de escalamiento moderada ({esc_rate:.1f}%). Revisar casos comunes para mejorar.")
                else:
                    insights.append(f"Alta tasa de escalamiento ({esc_rate:.1f}%). Requiere entrenamiento adicional del modelo.")

        # === ANALISIS DE TENDENCIAS (Time Series) ===
        if payload.time_series:
            for ts in payload.time_series:
                if ts.points and len(ts.points) >= 2:
                    values = [p.value for p in ts.points]
                    first_val = values[0]
                    last_val = values[-1]
                    max_val = max(values)
                    min_val = min(values)
                    avg_val = sum(values) / len(values)

                    # Calcular tendencia
                    change_pct = ((last_val - first_val) / first_val * 100) if first_val > 0 else 0

                    # Detectar volatilidad
                    volatility = (max_val - min_val) / avg_val * 100 if avg_val > 0 else 0

                    # Detectar picos
                    peak_idx = values.index(max_val)
                    peak_date = ts.points[peak_idx].date if peak_idx < len(ts.points) else "N/A"

                    if "sales" in ts.series_name.lower():
                        if change_pct > 10:
                            insights.append(f"Tendencia alcista (+{change_pct:.1f}%) en el periodo. Momentum positivo de ventas.")
                        elif change_pct < -10:
                            insights.append(f"Tendencia bajista ({change_pct:.1f}%). Analizar factores de mercado y competencia.")
                        else:
                            insights.append(f"Ventas estables (variacion {change_pct:+.1f}%). Mercado en consolidacion.")

                        if volatility > 50:
                            insights.append(f"Alta volatilidad detectada. Pico maximo el {peak_date} con ${max_val:,.0f}.")

        # === ANALISIS DE TOP PRODUCTOS ===
        if payload.top_items:
            for top in payload.top_items:
                if top.items and len(top.items) >= 3:
                    items = top.items[:10]  # Top 10
                    total_top_value = sum(i.value for i in items)
                    top1_value = items[0].value
                    top3_value = sum(i.value for i in items[:3])

                    # Concentracion de ventas
                    concentration = (top1_value / total_top_value * 100) if total_top_value > 0 else 0
                    top3_concentration = (top3_value / total_top_value * 100) if total_top_value > 0 else 0

                    # Producto estrella
                    star_product = items[0].title[:50]
                    insights.append(f"Producto estrella: '{star_product}' lidera con ${top1_value:,.0f}.")

                    if concentration > 30:
                        insights.append(f"Alta concentracion ({concentration:.0f}% en #1). Diversificar para reducir riesgo.")
                    elif top3_concentration > 60:
                        insights.append(f"Top 3 concentra {top3_concentration:.0f}% de ingresos. Portafolio concentrado.")

                    # Comparar top productos
                    if len(items) >= 2:
                        gap = ((items[0].value - items[1].value) / items[1].value * 100) if items[1].value > 0 else 0
                        if gap > 50:
                            insights.append(f"Brecha significativa ({gap:.0f}%) entre #1 y #2. Lider claro del mercado.")

        # === CONSTRUIR NARRATIVAS FINALES ===

        # Agregar summary si hay insights
        if insights:
            # Tomar los 3 insights mas relevantes
            for insight in insights[:4]:
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=insight
                ))

            # Recomendacion basada en los datos
            if payload.kpis and payload.kpis.total_sales:
                if payload.time_series:
                    values = [p.value for p in payload.time_series[0].points] if payload.time_series[0].points else []
                    if values:
                        change = ((values[-1] - values[0]) / values[0] * 100) if values[0] > 0 else 0
                        if change < -5:
                            narratives.append(NarrativeConfig(
                                type="callout",
                                text="📊 Recomendacion: Revisar estrategia de pricing y promociones para revertir tendencia."
                            ))
                        elif change > 15:
                            narratives.append(NarrativeConfig(
                                type="callout",
                                text="🚀 Recomendacion: Aprovechar momentum positivo con campañas de cross-selling."
                            ))
                        else:
                            narratives.append(NarrativeConfig(
                                type="callout",
                                text="💡 Recomendacion: Mantener estrategia actual y monitorear metricas clave."
                            ))

        # Fallback si no hay narrativas
        if not narratives:
            narratives.append(NarrativeConfig(
                type="summary",
                text="Datos procesados. Revisa las visualizaciones para detalles."
            ))

        return narratives

    def _generate_demo_narrative(self, payload: DataPayload) -> List[NarrativeConfig]:
        """Wrapper para modo demo - usa smart narrative"""
        return self._generate_smart_narrative(payload)

    def generate_narrative(self, question: str, payload: DataPayload) -> tuple[List[NarrativeConfig], str]:
        """
        Usa el LLM con .with_structured_output() para generar narrativa.
        Garantiza JSON válido sin parsers manuales (2025 standard).

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

        # Prompt simplificado - structured output maneja el formato
        system_prompt = """Eres un analista de datos experto en e-commerce para MercadoLibre Argentina.
Genera insights profesionales basados en los datos proporcionados.

Tu respuesta debe incluir:
- conclusion: Respuesta directa y concisa a la pregunta (1-2 oraciones)
- summary: Resumen ejecutivo del análisis (2-3 oraciones)
- insights: Lista de 2-4 insights analíticos accionables
- recommendation: Una recomendación accionable basada en los datos"""

        user_msg = f"""Pregunta del usuario: "{question}"

Datos disponibles:
{chr(10).join(data_summary)}

Genera el análisis."""

        try:
            # Usar structured output - garantiza NarrativeOutput válido sin parsing manual
            output: NarrativeOutput = self._invoke_structured([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_msg)
            ])

            print(f"[PresentationAgent] Narrativa generada (structured output)")

            narratives = []

            # Conclusion directa (respuesta a la pregunta) - PRIMERO
            if output.conclusion:
                narratives.append(NarrativeConfig(
                    type="headline",
                    text=output.conclusion
                ))

            # Summary ejecutivo
            if output.summary:
                narratives.append(NarrativeConfig(
                    type="summary",
                    text=output.summary
                ))

            # Insights detallados
            for insight in output.insights:
                narratives.append(NarrativeConfig(
                    type="insight",
                    text=insight
                ))

            # Recomendacion accionable
            if output.recommendation:
                narratives.append(NarrativeConfig(
                    type="callout",
                    text=f"💡 {output.recommendation}"
                ))

            return narratives, output.conclusion

        except Exception as e:
            print(f"[PresentationAgent] Structured output error, using fallback: {e}")
            # Usar analisis inteligente sin LLM como fallback
            narratives = self._generate_smart_narrative(payload)
            conclusion = self._generate_quick_conclusion(question, payload)
            return narratives, conclusion

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
