# ULTRATHINK: Arquitectura Flexible de Graficos

## Vision General

El objetivo es crear un sistema donde el **PresentationAgent** tenga autonomia para elegir entre un catalogo de tipos de graficos, cada uno con variables requeridas especificas. Si las variables no estan disponibles, el agente puede solicitarlas al **DataAgent** a traves del **Orchestrator**.

---

## Arquitectura Actual

```
[Router]
    |
    v
[DataAgent] --> (ejecuta queries predefinidas)
    |
    v
[PresentationAgent] --> (genera dashboard con lo que tiene)
    |
    v
[END]
```

**Limitacion**: El PresentationAgent solo puede usar datos que DataAgent ya genero. No puede pedir datos adicionales.

---

## Arquitectura Propuesta: Dynamic Data Request

```
[Router]
    |
    v
[DataAgent] --> (fase 1: datos base)
    |
    v
[PresentationAgent]
    |
    +---(tiene todas las vars?)---> SI ---> [END]
    |
    NO
    |
    v
[Orchestrator: request_data] --> (solicita vars faltantes)
    |
    v
[DataAgent] --> (fase 2: datos adicionales)
    |
    v
[PresentationAgent] --> (retry con datos completos)
    |
    v
[END]
```

---

## Catalogo de Tipos de Graficos (10 tipos)

### 1. `line_chart` - Grafico de Lineas (Tendencias)
- **Uso**: Mostrar evolucion temporal de una metrica
- **Variables requeridas**:
  - `time_series`: Array de puntos `{date, value}`
- **Ejemplo de refs**: `ts.sales_by_day`, `ts.orders_by_week`
- **Config**:
```json
{
  "type": "line_chart",
  "dataset_ref": "ts.sales_by_day",
  "x_axis": "date",
  "y_axis": "value"
}
```

### 2. `area_chart` - Grafico de Area (Acumulados)
- **Uso**: Mostrar volumen acumulado o magnitud
- **Variables requeridas**:
  - `time_series`: Array de puntos `{date, value}`
- **Ejemplo de refs**: `ts.revenue_by_month`
- **Diferencia con line**: Fill bajo la linea, mejor para volumen

### 3. `bar_chart` - Grafico de Barras Horizontal (Rankings)
- **Uso**: Comparar items ordenados por valor
- **Variables requeridas**:
  - `top_items`: Array de `{rank, title, value, extra?}`
- **Ejemplo de refs**: `top.products_by_revenue`, `top.categories`
- **Config**:
```json
{
  "type": "bar_chart",
  "dataset_ref": "top.products_by_revenue",
  "x_axis": "title",
  "y_axis": "value"
}
```

### 4. `vertical_bar_chart` - Barras Verticales (Comparativas)
- **Uso**: Comparar categorias o periodos
- **Variables requeridas**:
  - `categories`: Array de `{category, value}`
- **Ejemplo de refs**: `cat.sales_by_region`, `cat.orders_by_channel`

### 5. `pie_chart` - Grafico de Torta (Distribucion)
- **Uso**: Mostrar proporciones de un total
- **Variables requeridas**:
  - `distribution`: Array de `{name, value}` (max 8 items)
- **Ejemplo de refs**: `dist.sales_by_category`, `dist.orders_by_status`

### 6. `donut_chart` - Grafico de Dona (Distribucion con KPI central)
- **Uso**: Distribucion con metrica central destacada
- **Variables requeridas**:
  - `distribution`: Array de `{name, value}`
  - `center_value`: Numero o string a mostrar en centro
- **Ejemplo de refs**: `dist.inventory_status`

### 7. `comparison_bar` - Barras de Comparacion (Periodos)
- **Uso**: Comparar metricas entre dos periodos
- **Variables requeridas**:
  - `comparison`: Objeto con `current_period` y `previous_period`
- **Ejemplo de refs**: `comparison.sales`
- **Config**:
```json
{
  "type": "comparison_bar",
  "current_label": "Nov 2024",
  "previous_label": "Oct 2024",
  "metrics": ["total_sales", "total_orders"]
}
```

### 8. `scatter_plot` - Diagrama de Dispersion (Correlacion)
- **Uso**: Mostrar relacion entre dos variables
- **Variables requeridas**:
  - `scatter_data`: Array de `{x, y, label?, size?}`
- **Ejemplo de refs**: `scatter.price_vs_units`

### 9. `funnel_chart` - Grafico de Embudo (Conversion)
- **Uso**: Mostrar etapas de conversion
- **Variables requeridas**:
  - `funnel_stages`: Array de `{stage, value, conversion_rate?}`
- **Ejemplo de refs**: `funnel.sales_pipeline`

### 10. `heatmap` - Mapa de Calor (Patrones)
- **Uso**: Mostrar intensidad en matriz bidimensional
- **Variables requeridas**:
  - `heatmap_data`: Matrix de `{row, col, value}`
- **Ejemplo de refs**: `heat.sales_by_hour_day`

---

## Mapeo de Variables a Queries SQL

