# Arquitectura de IA - SQL Agent

## Resumen Ejecutivo

SQL Agent es un sistema de analytics conversacional que utiliza una arquitectura **multi-agente orquestada por un Supervisor**. El sistema combina **heurísticas deterministas** (rápidas, sin costo) con **razonamiento LLM no determinista** (semántico, flexible) para procesar preguntas en lenguaje natural y generar dashboards interactivos.

---

## Diagrama de Arquitectura

```
                    ┌─────────────────────┐
                    │   Usuario (Chat)    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   FastAPI + SSE     │
                    │  /v1/chat/stream    │
                    └──────────┬──────────┘
                               │
                               ▼
         ┌─────────────────────────────────────────┐
         │           LangGraph v2                  │
         │        Supervisor Pattern               │
         │                                         │
         │  ┌─────────────────────────────────┐   │
         │  │         SUPERVISOR              │   │
         │  │   (Orquestador Central)         │   │
         │  └──────────────┬──────────────────┘   │
         │                 │                       │
         │    ┌────────────┼────────────┐         │
         │    ▼            ▼            ▼         │
         │ ┌──────┐   ┌──────────┐  ┌─────────┐  │
         │ │Router│   │DataAgent │  │Present. │  │
         │ └──────┘   └──────────┘  │ Agent   │  │
         │                │         └─────────┘  │
         │                ▼                       │
         │         ┌────────────┐                │
         │         │ Reflection │                │
         │         │  (Retry)   │                │
         │         └────────────┘                │
         └─────────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       ┌───────────┐   ┌───────────┐    ┌───────────┐
       │  Supabase │   │  Gemini   │    │ OpenRouter│
       │ PostgreSQL│   │    LLM    │    │  (Backup) │
       └───────────┘   └───────────┘    └───────────┘
```

---

## Componentes del Sistema

### 1. Supervisor (Orquestador)

**Archivo:** `app/graphs/insight_graph_v2.py`

El Supervisor es el nodo central que orquesta todo el flujo. Implementa el **Supervisor Pattern** de LangGraph usando `Command` objects para routing dinámico.

```python
def supervisor_node(state) -> Command[Literal["router", "data_agent", "presentation", "direct_response", "__end__"]]:
    # Decide el siguiente nodo basado en el estado
```

**Decisiones del Supervisor:**
| Estado | Acción |
|--------|--------|
| Sin routing_decision | → Router |
| Conversacional | → DirectResponse |
| Necesita datos | → DataAgent |
| Necesita dashboard | → Presentation |
| Completado | → END |

---

### 2. Intent Router (Clasificador)

**Archivo:** `app/agents/intent_router.py`

El Router clasifica la intención del usuario y decide qué tipo de respuesta generar.

#### Tipos de Respuesta

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| `CONVERSATIONAL` | Saludo, ayuda, preguntas generales | "Hola", "¿Qué puedes hacer?" |
| `DATA_ONLY` | Solo números, sin visualización | "¿Cuántas ventas hubo ayer?" |
| `DASHBOARD` | Dashboard completo con gráficos | "¿Cómo van las ventas?" |
| `CLARIFICATION` | Pedir más contexto | Pregunta ambigua |

---

## Heurísticas: Deterministas vs No Deterministas

### Heurísticas Deterministas (Sin LLM)

Las heurísticas deterministas son **reglas basadas en keywords** que se ejecutan primero por ser rápidas y sin costo.

#### 1. Patrones Conversacionales (IntentRouter)

```python
CONVERSATIONAL_PATTERNS = [
    (r"^(hola|hey|buenas|buenos dias|...)", "greeting"),
    (r"^(gracias|muchas gracias|thanks|ok|...)", "thanks"),
    (r"(que puedes hacer|ayuda|help|...)", "help"),
    (r"(quien eres|que eres|...)", "identity"),
]
```

**Comportamiento:** Si la pregunta coincide con un patrón regex, se responde directamente sin invocar agentes.

#### 2. Keywords de Datos (IntentRouter)

```python
DATA_KEYWORDS = [
    "cuanto", "cuantos", "total", "suma",
    "vendimos", "ventas", "venta",
    "productos", "inventario", "stock",
    # ... más keywords
]
```

**Comportamiento:** Si la pregunta contiene keywords de datos, se activa `needs_sql=True`.

#### 3. Keywords de Dashboard (IntentRouter)

```python
DASHBOARD_KEYWORDS = [
    "mostrame", "muestrame", "ver", "visualiza",
    "grafico", "dashboard", "reporte",
    "tendencia", "comparar", "analisis",
    "como van", "como estan", "resumen",
    # ... más keywords
]
```

