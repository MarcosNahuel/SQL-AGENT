"""
Intent schemas - Define la estructura de la intencion del usuario
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


class QueryPlan(BaseModel):
    """Plan de queries a ejecutar - decidido por el LLM"""
    query_ids: List[str] = Field(
        ...,
        description="Lista de IDs de queries a ejecutar del allowlist"
    )
    params: dict = Field(
        default_factory=dict,
        description="Parametros para las queries (date_from, date_to, limit, etc)"
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
