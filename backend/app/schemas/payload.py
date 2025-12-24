"""
Payload schemas - Define la estructura de los datos retornados por las queries
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class DatasetMeta(BaseModel):
    """Metadata de un dataset"""
    query_id: str = Field(..., description="ID de la query ejecutada")
    row_count: int = Field(..., description="Cantidad de filas retornadas")
    execution_time_ms: float = Field(..., description="Tiempo de ejecucion en ms")
    executed_at: datetime = Field(default_factory=datetime.utcnow)


class KPIData(BaseModel):
    """Datos de KPIs - campos dinamicos"""
    # Ventas
    total_sales: Optional[float] = Field(None, description="Total de ventas")
    total_orders: Optional[int] = Field(None, description="Cantidad de ordenes")
    avg_order_value: Optional[float] = Field(None, description="Valor promedio de orden")
    total_units: Optional[int] = Field(None, description="Unidades vendidas")

    # AI Interactions
    total_interactions: Optional[int] = Field(None, description="Total interacciones AI")
    escalated_count: Optional[int] = Field(None, description="Casos escalados")
    escalation_rate: Optional[float] = Field(None, description="Tasa de escalamiento %")
    auto_responded: Optional[int] = Field(None, description="Respuestas automaticas")
    auto_response_rate: Optional[float] = Field(None, description="Tasa de respuesta automatica %")

    # Preventa
    total_queries: Optional[int] = Field(None, description="Total consultas preventa")
    answered: Optional[int] = Field(None, description="Consultas respondidas")
    pending: Optional[int] = Field(None, description="Consultas pendientes")
    answer_rate: Optional[float] = Field(None, description="Tasa de respuesta %")

    class Config:
        extra = "allow"  # Permite campos adicionales
        json_schema_extra = {
            "example": {
                "total_sales": 1500000.50,
                "total_orders": 150,
                "avg_order_value": 10000.00,
                "total_units": 320
            }
        }


class TimeSeriesPoint(BaseModel):
    """Un punto en la serie temporal"""
    date: str = Field(..., description="Fecha YYYY-MM-DD")
    value: float = Field(..., description="Valor")
    label: Optional[str] = Field(None, description="Etiqueta opcional")


class TimeSeriesData(BaseModel):
    """Datos de serie temporal"""
    series_name: str = Field(..., description="Nombre de la serie")
    points: List[TimeSeriesPoint] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "series_name": "sales_by_day",
                "points": [
                    {"date": "2024-12-01", "value": 50000},
                    {"date": "2024-12-02", "value": 75000}
                ]
            }
        }


class TopItem(BaseModel):
    """Un item del ranking"""
    rank: int = Field(..., description="Posicion en el ranking")
    id: str = Field(..., description="ID del item")
    title: str = Field(..., description="Titulo/nombre")
    value: float = Field(..., description="Valor (ventas, cantidad, etc)")
    extra: Optional[dict] = Field(None, description="Datos extra")


class TopItemsData(BaseModel):
    """Datos de top/ranking"""
    ranking_name: str = Field(..., description="Nombre del ranking")
    items: List[TopItem] = Field(default_factory=list)
    metric: str = Field("revenue", description="Metrica usada para el ranking")


class DataPayload(BaseModel):
    """Payload completo con todos los datasets"""
    kpis: Optional[KPIData] = Field(None, description="KPIs calculados")
    time_series: Optional[List[TimeSeriesData]] = Field(None, description="Series temporales")
    top_items: Optional[List[TopItemsData]] = Field(None, description="Rankings/tops")
    raw_data: Optional[List[Dict[str, Any]]] = Field(None, description="Datos crudos para tablas")

    # Metadata
    datasets_meta: List[DatasetMeta] = Field(default_factory=list)
    available_refs: List[str] = Field(
        default_factory=list,
        description="Lista de refs disponibles para el spec (kpi.total_sales, ts.sales_by_day, etc)"
    )
