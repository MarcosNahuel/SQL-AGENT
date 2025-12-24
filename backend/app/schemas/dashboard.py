"""
Dashboard Spec schemas - Define la estructura del JSON que renderiza el frontend
"""
from typing import Optional, List, Literal, Union
from pydantic import BaseModel, Field


class KpiCardConfig(BaseModel):
    """Configuracion de una tarjeta KPI"""
    type: Literal["kpi_card"] = "kpi_card"
    label: str = Field(..., description="Etiqueta del KPI")
    value_ref: str = Field(..., description="Referencia al valor (ej: kpi.total_sales)")
    format: Literal["currency", "number", "percent"] = Field("number")
    delta_ref: Optional[str] = Field(None, description="Referencia al delta/cambio")
    icon: Optional[str] = Field(None, description="Icono opcional")


class ChartConfig(BaseModel):
    """Configuracion de un grafico"""
    type: Literal["line_chart", "bar_chart", "area_chart"] = Field(...)
    title: str = Field(..., description="Titulo del grafico")
    dataset_ref: str = Field(..., description="Referencia al dataset (ej: ts.sales_by_day)")
    x_axis: str = Field("date", description="Campo para eje X")
    y_axis: str = Field("value", description="Campo para eje Y")
    color: Optional[str] = Field(None, description="Color del grafico")


class TableConfig(BaseModel):
    """Configuracion de una tabla"""
    type: Literal["table"] = "table"
    title: str = Field(..., description="Titulo de la tabla")
    dataset_ref: str = Field(..., description="Referencia al dataset")
    columns: List[str] = Field(..., description="Columnas a mostrar")
    max_rows: int = Field(10, description="Maximo de filas")


class NarrativeConfig(BaseModel):
    """Configuracion de un bloque narrativo"""
    type: Literal["headline", "insight", "callout", "summary"] = "summary"
    text: str = Field(..., description="Contenido del texto")
    icon: Optional[str] = Field(None, description="Icono opcional")


class SlotConfig(BaseModel):
    """Configuracion de slots del dashboard"""
    filters: List[dict] = Field(default_factory=list, description="Filtros activos")
    series: List[KpiCardConfig] = Field(default_factory=list, description="KPI cards")
    charts: List[Union[ChartConfig, TableConfig]] = Field(default_factory=list, description="Graficos y tablas")
    narrative: List[NarrativeConfig] = Field(default_factory=list, description="Narrativa/insights")


class DashboardSpec(BaseModel):
    """Especificacion completa del dashboard - Lo que renderiza el frontend"""
    title: str = Field(..., description="Titulo del dashboard")
    subtitle: Optional[str] = Field(None, description="Subtitulo")
    conclusion: Optional[str] = Field(None, description="Conclusion corta para mostrar en chat")
    slots: SlotConfig = Field(..., description="Contenido de los slots")
    generated_at: Optional[str] = Field(None, description="Timestamp de generacion")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Resumen de Ventas",
                "subtitle": "Ultimos 30 dias",
                "slots": {
                    "filters": [{"type": "date_range", "from": "2024-12-01", "to": "2024-12-19"}],
                    "series": [
                        {"type": "kpi_card", "label": "Ventas Totales", "value_ref": "kpi.total_sales", "format": "currency"}
                    ],
                    "charts": [
                        {"type": "line_chart", "title": "Ventas por Dia", "dataset_ref": "ts.sales_by_day", "x_axis": "date", "y_axis": "value"}
                    ],
                    "narrative": [
                        {"type": "summary", "text": "Las ventas muestran una tendencia positiva..."}
                    ]
                }
            }
        }
