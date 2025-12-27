# SQL Agent - Documentacion Tecnica Completa

**Version:** 2.5 (Diciembre 2025)
**Modelo LLM:** `google/gemini-3-flash-preview` via OpenRouter
**Framework:** LangGraph v0.2+ con patron Router-as-CEO

---

## 1. Vision General

SQL Agent es un sistema de Business Intelligence conversacional que permite a usuarios hacer preguntas en lenguaje natural sobre datos de e-commerce (MercadoLibre Argentina) y recibir dashboards interactivos con KPIs, graficos y narrativas.

### 1.1 Flujo Principal

```
Usuario: "como van las ventas"
    |
    v
[API Endpoint] /v1/chat/stream (SSE)
    |
    v
[Date Parser] Extrae fechas del lenguaje natural
    |
    v
[Chat Memory] Carga historial de conversacion
    |
    v
[LangGraph] InsightGraph v2 (Router-as-CEO)
    |
    +---> [Router Node] Clasificacion por heuristicas
    |         |
    |         v
    +---> [DataAgent Node] Seleccion y ejecucion de SQL
    |         |
    |         v
    +---> [Presentation Node] Generacion de dashboard
    |
    v
[SSE Stream] AI SDK v5 Protocol
    |
    v
Frontend: Dashboard renderizado
```

---

## 2. Arquitectura de Componentes

### 2.1 API Layer (`app/api/v1_chat.py`)

**Endpoint:** `POST /v1/chat/stream`

```python
class ChatRequest(BaseModel):
    question: str           # Pregunta del usuario
    conversation_id: str    # ID de conversacion (opcional)
    user_id: str           # ID de usuario (opcional)
```

**Responsabilidades:**
- Recibir request HTTP
- Extraer fechas del lenguaje natural (`extract_date_range`)
- Cargar historial de chat (`ChatMemory`)
- Ejecutar LangGraph
- Emitir eventos SSE en formato AI SDK v5

**Formato SSE:**
```
data: {"type": "start", "messageId": "msg-xxx"}
data: {"type": "data-agent_step", "data": {...}}
data: {"type": "data-dashboard", "data": {...}}
data: {"type": "data-payload", "data": {...}}
data: {"type": "finish", "finishReason": "complete"}
data: [DONE]
```

### 2.2 LangGraph (`app/graphs/insight_graph.py`)

**Patron:** Router-as-CEO (LangGraph 2025)

El Router actua como CEO del sistema - decide Y navega directamente sin supervisor intermedio.

```
                    [START]
                       |
                       v
                  [router_node]
                  /    |    \
                 /     |     \
                v      v      v
    [direct_response] [data_agent] [clarification_agent]
                |          |              |
                v          v              v
              [END]  [presentation]  [data_agent o END]
                           |
                           v
                         [END]
```

**Estado del Grafo (`InsightStateV2`):**
```python
class InsightStateV2(TypedDict):
    question: str                    # Pregunta del usuario
    date_from: Optional[str]         # Fecha inicio
    date_to: Optional[str]           # Fecha fin
    chat_context: Optional[str]      # Historial de conversacion
    routing_decision: RoutingDecision # Decision del router
    data_payload: DataPayload        # Datos de SQL
    dashboard_spec: DashboardSpec    # Especificacion del dashboard
    messages: List[AnyMessage]       # Memoria de mensajes (LangGraph)
    agent_steps: List[dict]          # Pasos ejecutados (tracing)
```

### 2.3 Intent Router (`app/agents/intent_router.py`)

**Funcion:** Clasificar la intencion del usuario y decidir que agentes invocar.

**Tipos de Respuesta:**
```python
class ResponseType(Enum):
    CONVERSATIONAL = "conversational"  # Saludo, ayuda
    DATA_ONLY = "data_only"            # Solo datos, sin dashboard
    DASHBOARD = "dashboard"            # Dashboard completo
    CLARIFICATION = "clarification"    # Pedir mas contexto
```

**Sistema de Heuristicas (sin LLM):**

El router usa heuristicas basadas en keywords para clasificacion ultra-rapida (~0ms):

