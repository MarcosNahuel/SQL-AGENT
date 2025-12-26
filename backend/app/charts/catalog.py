"""
Chart Catalog - Definiciones de tipos de graficos y sus requerimientos

Cada tipo de grafico define:
- required_vars: Variables que DEBE tener para renderizar
- optional_vars: Variables que mejoran el grafico pero no son criticas
- description: Descripcion de uso
- best_for: Casos de uso ideales
- query_mapping: Mapeo de ref a query_id del allowlist

Uso:
    from app.charts.catalog import CHART_CATALOG, get_chart_requirements, validate_chart_data
"""
from typing import List, Dict, Optional, Literal, TypedDict
from dataclasses import dataclass, field
from enum import Enum


class ChartType(str, Enum):
    """Tipos de graficos soportados"""
    LINE_CHART = "line_chart"
    AREA_CHART = "area_chart"
    BAR_CHART = "bar_chart"
    VERTICAL_BAR_CHART = "vertical_bar_chart"
    PIE_CHART = "pie_chart"
    DONUT_CHART = "donut_chart"
    COMPARISON_BAR = "comparison_bar"
    SCATTER_PLOT = "scatter_plot"
    FUNNEL_CHART = "funnel_chart"
    HEATMAP = "heatmap"


@dataclass
class ChartDefinition:
    """Definicion completa de un tipo de grafico"""
    type: ChartType
    description: str
    best_for: List[str]
    required_vars: List[str]  # Refs requeridas (ej: "ts.*", "top.*")
    optional_vars: List[str] = field(default_factory=list)
    config_template: Dict = field(default_factory=dict)
    example_refs: List[str] = field(default_factory=list)


# ============== CATALOGO DE GRAFICOS ==============

CHART_CATALOG: Dict[ChartType, ChartDefinition] = {

    ChartType.LINE_CHART: ChartDefinition(
        type=ChartType.LINE_CHART,
        description="Grafico de lineas para mostrar tendencias temporales",
        best_for=[
            "Evolucion de ventas en el tiempo",
            "Tendencias de ordenes diarias/semanales",
            "Seguimiento de metricas a lo largo del tiempo"
        ],
        required_vars=["ts.*"],  # Cualquier time_series
        optional_vars=["kpi.*"],  # KPIs para contexto
        config_template={
            "type": "line_chart",
            "x_axis": "date",
            "y_axis": "value"
        },
        example_refs=["ts.sales_by_day", "ts.orders_by_week", "ts.revenue_by_month"]
    ),

    ChartType.AREA_CHART: ChartDefinition(
        type=ChartType.AREA_CHART,
        description="Grafico de area para mostrar volumen acumulado",
        best_for=[
            "Volumen de ventas con enfasis en magnitud",
            "Revenue acumulado",
            "Metricas donde el area bajo la curva importa"
        ],
        required_vars=["ts.*"],
        optional_vars=["kpi.*"],
        config_template={
            "type": "area_chart",
            "x_axis": "date",
            "y_axis": "value",
            "fill_opacity": 0.3
        },
        example_refs=["ts.sales_by_day", "ts.cumulative_revenue"]
    ),

    ChartType.BAR_CHART: ChartDefinition(
        type=ChartType.BAR_CHART,
        description="Barras horizontales para rankings y comparativas de items",
        best_for=[
            "Top productos por revenue",
            "Ranking de categorias",
            "Comparar items ordenados por valor"
        ],
        required_vars=["top.*"],  # Cualquier top_items
        optional_vars=[],
        config_template={
            "type": "bar_chart",
            "x_axis": "title",
            "y_axis": "value",
            "layout": "horizontal"
        },
        example_refs=["top.products_by_revenue", "top.categories", "top.stock_reorder"]
    ),

    ChartType.VERTICAL_BAR_CHART: ChartDefinition(
        type=ChartType.VERTICAL_BAR_CHART,
        description="Barras verticales para comparar categorias",
        best_for=[
            "Ventas por region",
            "Ordenes por canal",
            "Comparar categorias discretas"
        ],
        required_vars=["cat.*"],  # Categories data
        optional_vars=["kpi.*"],
        config_template={
            "type": "vertical_bar_chart",
            "x_axis": "category",
            "y_axis": "value"
        },
        example_refs=["cat.sales_by_region", "cat.orders_by_channel"]
    ),

    ChartType.PIE_CHART: ChartDefinition(
        type=ChartType.PIE_CHART,
        description="Grafico de torta para mostrar distribucion proporcional",
        best_for=[
            "Distribucion de ventas por categoria",
            "Proporcion de ordenes por estado",
            "Mostrar partes de un todo (max 6-8 segmentos)"
        ],
        required_vars=["dist.*"],  # Distribution data
        optional_vars=[],
        config_template={
            "type": "pie_chart",
            "max_segments": 8
        },
        example_refs=["dist.sales_by_category", "dist.orders_by_status"]
    ),

    ChartType.DONUT_CHART: ChartDefinition(
        type=ChartType.DONUT_CHART,
        description="Dona con KPI central para distribucion con metrica destacada",
        best_for=[
            "Estado de inventario con total en centro",
            "Distribucion con metrica principal visible",
            "Dashboard ejecutivo"
        ],
        required_vars=["dist.*", "kpi.*"],
        optional_vars=[],
        config_template={
            "type": "donut_chart",
            "center_metric": "total"
        },
        example_refs=["dist.inventory_status", "dist.order_status"]
    ),

    ChartType.COMPARISON_BAR: ChartDefinition(
        type=ChartType.COMPARISON_BAR,
        description="Barras comparativas entre dos periodos",
        best_for=[
            "Comparar ventas mes actual vs anterior",
            "Analisis year-over-year",
            "Evaluar crecimiento entre periodos"
        ],
        required_vars=["comparison.*"],
        optional_vars=["ts.*"],  # Para mostrar tendencia adicional
        config_template={
            "type": "comparison_bar",
            "metrics": ["total_sales", "total_orders", "avg_order_value"]
        },
        example_refs=["comparison.sales_periods", "comparison.yoy"]
    ),

    ChartType.SCATTER_PLOT: ChartDefinition(
        type=ChartType.SCATTER_PLOT,
        description="Diagrama de dispersion para correlacion entre variables",
        best_for=[
            "Relacion precio vs unidades vendidas",
            "Correlacion entre metricas",
            "Identificar outliers y clusters"
        ],
        required_vars=["scatter.*"],
        optional_vars=[],
        config_template={
            "type": "scatter_plot",
            "x_axis": "x",
            "y_axis": "y",
            "size_var": "size"
        },
        example_refs=["scatter.price_vs_units", "scatter.margin_vs_volume"]
    ),

    ChartType.FUNNEL_CHART: ChartDefinition(
        type=ChartType.FUNNEL_CHART,
        description="Embudo para visualizar etapas de conversion",
        best_for=[
            "Pipeline de ventas",
            "Conversion de carrito a compra",
            "Etapas de proceso con drop-off"
        ],
        required_vars=["funnel.*"],
        optional_vars=["kpi.*"],
        config_template={
            "type": "funnel_chart",
            "show_conversion_rate": True
        },
        example_refs=["funnel.sales_pipeline", "funnel.checkout"]
    ),

    ChartType.HEATMAP: ChartDefinition(
        type=ChartType.HEATMAP,
        description="Mapa de calor para patrones bidimensionales",
        best_for=[
            "Ventas por hora y dia de semana",
            "Actividad por tiempo",
            "Identificar patrones estacionales"
        ],
        required_vars=["heat.*"],
        optional_vars=[],
        config_template={
            "type": "heatmap",
            "x_axis": "col",
            "y_axis": "row",
            "value": "intensity"
        },
        example_refs=["heat.sales_by_hour_day", "heat.activity_pattern"]
    )
}


