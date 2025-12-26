"""
Charts module - Catalogo de tipos de graficos y utilidades

Uso:
    from app.charts import (
        ChartType,
        CHART_CATALOG,
        get_charts_for_data,
        recommend_charts_for_question
    )
"""
from .catalog import (
    ChartType,
    ChartDefinition,
    CHART_CATALOG,
    CHART_REF_QUERIES,
    get_chart_requirements,
    get_charts_for_data,
    get_missing_refs_for_chart,
    get_query_for_ref,
    recommend_charts_for_question,
    validate_chart_data
)

__all__ = [
    "ChartType",
    "ChartDefinition",
    "CHART_CATALOG",
    "CHART_REF_QUERIES",
    "get_chart_requirements",
    "get_charts_for_data",
    "get_missing_refs_for_chart",
    "get_query_for_ref",
    "recommend_charts_for_question",
    "validate_chart_data"
]
