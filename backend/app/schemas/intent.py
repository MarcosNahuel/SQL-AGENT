"""
Intent schemas - Define la estructura de la intencion del usuario

Estos modelos se usan con .with_structured_output() para garantizar
JSON válido sin necesidad de parsers manuales.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import date


class QueryRequest(BaseModel):
    """Request del usuario al sistema de insights"""
    question: str = Field(..., description="Pregunta del usuario en lenguaje natural")
    date_from: Optional[date] = Field(None, description="Fecha inicio del rango")
    date_to: Optional[date] = Field(None, description="Fecha fin del rango")
    filters: Optional[dict] = Field(default_factory=dict, description="Filtros adicionales")
    chat_context: Optional[str] = Field(None, description="Historial de conversación para contexto")


class QueryPlan(BaseModel):
    """
    Plan de queries a ejecutar - decidido por el LLM.
    Usado como Tool schema con .with_structured_output().
    """
    query_ids: List[str] = Field(
        ...,
        description="Lista de IDs de queries a ejecutar. SOLO usar IDs válidos del allowlist: "
                    "kpi_sales_summary, ts_sales_by_day, top_products_by_revenue, "
                    "products_inventory, products_low_stock, stock_alerts, kpi_inventory_summary, "
                    "ai_interactions_summary, recent_ai_interactions, escalated_cases, etc."
    )
    params: dict = Field(
        default_factory=dict,
        description="Parámetros opcionales: {limit: número máximo de filas (default 10)}"
    )


class NarrativeOutput(BaseModel):
    """
    Salida estructurada del PresentationAgent para narrativa/insights.
    Usado como Tool schema con .with_structured_output().
    """
    conclusion: str = Field(
        ...,
        description="Respuesta directa y concisa a la pregunta del usuario (1-2 oraciones). "
                    "Ejemplo: 'Las ventas de diciembre alcanzaron $4.5M, un 15% más que noviembre.'"
    )
    summary: str = Field(
        ...,
        description="Resumen ejecutivo del análisis (2-3 oraciones). "
                    "Debe contextualizar los datos principales sin repetir la conclusión."
    )
    insights: List[str] = Field(
        default_factory=list,
        description="Lista de 2-4 insights analíticos. Cada insight debe ser accionable y específico. "
                    "Ejemplo: ['El ticket promedio de $45K indica compras B2B', 'Top 3 productos concentran 60% del revenue']"
    )
    recommendation: str = Field(
        "",
        description="Recomendación accionable basada en los datos (1 oración). "
                    "Ejemplo: 'Aumentar stock del producto #1 para evitar quiebre en temporada alta.'"
    )


class RouterDecision(BaseModel):
    """
    Decisión del Router para clasificación semántica.
    Usado como Tool schema con .with_structured_output().
    """
    response_type: Literal["dashboard", "data_only", "conversational"] = Field(
        ...,
        description="Tipo de respuesta: 'dashboard' (visualización completa), "
                    "'data_only' (solo números), 'conversational' (saludo/ayuda)"
    )
    domain: Literal["sales", "inventory", "conversations"] = Field(
        "sales",
        description="Dominio de datos: 'sales' (ventas/órdenes), "
                    "'inventory' (productos/stock), 'conversations' (agente AI/escalados)"
    )
    reasoning: str = Field(
        "",
        description="Explicación breve de la clasificación"
    )


class IntentSchema(BaseModel):
    """Intent clasificado por el LLM"""
    intent_type: Literal["sales_overview", "top_products", "time_series", "mixed"] = Field(
        ...,
        description="Tipo de intent detectado"
    )
    requires_kpis: bool = Field(True, description="Si necesita KPIs")
    requires_chart: bool = Field(True, description="Si necesita graficos")
    requires_table: bool = Field(False, description="Si necesita tabla")
    query_plan: QueryPlan = Field(..., description="Plan de queries a ejecutar")
    confidence: float = Field(0.8, ge=0, le=1, description="Confianza del clasificador")