```python
CHART_VARIABLE_QUERIES = {
    # Time Series
    "ts.sales_by_day": "ts_sales_by_day",
    "ts.sales_by_week": "ts_sales_by_week",
    "ts.sales_by_month": "ts_sales_by_month",
    "ts.orders_by_day": "ts_orders_by_day",

    # Top Items / Rankings
    "top.products_by_revenue": "top_products_by_revenue",
    "top.products_by_units": "top_products_by_units",
    "top.categories_by_revenue": "top_categories_by_revenue",

    # Distribution
    "dist.sales_by_category": "distribution_sales_by_category",
    "dist.orders_by_status": "distribution_orders_by_status",
    "dist.inventory_status": "distribution_inventory_status",

    # Comparison
    "comparison.sales": "comparison_sales_periods",

    # Scatter
    "scatter.price_vs_units": "scatter_price_units",

    # Funnel
    "funnel.sales_pipeline": "funnel_sales",

    # Heatmap
    "heat.sales_by_hour_day": "heatmap_hourly_sales"
}
```

---

## Flujo de Solicitud de Datos

### Paso 1: PresentationAgent analiza pregunta
```python
def analyze_visualization_needs(self, question: str, available_refs: List[str]) -> dict:
    """
    Determina que graficos son apropiados y que variables faltan.

    Returns:
        {
            "recommended_charts": [
                {"type": "line_chart", "dataset_ref": "ts.sales_by_day"},
                {"type": "bar_chart", "dataset_ref": "top.products_by_revenue"}
            ],
            "missing_refs": ["ts.sales_by_day"],
            "available_refs": ["top.products_by_revenue", "kpi.total_sales"]
        }
    """
```

### Paso 2: Orchestrator decide accion
```python
def orchestrator_check_data(state: SupervisorState) -> Command:
    """
    Si hay refs faltantes, delega a DataAgent para obtenerlas.
    """
    missing = state.get("missing_refs", [])

    if missing:
        return Command(
            goto="data_agent",
            update={
                "additional_queries": missing,
                "retry_presentation": True
            }
        )

    return Command(goto="__end__")
```

### Paso 3: DataAgent ejecuta queries adicionales
```python
def data_agent_additional(state: SupervisorState) -> Command:
    """
    Ejecuta solo las queries solicitadas, no el plan completo.
    """
    queries_needed = state.get("additional_queries", [])

    for ref in queries_needed:
        query_id = CHART_VARIABLE_QUERIES.get(ref)
        if query_id:
            result = execute_query(query_id)
            payload.add_data(ref, result)

    return Command(
        goto="presentation",
        update={"data_payload": payload}
    )
```

---

## Implementacion Propuesta

### Fase 1: Catalogo de Charts
1. Crear `backend/app/charts/catalog.py` con definiciones
2. Cada tipo define: `required_vars`, `optional_vars`, `example_config`
3. Funcion `validate_chart_requirements(chart_type, available_refs)`

### Fase 2: PresentationAgent Mejorado
1. Metodo `_analyze_chart_needs()` - analiza que graficos son posibles
2. Metodo `_identify_missing_refs()` - detecta variables faltantes
3. Retornar `ChartRequest` al orchestrator si faltan datos

### Fase 3: Orchestrator Loop
1. Nuevo nodo `check_data_completeness`
2. Condicional: si `missing_refs` → volver a `data_agent`
3. Limite de retry (max 2 vueltas) para evitar loops infinitos

### Fase 4: DataAgent Incremental
1. Modo "incremental": solo ejecuta queries especificas
2. Merge de payload existente con nuevos datos
3. Respeta cache de queries ya ejecutadas

---

## Ejemplo de Flujo Completo

**Usuario**: "Comparame las ventas de noviembre vs octubre"

1. **Router**: detecta `comparison`, envía a `data_agent`

2. **DataAgent (fase 1)**: ejecuta plan base
   - `kpi_sales_summary` (Nov)
   - `comparison_periods`
   - Genera: `kpi.*`, `comparison.*`

3. **PresentationAgent**: analiza
   - Quiere mostrar: `comparison_bar`, `line_chart` (tendencia Nov)
   - Tiene: `comparison.*`, `kpi.*`
   - Falta: `ts.sales_by_day` (para linea)
   - Retorna: `{"missing_refs": ["ts.sales_by_day"]}`

4. **Orchestrator**: detecta missing_refs
   - Envía a `data_agent` con `additional_queries`

5. **DataAgent (fase 2)**: ejecuta incremental
   - Solo `ts_sales_by_day`
   - Merge con payload existente

6. **PresentationAgent (retry)**: ahora tiene todo
   - Genera dashboard con `comparison_bar` + `line_chart`
   - Fin exitoso

---

## Consideraciones de Performance

1. **Cache de Queries**: DataAgent debe cachear resultados por `(query_id, date_range)`
2. **Max Retries**: Limitar a 2 vueltas presentation→data→presentation
3. **Parallel Execution**: Si faltan multiples refs, ejecutarlas en paralelo
4. **Smart Defaults**: Si falta data no critica, usar placeholder o mensaje

---

## Siguiente Paso

Implementar en este orden:
1. `charts/catalog.py` - Definiciones de tipos
2. `presentation_agent._analyze_chart_needs()` - Analisis
3. `insight_graph.check_data_node` - Nuevo nodo
4. Tests unitarios para cada tipo de chart