**Comportamiento:** Si contiene keywords de dashboard, se activa `needs_dashboard=True`.

#### 4. Selección de Queries (DataAgent)

```python
def _decide_queries_heuristic(self, question: str) -> QueryPlan:
    q_lower = question.lower()

    # Agente AI / Interacciones
    if any(kw in q_lower for kw in ["agente", "ai", "bot"]):
        return ["ai_interactions_summary", "recent_ai_interactions"]

    # Ventas / Revenue
    elif any(kw in q_lower for kw in ["venta", "factura", "ingreso"]):
        return ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

    # Reposición de stock
    elif any(kw in q_lower for kw in ["reponer", "reposicion", "quiebre"]):
        return ["kpi_sales_summary", "stock_reorder_analysis", "ts_top_product_sales"]

    # ... más reglas
```

**Comportamiento:** Basado en keywords, se seleccionan las queries predefinidas del allowlist.

---

### Heurísticas No Deterministas (Con LLM)

Las heurísticas no deterministas usan **LLM para razonamiento semántico** cuando las reglas deterministas no son suficientes.

#### 1. Routing Semántico (IntentRouter)

**Cuándo se activa:** Cuando no hay keywords claros en la pregunta.

```python
def _route_with_llm(self, question: str) -> RoutingDecision:
    system_prompt = """
    Analiza la pregunta del usuario y determina:
    1. response_type: "dashboard" | "data_only" | "conversational"
    2. domain: "sales" | "inventory" | "conversations"
    """
    # LLM decide el routing
```

**Modelo usado:** `gemini-2.0-flash-exp` o `google/gemini-3-flash-preview` (OpenRouter)

#### 2. Selección de Queries con LLM (DataAgent)

**Cuándo se activa:** Cuando `DATA_AGENT_USE_LLM=true` (por defecto).

```python
def decide_queries(self, question: str, ...) -> QueryPlan:
    system_prompt = f"""
    Eres un experto en análisis de datos de e-commerce.

    ## QUERIES DISPONIBLES:
    {queries_list}

    ## REGLAS:
    1. SOLO usa query_ids de la lista
    2. Elige las queries MÁS RELEVANTES (max 3)
    3. Para ventas: SIEMPRE incluir kpi_sales_summary
    """
```

**El LLM decide:**
- Qué queries ejecutar del allowlist
- Qué parámetros usar (límites, fechas)

#### 3. Generación de Narrativa (PresentationAgent)

**Cuándo se activa:** Siempre (excepto en DEMO_MODE).

```python
def generate_narrative(self, question: str, payload: DataPayload):
    # Usa prompt UltraThink para análisis profundo
    system_prompt = get_narrative_prompt()

    # Genera:
    # - conclusion: Respuesta directa a la pregunta
    # - summary: Resumen ejecutivo
    # - insights: Lista de insights detallados
    # - recommendation: Acción recomendada
```

**Modelo usado:** `gemini-2.0-flash-thinking-exp` (con capacidad de razonamiento extendido)

---

## Flujo de Decisión

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PREGUNTA DEL USUARIO                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 1: Patrones Conversacionales (DETERMINISTA)                   │
│  ¿Coincide con regex de saludo/ayuda/agradecimiento?                │
│                                                                     │
│  SÍ → Respuesta directa (sin agentes)                              │
│  NO → Continuar                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 2: Keywords de Datos/Dashboard (DETERMINISTA)                 │
│  ¿Contiene keywords de DATA_KEYWORDS o DASHBOARD_KEYWORDS?          │
│                                                                     │
│  SÍ → Clasificar como DATA_ONLY o DASHBOARD                        │
│  NO → Continuar a LLM                                               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 3: Routing Semántico (NO DETERMINISTA - LLM)                  │
│  LLM analiza semánticamente la pregunta y decide:                   │
│  - response_type: dashboard | data_only | conversational            │
│  - domain: sales | inventory | conversations                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 4: Selección de Queries (HÍBRIDO)                             │
│                                                                     │
│  Si DATA_AGENT_USE_LLM=true:                                       │
│    → LLM elige queries del allowlist                                │
│  Else:                                                              │
│    → Heurísticas por keywords                                       │
│                                                                     │
│  Fallback: Si LLM falla → usar heurísticas                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 5: Ejecución de Queries (DETERMINISTA)                        │
│  Solo ejecuta queries del ALLOWLIST predefinido                     │
│  Queries son templates SQL seguros con parámetros                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PASO 6: Generación de Dashboard (HÍBRIDO)                          │
│                                                                     │
│  Estructura del dashboard: DETERMINISTA                             │
│  - _build_spec_heuristic() construye KPIs, charts, tables           │
│  - _ensure_two_charts() asegura mínimo 2 gráficos                   │
│                                                                     │
│  Narrativa/Insights: NO DETERMINISTA (LLM UltraThink)              │
│  - generate_narrative() con análisis profundo                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Queries Allowlist