```python
# Keywords que indican datos
DATA_KEYWORDS = [
    "cuanto", "total", "ventas", "ordenes", "productos",
    "inventario", "stock", "agente", "escalado"...
]

# Keywords que indican dashboard
DASHBOARD_KEYWORDS = [
    "mostrame", "grafico", "dashboard", "tendencia",
    "como van", "como esta", "resumen"...
]

# Dominios de datos
DOMAIN_KEYWORDS = {
    "sales": ["ventas", "vendido", "orden", "factura"],
    "inventory": ["producto", "inventario", "stock"],
    "conversations": ["agente", "ai", "bot", "interaccion"]
}
```

**Flujo de Decision:**
```
1. Verificar patrones conversacionales (hola, gracias, ayuda)
   -> CONVERSATIONAL (respuesta directa)

2. Detectar ambiguedad (pronombres sin contexto, pregunta muy corta)
   -> CLARIFICATION (pedir mas info)

3. Detectar keywords de datos
   -> needs_data = True

4. Detectar keywords de dashboard
   -> needs_dashboard = True

5. Si ambos son False -> LLM semantico (fallback lento)

6. Retornar RoutingDecision
```

### 2.4 Data Agent (`app/agents/data_agent.py`)

**Funcion:** Decidir que queries SQL ejecutar y obtener los datos.

**IMPORTANTE: Sistema de Heuristicas Optimizado**

El DataAgent usa heuristicas para seleccionar queries SIN llamar al LLM:

```python
def decide_queries(self, question, date_from, date_to, chat_context):
    q_lower = question.lower()

    # Lista de keywords claros
    has_clear_keywords = any(kw in q_lower for kw in [
        "inventario", "stock", "venta", "ventas", "producto",
        "agente", "escalado", "preventa", "kpi", "resumen"...
    ])

    # Referencias ambiguas que REQUIEREN contexto
    has_ambiguous_refs = any(ref in q_lower for ref in [
        "eso", "esto", "lo mismo", "esos datos", "lo anterior"
    ])

    # Si hay keywords claros Y no hay referencias ambiguas
    # -> USAR HEURISTICAS (bypass LLM)
    if has_clear_keywords and not has_ambiguous_refs:
        return self._decide_queries_heuristic(question)
```

**Heuristicas de Seleccion de Queries:**

```python
def _decide_queries_heuristic(self, question):
    q_lower = question.lower()

    # Agente AI / Interacciones
    if "agente" in q_lower or "ai" in q_lower:
        return ["ai_interactions_summary", "recent_ai_interactions"]

    # IMPORTANTE: Inventario ANTES de Ventas
    # porque "inventario" contiene "venta" como substring!
    elif "inventario" in q_lower or "stock" in q_lower:
        return ["kpi_inventory_summary", "stock_reorder_analysis"]

    # Ventas / Revenue (despues de inventario)
    elif "venta" in q_lower or "vendido" in q_lower:
        return ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]

    # Default
    else:
        return ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]
```

**Allowlist de Queries (`app/sql/allowlist.py`):**

Solo se ejecutan queries predefinidas - NO se genera SQL dinamico:

```python
QUERY_ALLOWLIST = {
    # Ventas
    "kpi_sales_summary": {...},
    "ts_sales_by_day": {...},
    "top_products_by_revenue": {...},

    # Inventario
    "kpi_inventory_summary": {...},
    "stock_reorder_analysis": {...},
    "products_low_stock": {...},

    # AI Agent
    "ai_interactions_summary": {...},
    "escalated_cases": {...}
}
```

### 2.5 Presentation Agent (`app/agents/presentation_agent.py`)

**Funcion:** Generar el DashboardSpec con KPIs, graficos y narrativa.

**OPTIMIZACION: Smart Narrative (sin LLM)**

Por defecto, usa heuristicas inteligentes para generar narrativa:

```python
def generate_narrative(self, question, payload):
    # Por defecto NO usa LLM (muy lento)
    use_llm = os.getenv("PRESENTATION_USE_LLM", "false") == "true"

    if not use_llm:
        # Usar analisis inteligente sin LLM
        narratives = self._generate_smart_narrative(payload)
        conclusion = self._generate_quick_conclusion(question, payload)
        return narratives, conclusion
```

**Smart Narrative - Analisis Automatico:**