# ============== MAPEO DE REFS A QUERIES ==============

CHART_REF_QUERIES: Dict[str, str] = {
    # Time Series
    "ts.sales_by_day": "ts_sales_by_day",
    "ts.sales_by_week": "ts_sales_by_week",
    "ts.sales_by_month": "ts_sales_by_month",
    "ts.orders_by_day": "ts_orders_by_day",
    "ts.revenue_by_month": "ts_revenue_by_month",

    # Top Items / Rankings
    "top.products_by_revenue": "top_products_by_revenue",
    "top.products_by_units": "top_products_by_units",
    "top.categories": "top_categories_by_revenue",
    "top.stock_reorder": "stock_reorder_analysis",

    # Distribution
    "dist.sales_by_category": "distribution_sales_category",
    "dist.orders_by_status": "distribution_order_status",
    "dist.inventory_status": "kpi_inventory_summary",

    # Categories
    "cat.sales_by_region": "sales_by_region",
    "cat.orders_by_channel": "orders_by_channel",

    # Comparison
    "comparison.sales_periods": "comparison_periods",

    # Scatter
    "scatter.price_vs_units": "scatter_price_units",

    # Funnel
    "funnel.sales_pipeline": "funnel_sales",

    # Heatmap
    "heat.sales_by_hour_day": "heatmap_hourly_sales"
}


# ============== FUNCIONES DE UTILIDAD ==============

def get_chart_requirements(chart_type: ChartType) -> ChartDefinition:
    """Obtiene la definicion de un tipo de grafico"""
    return CHART_CATALOG.get(chart_type)


def get_charts_for_data(available_refs: List[str]) -> List[ChartDefinition]:
    """
    Retorna los tipos de graficos que pueden renderizarse con los datos disponibles.

    Args:
        available_refs: Lista de refs disponibles (ej: ["kpi.total_sales", "ts.sales_by_day"])

    Returns:
        Lista de ChartDefinition que tienen sus required_vars satisfechas
    """
    compatible_charts = []

    for chart_def in CHART_CATALOG.values():
        # Check if all required vars have at least one match
        all_required_satisfied = True

        for req_pattern in chart_def.required_vars:
            # Pattern can be "ts.*" or specific "ts.sales_by_day"
            if req_pattern.endswith(".*"):
                prefix = req_pattern[:-1]  # Remove "*"
                has_match = any(ref.startswith(prefix) for ref in available_refs)
            else:
                has_match = req_pattern in available_refs

            if not has_match:
                all_required_satisfied = False
                break

        if all_required_satisfied:
            compatible_charts.append(chart_def)

    return compatible_charts