El sistema usa un **allowlist de queries predefinidas** por seguridad. El LLM SOLO puede elegir de esta lista.

### Categorías de Queries

| Categoría | Queries | Tipo Output |
|-----------|---------|-------------|
| **Ventas** | `kpi_sales_summary`, `ts_sales_by_day`, `top_products_by_revenue` | KPI, TimeSeries, TopItems |
| **Productos** | `products_inventory`, `products_low_stock`, `top_products_by_sales` | Table, TopItems |
| **Stock** | `stock_alerts`, `stock_reorder_analysis` | Table, TopItems |
| **AI Agent** | `ai_interactions_summary`, `escalated_cases` | KPI, Table |
| **Preventa** | `preventa_summary`, `recent_preventa_queries` | KPI, Table |

### Tipos de Output

```python
"kpi"         → payload.kpis (métricas agregadas)
"time_series" → payload.time_series (datos para gráficos de línea)
"top_items"   → payload.top_items (rankings para gráficos de barras)
"table"       → payload.raw_data (datos tabulares)
```

---

## Ciclo de Reflexión (Retry)

El sistema implementa un **ciclo de reflexión** para autocorrección de errores.

```
DataAgent → Error → Reflection → DataAgent (retry)
                        │
                        ▼
              Analiza el error y ajusta
              estrategia antes de reintentar
```

**Configuración:**
- `retry_count`: Contador de reintentos (default: 0)
- `max_retries`: Máximo de reintentos (default: 3)

---

## Modelos LLM Utilizados

| Componente | Modelo Primario | Modelo Fallback | Temperatura |
|------------|-----------------|-----------------|-------------|
| IntentRouter | gemini-2.0-flash-exp | google/gemini-3-flash-preview | 0.1 |
| DataAgent | gemini-2.0-flash-exp | google/gemini-3-flash-preview | 0.1 |
| PresentationAgent | gemini-2.0-flash-thinking-exp | google/gemini-3-flash-preview | 0.7 |

**Nota:** Si `USE_OPENROUTER_PRIMARY=true`, OpenRouter se usa como primario y Gemini como fallback.

---

## Variables de Entorno Relevantes

```bash
# LLM
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash-exp
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-3-flash-preview
USE_OPENROUTER_PRIMARY=true

# Comportamiento
DATA_AGENT_USE_LLM=true    # Si false, solo usa heurísticas
DEMO_MODE=false             # Si true, skip LLM en narrativa
USE_GRAPH_V2=true           # Usar arquitectura Supervisor

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tienda-lubbi-insights
LANGCHAIN_API_KEY=...
```

---

## Observabilidad con LangSmith

Ver documento separado: [LANGSMITH_SETUP.md](./LANGSMITH_SETUP.md)

---

## Resumen de Decisiones Deterministas vs No Deterministas

| Componente | Determinista | No Determinista |
|------------|--------------|-----------------|
| **Patrones conversacionales** | ✅ Regex | ❌ |
| **Keywords routing** | ✅ Lista de keywords | ❌ |
| **Routing semántico** | ❌ | ✅ LLM |
| **Selección de queries** | ✅ Fallback por keywords | ✅ LLM primario |
| **Ejecución SQL** | ✅ Templates allowlist | ❌ |
| **Estructura dashboard** | ✅ Heurísticas | ❌ |
| **Narrativa/Insights** | ❌ | ✅ LLM UltraThink |
| **Retry/Reflection** | ✅ Lógica fija | ❌ |

---

## Archivos Clave

```
backend/
├── app/
│   ├── agents/
│   │   ├── intent_router.py      # Router con heurísticas + LLM
│   │   ├── data_agent.py         # Agente de datos con LLM reasoning
│   │   └── presentation_agent.py # Generación de dashboard + narrativa
│   ├── graphs/
│   │   └── insight_graph_v2.py   # LangGraph Supervisor Pattern
│   ├── sql/
│   │   ├── allowlist.py          # Queries permitidas
│   │   └── schema_registry.py    # Schema de la DB
│   ├── observability/
│   │   └── langsmith.py          # Tracing y callbacks
│   └── prompts/
│       └── ultrathink.py         # Prompts para LLM
```