```python
def _generate_smart_narrative(self, payload):
    narratives = []

    # Analisis de KPIs
    if payload.kpis and payload.kpis.total_sales:
        narratives.append({
            "type": "headline",
            "text": f"Facturacion de ${total_sales:,.0f} en {orders:,} ordenes"
        })

        # Insight de ticket promedio
        if avg_ticket > 50000:
            narratives.append({
                "type": "insight",
                "text": "Ticket promedio saludable con buena conversion."
            })

    # Analisis de tendencias
    if payload.time_series:
        change_pct = calcular_tendencia(ts.points)
        if change_pct < -10:
            narratives.append({
                "type": "insight",
                "text": f"Tendencia bajista ({change_pct:.1f}%). Revisar estrategia."
            })

    return narratives
```

### 2.6 Supabase Client (`app/db/supabase_client.py`)

**Funcion:** Ejecutar queries SQL via REST API de Supabase.

```python
class SupabaseRESTClient:
    def execute_safe_query(self, query_id, params):
        # 1. Validar que query_id esta en allowlist
        if not validate_query_id(query_id):
            raise ValueError(f"Query no permitida: {query_id}")

        # 2. Obtener template SQL
        template = get_query_template(query_id)

        # 3. Construir parametros seguros
        safe_params = build_params(params)

        # 4. Ejecutar via REST API
        response = self._execute_rpc(template["function"], safe_params)

        return response["data"], DatasetMeta(...)
```

---

## 3. Sistema de Cache

### 3.1 Cache de Queries SQL

El sistema cachea resultados de queries para evitar llamadas repetidas a Supabase:

```python
# Cache en memoria con TTL de 15 minutos
_query_cache = {}
_cache_ttl = 900  # 15 minutos

def execute_with_cache(query_id, params):
    cache_key = f"{query_id}:{hash(params)}"

    if cache_key in _query_cache:
        if time.time() - _query_cache[cache_key]["ts"] < _cache_ttl:
            return _query_cache[cache_key]["data"]  # Cache HIT

    # Cache MISS - ejecutar query
    result = execute_query(query_id, params)
    _query_cache[cache_key] = {"data": result, "ts": time.time()}
    return result
```

### 3.2 Impacto del Cache

| Escenario | Tiempo |
|-----------|--------|
| Cold (primera vez) | 40-60s |
| Warm (cache hit) | 2-3s |

---

## 4. Sistema de Memoria

### 4.1 Chat Memory (`app/memory/chat_memory.py`)

Persiste el historial de conversacion en Supabase:

```python
class ChatMemory:
    def __init__(self, thread_id, user_id):
        self.thread_id = thread_id
        self.user_id = user_id
        self.messages = []

    def add_message_sync(self, role, content, metadata=None):
        # Guardar en Supabase tabla chat_messages
        self.client.insert("chat_messages", {
            "thread_id": self.thread_id,
            "role": role,
            "content": content,
            "metadata": metadata
        })

    def get_context_string(self, max_messages=5):
        # Retornar ultimos N mensajes como contexto
        return "\n".join([
            f"{m.role.capitalize()}: {m.content}"
            for m in self.messages[-max_messages:]
        ])
```

### 4.2 Uso del Contexto

El contexto de chat se pasa al DataAgent para entender referencias:

```python
# En v1_chat.py
chat_context = chat_memory.get_context_string(max_messages=5)

query_request = QueryRequest(
    question=question,
    chat_context=chat_context  # "Usuario: como van las ventas\nAsistente: Ventas totales: $5M"
)
```

---

## 5. Configuracion de Ambiente

### 5.1 Variables de Entorno (`.env`)

```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=xxx
SUPABASE_SERVICE_KEY=xxx

# Modelo LLM (OpenRouter)
OPENROUTER_API_KEY=sk-or-xxx
OPENROUTER_MODEL=google/gemini-3-flash-preview
USE_OPENROUTER_PRIMARY=true

# Gemini (fallback)
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-2.0-flash-exp

# Optimizaciones
DATA_AGENT_USE_LLM=true           # Permite LLM para casos ambiguos
PRESENTATION_USE_LLM=false        # Desactiva LLM en narrativa (usa smart_narrative)

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tienda-lubbi-insights
LANGSMITH_API_KEY=xxx

# Server
PORT=8000
LOG_LEVEL=DEBUG
CACHE_ENABLED=true
```

---

## 6. Optimizaciones de Rendimiento