def get_missing_refs_for_chart(
    chart_type: ChartType,
    available_refs: List[str]
) -> List[str]:
    """
    Identifica que refs faltan para poder renderizar un tipo de grafico.

    Args:
        chart_type: Tipo de grafico deseado
        available_refs: Refs actualmente disponibles

    Returns:
        Lista de refs faltantes (o patrones como "ts.*" si necesita cualquier time_series)
    """
    chart_def = CHART_CATALOG.get(chart_type)
    if not chart_def:
        return []

    missing = []
    for req_pattern in chart_def.required_vars:
        if req_pattern.endswith(".*"):
            prefix = req_pattern[:-1]
            has_match = any(ref.startswith(prefix) for ref in available_refs)
            if not has_match:
                # Suggest a specific example ref
                example = next(
                    (ex for ex in chart_def.example_refs if ex.startswith(prefix)),
                    req_pattern
                )
                missing.append(example)
        else:
            if req_pattern not in available_refs:
                missing.append(req_pattern)

    return missing


def get_query_for_ref(ref: str) -> Optional[str]:
    """
    Obtiene el query_id del allowlist para una ref especifica.

    Args:
        ref: Referencia de datos (ej: "ts.sales_by_day")

    Returns:
        query_id si existe, None si no esta mapeado
    """
    return CHART_REF_QUERIES.get(ref)


def recommend_charts_for_question(
    question: str,
    domain: Optional[str] = None
) -> List[ChartType]:
    """
    Recomienda tipos de graficos basado en la pregunta del usuario.

    Args:
        question: Pregunta del usuario
        domain: Dominio detectado (sales, inventory, etc)

    Returns:
        Lista ordenada de tipos de grafico recomendados
    """
    q_lower = question.lower()
    recommendations = []

    # Tendencias temporales
    if any(kw in q_lower for kw in ["tendencia", "evolucion", "tiempo", "dias", "semanas"]):
        recommendations.extend([ChartType.LINE_CHART, ChartType.AREA_CHART])

    # Rankings
    if any(kw in q_lower for kw in ["top", "mejores", "ranking", "mas vendidos"]):
        recommendations.append(ChartType.BAR_CHART)

    # Comparaciones
    if any(kw in q_lower for kw in ["comparar", "vs", "versus", "anterior", "crecimiento"]):
        recommendations.append(ChartType.COMPARISON_BAR)

    # Distribucion
    if any(kw in q_lower for kw in ["distribucion", "proporcion", "porcentaje", "por categoria"]):
        recommendations.extend([ChartType.PIE_CHART, ChartType.DONUT_CHART])

    # Patrones
    if any(kw in q_lower for kw in ["patron", "horario", "cuando", "mejor hora"]):
        recommendations.append(ChartType.HEATMAP)

    # Conversion / Funnel
    if any(kw in q_lower for kw in ["conversion", "funnel", "etapas", "pipeline"]):
        recommendations.append(ChartType.FUNNEL_CHART)

    # Correlacion
    if any(kw in q_lower for kw in ["correlacion", "relacion", "precio vs"]):
        recommendations.append(ChartType.SCATTER_PLOT)

    # Defaults por dominio
    if not recommendations:
        if domain == "sales":
            recommendations = [ChartType.LINE_CHART, ChartType.BAR_CHART]
        elif domain == "inventory":
            recommendations = [ChartType.BAR_CHART, ChartType.DONUT_CHART]
        else:
            recommendations = [ChartType.LINE_CHART, ChartType.BAR_CHART]

    # Eliminar duplicados manteniendo orden
    seen = set()
    unique = []
    for chart in recommendations:
        if chart not in seen:
            seen.add(chart)
            unique.append(chart)

    return unique[:3]  # Max 3 recomendaciones


# ============== VALIDACION ==============

def validate_chart_data(
    chart_type: ChartType,
    data: Dict
) -> tuple[bool, Optional[str]]:
    """
    Valida que los datos cumplen los requisitos para un tipo de grafico.

    Args:
        chart_type: Tipo de grafico
        data: Datos a validar

    Returns:
        Tuple de (es_valido, mensaje_error)
    """
    chart_def = CHART_CATALOG.get(chart_type)
    if not chart_def:
        return False, f"Tipo de grafico desconocido: {chart_type}"

    # Validaciones especificas por tipo
    if chart_type == ChartType.PIE_CHART:
        if len(data.get("items", [])) > 8:
            return False, "Pie chart soporta maximo 8 segmentos"

    if chart_type in [ChartType.LINE_CHART, ChartType.AREA_CHART]:
        points = data.get("points", [])
        if len(points) < 2:
            return False, "Se necesitan al menos 2 puntos para grafico de linea"

    if chart_type == ChartType.COMPARISON_BAR:
        if not data.get("current_period") or not data.get("previous_period"):
            return False, "Comparacion requiere current_period y previous_period"

    return True, None


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
