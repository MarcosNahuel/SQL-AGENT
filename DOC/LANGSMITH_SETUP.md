# LangSmith - Observabilidad del Sistema Agentico

## Que es LangSmith?

LangSmith es la plataforma de observabilidad de LangChain que permite:
- **Tracing**: Ver el flujo completo de ejecucion de los agentes
- **Debugging**: Identificar donde fallan las llamadas LLM
- **Evaluacion**: Medir la calidad de las respuestas
- **Monitoreo**: Metricas de latencia, tokens, costos

---

## Configuracion Inicial

### Paso 1: Crear cuenta en LangSmith

1. Ir a https://smith.langchain.com/
2. Crear cuenta con Google o GitHub
3. Una vez dentro, ir a **Settings** > **API Keys**
4. Crear una nueva API Key

### Paso 2: Configurar variables de entorno

En el archivo `backend/.env`:

```bash
# LangSmith (observabilidad)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tienda-lubbi-insights
LANGCHAIN_API_KEY=lsv2_pt_xxxxx  # Tu API key
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

**Variables explicadas:**

| Variable | Descripcion |
|----------|-------------|
| `LANGCHAIN_TRACING_V2` | Habilita el tracing automatico |
| `LANGCHAIN_PROJECT` | Nombre del proyecto en LangSmith |
| `LANGCHAIN_API_KEY` | Tu API key de LangSmith |
| `LANGCHAIN_ENDPOINT` | URL del servidor (default) |

### Paso 3: Verificar configuracion

Al iniciar el backend, deberias ver:

```
[LangSmith] Configured for project: tienda-lubbi-insights
```

---

## Navegando LangSmith

### Dashboard Principal

URL: https://smith.langchain.com/

1. **Projects**: Lista de proyectos (ej: `tienda-lubbi-insights`)
2. **Runs**: Ejecuciones individuales del sistema
3. **Datasets**: Conjuntos de datos para evaluacion
4. **Feedback**: Anotaciones y evaluaciones

### Vista de Proyecto

Al entrar a tu proyecto veras:

```
┌─────────────────────────────────────────────────────────────┐
│  tienda-lubbi-insights                                      │
├─────────────────────────────────────────────────────────────┤
│  Runs (ultimas 24h)                                         │
│  ─────────────────                                          │
│  ✓ InsightGraph-v2-abc123    45.2s   $0.003   SUCCESS      │
│  ✓ InsightGraph-v2-def456    32.1s   $0.002   SUCCESS      │
│  ✗ InsightGraph-v2-ghi789    12.4s   $0.001   ERROR        │
└─────────────────────────────────────────────────────────────┘
```

---

## Entendiendo un Trace

### Estructura del Trace

Cada ejecucion genera un trace con esta estructura:

```
InsightGraph-v2-abc123
├── supervisor (0ms)
│   └── Routing decision: route_to_router
├── router (622ms)
│   ├── LLM Call: gemini-2.0-flash
│   │   ├── Input: "Como van las ventas?"
│   │   └── Output: {"response_type": "dashboard", ...}
│   └── Decision: DASHBOARD, Domain: sales
├── supervisor (0ms)
│   └── Routing decision: fetch_data
├── data_agent (45319ms)
│   ├── LLM Call: gemini-2.0-flash
│   │   ├── Input: "Decide queries for: Como van las ventas?"
│   │   └── Output: {"query_ids": ["kpi_sales_summary", ...]}
│   ├── SQL Execution: kpi_sales_summary (234ms)
│   ├── SQL Execution: ts_sales_by_day (156ms)
│   └── SQL Execution: top_products_by_revenue (312ms)
├── supervisor (0ms)
│   └── Routing decision: generate_dashboard
├── presentation (8234ms)
│   ├── Build Spec (deterministic)
│   └── LLM Call: gemini-2.0-flash-thinking
│       ├── Input: "Generate insights for sales data..."
│       └── Output: {"conclusion": "...", "insights": [...]}
└── supervisor (0ms)
    └── Routing decision: complete