### 6.1 Problema Original

El sistema era muy lento (138 segundos por consulta) porque:

1. **Router** llamaba al LLM para clasificacion (63s)
2. **DataAgent** llamaba al LLM para seleccion de queries (64s)
3. **PresentationAgent** llamaba al LLM para narrativa (64s)

### 6.2 Solucion Implementada

| Componente | Antes | Despues | Mejora |
|------------|-------|---------|--------|
| Router | LLM (63s) | Heuristicas (0ms) | 100% |
| DataAgent | LLM (64s) | Heuristicas (0ms) | 100% |
| PresentationAgent | LLM (64s) | smart_narrative (0ms) | 100% |
| **TOTAL** | **138s** | **2-3s (warm)** | **98%** |

### 6.3 Heuristicas vs LLM

**Cuando usar Heuristicas:**
- Keywords claros en la pregunta ("ventas", "inventario", "agente")
- Sin referencias ambiguas ("eso", "lo mismo")
- Preguntas comunes y bien formadas

**Cuando usar LLM (fallback):**
- No hay keywords claros
- Referencias ambiguas que requieren contexto
- Preguntas semanticamente complejas

### 6.4 Bug Corregido: Substring "inventario"

**Problema:** La palabra "inventario" contiene "venta" como substring:
- in**venta**rio

Esto causaba que preguntas de inventario se clasificaran como ventas.

**Solucion:** Reordenar las condiciones para verificar "inventario" ANTES de "venta":

```python
# CORRECTO (inventario primero)
if "inventario" in q_lower:
    return ["kpi_inventory_summary", ...]
elif "venta" in q_lower:
    return ["kpi_sales_summary", ...]

# INCORRECTO (venta primero)
if "venta" in q_lower:  # "inventario" matchea aqui!
    return ["kpi_sales_summary", ...]
```

---

## 7. Estructura de Datos

### 7.1 DataPayload

```python
class DataPayload(BaseModel):
    kpis: Optional[KPIData]              # KPIs calculados
    time_series: List[TimeSeriesData]    # Series temporales
    top_items: List[TopItemsData]        # Rankings
    tables: List[TableData]              # Tablas raw
    comparison: Optional[ComparisonData] # Comparacion de periodos
    available_refs: List[str]            # Referencias disponibles
```

### 7.2 DashboardSpec

```python
class DashboardSpec(BaseModel):
    title: str                    # "Dashboard de Ventas"
    subtitle: str                 # "Generado: 27/12/2025"
    conclusion: str               # Respuesta principal
    slots: SlotConfig             # Componentes visuales
    generated_at: str             # Timestamp
```

### 7.3 SlotConfig

```python
class SlotConfig(BaseModel):
    filters: List[FilterConfig]      # Filtros interactivos
    series: List[KpiCardConfig]      # KPI cards
    charts: List[ChartConfig]        # Graficos
    narrative: List[NarrativeConfig] # Textos/insights
```

---

## 8. Tracing y Observabilidad

### 8.1 LangSmith Integration

Todos los nodos del grafo estan decorados con `@traced`:

```python
@traced("Router")
def router_node(state):
    # Automaticamente logeado a LangSmith
    ...

@traced("DataAgent")
def data_agent_node(state):
    ...
```

### 8.2 Logs del Sistema

```
[Trace] [trace_id] START Router
[IntentRouter.route] INICIO para: como van las ventas
[IntentRouter.route] FIN heuristicas en 0.00s - needs_data=True, needs_dashboard=True
[Router] Decision: dashboard, Domain: sales
[Trace] [trace_id] END Router: 0ms (ok)

[Trace] [trace_id] START DataAgent
[DataAgent] Keywords claros detectados, usando heuristicas rapidas (bypass LLM)
[DataAgent] Heuristic selected: ['kpi_sales_summary', 'ts_sales_by_day', 'top_products_by_revenue']
[DataAgent] Completado: 7 refs
[Trace] [trace_id] END DataAgent: 1ms (ok)

[Trace] [trace_id] START Presentation
[PresentationAgent] Usando smart narrative (sin LLM) para latencia ultra-baja
[Presentation] Dashboard: Dashboard de Ventas
[Trace] [trace_id] END Presentation: 0ms (ok)
```

---

## 9. Diagramas

