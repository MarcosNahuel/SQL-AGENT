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

    # Inventario
    critical_count: Optional[int] = Field(None, description="Productos en estado critico")
    warning_count: Optional[int] = Field(None, description="Productos en alerta")
    ok_count: Optional[int] = Field(None, description="Productos con stock ok")
    total_products: Optional[int] = Field(None, description="Total productos")
    avg_days_cover: Optional[float] = Field(None, description="Promedio dias de cobertura")

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


class TableData(BaseModel):
    """Datos de una tabla"""
    name: str = Field(..., description="Nombre de la tabla (ej: 'recent_orders')")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Filas de datos")


class ComparisonPeriod(BaseModel):
    """Datos de un periodo en una comparación"""
    label: str = Field(..., description="Etiqueta del periodo (ej: 'Diciembre 2025')")
    date_from: str = Field(..., description="Fecha inicio ISO")
    date_to: str = Field(..., description="Fecha fin ISO")
    kpis: Optional[KPIData] = Field(None, description="KPIs del periodo")


class ComparisonData(BaseModel):
    """Datos de comparación entre dos periodos"""
    is_comparison: bool = Field(True, description="Indica que es una comparación")
    current_period: ComparisonPeriod = Field(..., description="Periodo actual/principal")
    previous_period: ComparisonPeriod = Field(..., description="Periodo anterior/comparado")
    # Deltas calculados
    delta_sales: Optional[float] = Field(None, description="Cambio en ventas (actual - anterior)")
    delta_sales_pct: Optional[float] = Field(None, description="Cambio % en ventas")
    delta_orders: Optional[int] = Field(None, description="Cambio en ordenes")
    delta_orders_pct: Optional[float] = Field(None, description="Cambio % en ordenes")
    delta_avg_order: Optional[float] = Field(None, description="Cambio en ticket promedio")
    delta_avg_order_pct: Optional[float] = Field(None, description="Cambio % en ticket promedio")
    delta_units: Optional[int] = Field(None, description="Cambio en unidades")
    delta_units_pct: Optional[float] = Field(None, description="Cambio % en unidades")


class DataPayload(BaseModel):
    """Payload completo con todos los datasets"""
    kpis: Optional[KPIData] = Field(None, description="KPIs calculados")
    time_series: Optional[List[TimeSeriesData]] = Field(None, description="Series temporales")
    top_items: Optional[List[TopItemsData]] = Field(None, description="Rankings/tops")
    tables: Optional[List[TableData]] = Field(None, description="Tablas de datos")
    raw_data: Optional[List[Dict[str, Any]]] = Field(None, description="Datos crudos (legacy)")

    # Datos de comparación
    comparison: Optional[ComparisonData] = Field(None, description="Datos de comparación entre periodos")

    # Metadata
    datasets_meta: List[DatasetMeta] = Field(default_factory=list)
    available_refs: List[str] = Field(
        default_factory=list,
        description="Lista de refs disponibles para el spec (kpi.total_sales, ts.sales_by_day, etc)"
    )