```

### Que buscar en cada nodo

#### 1. Router Node
- **Input**: Pregunta del usuario
- **Output**: Tipo de respuesta (`dashboard`, `data_only`, `conversational`)
- **Verificar**: Esta clasificando correctamente?

#### 2. DataAgent Node
- **LLM Input**: Pregunta + lista de queries disponibles
- **LLM Output**: Query IDs seleccionados
- **SQL Executions**: Queries ejecutadas y tiempos
- **Verificar**: Esta eligiendo las queries correctas?

#### 3. Presentation Node
- **LLM Input**: Pregunta + datos del payload
- **LLM Output**: Insights y narrativa
- **Verificar**: Los insights son relevantes?

---

## Casos de Uso para Debugging

### Caso 1: El agente no elige las queries correctas

**Problema**: Pregunta "que producto necesita reposicion" pero no usa `stock_alerts`

**Como investigar en LangSmith**:

1. Buscar el trace de esa pregunta
2. Ir al nodo `data_agent`
3. Expandir la llamada LLM
4. Ver el **Input** (prompt) y **Output** (decision)

**Que buscar**:
```json
// Output del LLM
{
  "query_ids": ["kpi_sales_summary", "products_low_stock", "top_products_by_revenue"]
  // Falta "stock_alerts" o "stock_reorder_analysis"
}
```

**Solucion**: Ajustar el prompt del DataAgent para que considere queries de stock

### Caso 2: La narrativa no responde la pregunta

**Problema**: Usuario pregunta "cual fue el mejor mes?" pero el insight habla de otra cosa

**Como investigar**:

1. Ir al nodo `presentation`
2. Ver el **Input** que recibio el LLM
3. Verificar que los datos del payload incluyen la info necesaria
4. Ver el **Output** del LLM

**Que buscar**:
- El payload tiene `time_series` con datos por mes?
- El prompt le pide que responda la pregunta especifica?

### Caso 3: Error de rate limit

**Sintoma**: Trace termina en error con "429" o "RESOURCE_EXHAUSTED"

**Como investigar**:

1. Ver el nodo que fallo
2. Verificar la duracion - si es muy rapida, fue rechazado antes de procesar
3. Ver si hay nodo `reflection` (significa que hizo retry)

**Solucion**:
- El sistema tiene fallback automatico a OpenRouter
- Si persiste, esperar o cambiar `USE_OPENROUTER_PRIMARY=true`

---

## Filtros Utiles en LangSmith

### Por Estado
```
status: success    # Solo exitosos
status: error      # Solo con errores
```

### Por Duracion
```
latency: >30s      # Lentos (mas de 30 segundos)
latency: <5s       # Rapidos
```

### Por Tags
```
tags: sql-agent    # Todos los traces del agente
tags: v2           # Solo version 2 del grafo
tags: streaming    # Solo ejecuciones streaming
```

### Por Fecha
```
start_time: >2025-01-01    # Desde una fecha
```

---

## Metricas Clave a Monitorear

### Latencia por Nodo

| Nodo | Latencia Esperada | Alerta Si |
|------|-------------------|-----------|
| Router | < 1s | > 3s |
| DataAgent | < 10s | > 30s |
| Presentation | < 15s | > 45s |
| **Total** | < 30s | > 60s |

### Tokens Consumidos

```
Promedio por ejecucion:
- Input tokens: ~2000-5000
- Output tokens: ~500-1500
- Costo estimado: $0.002-0.005
```

### Tasa de Errores

```
Aceptable: < 5% de errores
Alerta: > 10% de errores
Critico: > 25% de errores
```

---

## Configuracion de Alertas (Opcional)

LangSmith permite configurar alertas. Ir a **Settings** > **Alerts**:

1. **Error Rate Alert**: Si > 10% de runs fallan en 1 hora
2. **Latency Alert**: Si latencia promedio > 60s
3. **Cost Alert**: Si costo diario > $10

---

## Evaluaciones con Datasets

### Crear un Dataset de Evaluacion

1. Ir a **Datasets** > **Create Dataset**
2. Nombre: `sql-agent-test-cases`
3. Agregar ejemplos:

```json
[
  {
    "input": "como van las ventas",
    "expected_output": {
      "response_type": "dashboard",
      "domain": "sales",
      "queries_should_include": ["kpi_sales_summary"]
    }
  },
  {
    "input": "que producto necesita reposicion",
    "expected_output": {
      "response_type": "dashboard",
      "domain": "inventory",
      "queries_should_include": ["stock_reorder_analysis"]
    }
  }
]
```

### Ejecutar Evaluacion

Desde el dashboard de LangSmith:
1. Ir al Dataset
2. Click en **Run Evaluation**
3. Seleccionar el proyecto
4. Ver resultados comparativos

---

## Integracion con el Codigo

### Decorador @traced

El sistema usa el decorador `@traced` para marcar nodos:

```python
from ..observability.langsmith import traced

@traced("DataAgent")
def data_agent_node(state):
    # Automaticamente crea un span en LangSmith
    ...
```

### TraceContext Manual

Para tracing mas detallado:

```python
from ..observability.langsmith import trace_node

def my_function():
    with trace_node("CustomOperation", trace_id) as ctx:
        result = do_something()
        ctx.log_event("step_completed", {"rows": len(result)})
    return result
```

### Callbacks Personalizados

```python
from ..observability.langsmith import get_langsmith_callback

callback = get_langsmith_callback(
    trace_id="abc123",
    node_name="DataAgent"
)

# Usar con el LLM
llm.invoke(messages, callbacks=[callback])
```

---

## Comandos Utiles

### Ver logs en tiempo real

```bash
# En la terminal del backend
tail -f backend.log | grep "\[LangSmith\]"
```

### Verificar configuracion

```python
from app.observability.langsmith import is_langsmith_enabled

print(f"LangSmith enabled: {is_langsmith_enabled()}")
```

---

## Troubleshooting

### "LangSmith not configured"

**Causa**: Falta `LANGCHAIN_TRACING_V2=true` o `LANGCHAIN_API_KEY`

**Solucion**: Verificar variables en `.env`

### Traces no aparecen en el dashboard

**Causas posibles**:
1. API key incorrecta
2. Proyecto mal escrito
3. Firewall bloqueando conexion

**Verificar**:
```bash
curl -H "Authorization: Bearer $LANGCHAIN_API_KEY" https://api.smith.langchain.com/
```

### Latencia muy alta en traces

**Causa**: Incluir payloads muy grandes en logs

**Solucion**: El sistema ya filtra payloads grandes automaticamente

---

## Links Utiles

- LangSmith Dashboard: https://smith.langchain.com/
- Documentacion: https://docs.smith.langchain.com/
- Pricing: https://www.langchain.com/pricing
- Status: https://status.langchain.com/