### 9.1 Flujo de Request

```
[Frontend]
    |
    | POST /v1/chat/stream
    | {"question": "como van las ventas"}
    v
[FastAPI]
    |
    | 1. Parse dates
    | 2. Load chat memory
    | 3. Create QueryRequest
    v
[LangGraph.invoke()]
    |
    +---> [router_node]
    |         |
    |         | RoutingDecision(type=DASHBOARD, domain=sales)
    |         v
    +---> [data_agent_node]
    |         |
    |         | Heuristics: ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"]
    |         | Execute SQL via Supabase REST
    |         v
    +---> [presentation_node]
              |
              | Smart Narrative (no LLM)
              | Build DashboardSpec
              v
[SSE Stream]
    |
    | data: {"type": "data-dashboard", "data": {...}}
    | data: {"type": "data-payload", "data": {...}}
    v
[Frontend]
    |
    | Render Dashboard
    v
[Usuario ve el dashboard]
```

### 9.2 Arquitectura de Agentes

```
+------------------+
|  IntentRouter    |
|  (Heuristicas)   |
+--------+---------+
         |
         | RoutingDecision
         v
+--------+---------+     +-------------------+
|    DataAgent     |---->|  Supabase REST    |
|  (Heuristicas)   |     |  (SQL Queries)    |
+--------+---------+     +-------------------+
         |
         | DataPayload
         v
+--------+---------+
| PresentationAgent|
| (Smart Narrative)|
+--------+---------+
         |
         | DashboardSpec
         v
+--------+---------+
|   SSE Stream     |
|  (AI SDK v5)     |
+------------------+
```

---

## 10. Testing

### 10.1 Queries de Prueba

```bash
# Ventas
curl -X POST "http://localhost:8000/v1/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"como van las ventas"}'

# Inventario
curl -X POST "http://localhost:8000/v1/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"como esta el inventario"}'

# Agente AI
curl -X POST "http://localhost:8000/v1/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"como esta el agente AI"}'
```

### 10.2 Tiempos Esperados

| Query | Cold | Warm (cache) |
|-------|------|--------------|
| ventas | ~45s | ~2s |
| inventario | ~20s | ~2s |
| agente AI | ~5s | ~2s |

---

## 11. Archivos Principales

```
backend/
├── app/
│   ├── api/
│   │   └── v1_chat.py          # Endpoint SSE
│   ├── agents/
│   │   ├── intent_router.py    # Clasificador de intenciones
│   │   ├── data_agent.py       # Ejecutor de SQL
│   │   ├── presentation_agent.py # Generador de dashboard
│   │   └── clarification_agent.py # Agente de clarificacion
│   ├── graphs/
│   │   └── insight_graph.py    # LangGraph v2
│   ├── sql/
│   │   ├── allowlist.py        # Queries permitidas
│   │   └── schema_docs.py      # Documentacion de esquema
│   ├── schemas/
│   │   ├── payload.py          # DataPayload, KPIData
│   │   ├── dashboard.py        # DashboardSpec
│   │   ├── intent.py           # QueryRequest, QueryPlan
│   │   └── agent_state.py      # InsightStateV2
│   ├── db/
│   │   └── supabase_client.py  # Cliente REST de Supabase
│   ├── memory/
│   │   ├── chat_memory.py      # Persistencia de chat
│   │   └── checkpointer.py     # LangGraph checkpointer
│   └── main.py                 # FastAPI app
├── .env                        # Configuracion
└── requirements.txt            # Dependencias
```

---

## 12. Conclusiones

El SQL Agent v2.5 implementa un sistema de BI conversacional altamente optimizado:

1. **Rendimiento:** De 138s a 2-3s (98% mejora)
2. **Precision:** Heuristicas correctas para cada dominio
3. **Escalabilidad:** Cache de queries reduce carga en Supabase
4. **Mantenibilidad:** Codigo modular con agentes especializados
5. **Observabilidad:** Tracing completo con LangSmith

**Proximos Pasos Sugeridos:**
- Optimizar queries SQL para reducir tiempo cold
- Implementar cache distribuido (Redis)
- Agregar mas dominios (marketing, logistica)
- Mejorar deteccion de ambiguedad

---

*Documento generado: 27/12/2025*
*Autor: Claude Code (Opus 4.5)*
