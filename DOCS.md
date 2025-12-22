# SQL Agent - Documentacion Completa

## Resumen del Proyecto

SQL Agent es un asistente de Business Intelligence (BI) potenciado por IA que permite consultar datos de negocio usando lenguaje natural. El sistema utiliza una arquitectura multi-agente con LangGraph para orquestar el flujo de datos.

### Caracteristicas Principales

- **Consultas en lenguaje natural**: "Como van las ventas?" genera un dashboard completo
- **Multi-agente**: Router + DataAgent + PresentationAgent
- **Streaming SSE**: Actualizaciones en tiempo real con AI SDK v5
- **SQL Seguro**: Solo queries del allowlist, sin SQL dinamico
- **Visualizaciones dinamicas**: KPIs, graficos de linea/barras, tablas

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                 │
│  Next.js 14 + Tailwind + Recharts + AI SDK v5                   │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────┐                  │
│  │   Chat   │ │  Dashboard   │ │ AgentTimeline│                  │
│  │  Panel   │ │  Renderer    │ │   (Steps)   │                  │
│  └──────────┘ └──────────────┘ └─────────────┘                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ SSE Stream (AI SDK v5 Protocol)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND                                  │
│  FastAPI + LangGraph + Gemini/OpenRouter                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   LangGraph Pipeline                      │   │
│  │                                                           │   │
│  │   ┌─────────┐      ┌───────────┐      ┌──────────────┐   │   │
│  │   │ Intent  │ ───► │   Data    │ ───► │ Presentation │   │   │
│  │   │ Router  │      │   Agent   │      │    Agent     │   │   │
│  │   └─────────┘      └───────────┘      └──────────────┘   │   │
│  │        │                 │                    │          │   │
│  │   Clasifica         Ejecuta SQL         Genera Spec      │   │
│  │   Intent            del Allowlist       + Narrativa      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            │                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │ REST API (PostgREST)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        SUPABASE                                  │
│  PostgreSQL + PostgREST                                          │
│  ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌────────────┐    │
│  │ml_orders │ │  ml_items │ │conversations │ │ escalations│    │
│  └──────────┘ └───────────┘ └──────────────┘ └────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack Tecnologico

### Backend (Python 3.12+)

| Componente | Tecnologia | Version |
|------------|------------|---------|
| Framework | FastAPI | >=0.109.0 |
| Server | Uvicorn | >=0.27.0 |
| Orquestacion | LangGraph | >=0.2.0 |
| LLM Chain | LangChain Core | >=0.3.0 |
| LLM Provider | Gemini / OpenRouter | - |
| Observabilidad | LangSmith | >=0.5.0 |
| Schemas | Pydantic | >=2.7.4 |
| HTTP Client | httpx | >=0.27.0 |

### Frontend (Node.js 18+)

| Componente | Tecnologia | Version |
|------------|------------|---------|
| Framework | Next.js | 14.2.18 |
| UI | React | 18.3.1 |
| Styling | Tailwind CSS | 3.4.16 |
| Charts | Recharts | 2.13.3 |
| Icons | Lucide React | 0.454.0 |
| Validation | Zod | 4.2.1 |
| AI SDK | @ai-sdk/react | 3.0.1 |

### Base de Datos

- **Supabase** (PostgreSQL + PostgREST)
- Tablas: `ml_orders`, `ml_items`, `conversations`, `escalations`, `messages`
- Vista: `v_stock_dashboard`

---

## Flujo de Datos Detallado

### 1. Usuario envia pregunta

```
"Como van las ventas?"
     │
     ▼
POST /v1/chat/stream
```

### 2. IntentRouter clasifica

```python
# Tipos de respuesta posibles:
- CONVERSATIONAL  # "Hola" -> respuesta directa
- DATA_ONLY       # "cuantas ordenes?" -> solo KPIs
- DASHBOARD       # "como van las ventas?" -> dashboard completo
- CLARIFICATION   # pregunta ambigua -> pedir mas info
```

### 3. DataAgent ejecuta queries

```python
# El LLM decide que queries ejecutar del allowlist:
plan = {
    "query_ids": ["kpi_sales_summary", "ts_sales_by_day", "top_products_by_revenue"],
    "params": {"limit": 10}
}

# DataAgent ejecuta y genera DataPayload:
{
    "kpis": {"total_sales": 4567890.50, "total_orders": 234, ...},
    "time_series": [{"series_name": "sales_by_day", "points": [...]}],
    "top_items": [{"ranking_name": "products_by_revenue", "items": [...]}],
    "available_refs": ["kpi.total_sales", "ts.sales_by_day", ...]
}
```

### 4. PresentationAgent genera DashboardSpec

```python
# Genera especificacion + narrativa con UltraThink:
{
    "title": "Dashboard de Ventas",
    "subtitle": "Ultimos 30 dias",
    "conclusion": "Ventas totales: $4.5M con 234 ordenes",
    "slots": {
        "series": [{"label": "Ventas Totales", "value_ref": "kpi.total_sales"}],
        "charts": [{"type": "area_chart", "dataset_ref": "ts.sales_by_day"}],
        "narrative": [{"type": "headline", "text": "Tendencia positiva..."}]
    }
}
```

### 5. Frontend renderiza

El `DashboardRenderer` resuelve las refs contra el payload y renderiza:
- KpiCards con valores reales
- Graficos con datos de time_series
- Rankings con top_items
- Narrativa con insights

---

## Estructura de Archivos

```
SQL-AGENT/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, endpoints
│   │   ├── config.py            # Settings con pydantic-settings
│   │   │
│   │   ├── agents/
│   │   │   ├── intent_router.py # Router con heuristicas + LLM
│   │   │   ├── data_agent.py    # Ejecuta queries, genera payload
│   │   │   └── presentation_agent.py # Genera spec + narrativa
│   │   │
│   │   ├── api/
│   │   │   └── v1_chat.py       # Endpoint SSE AI SDK v5
│   │   │
│   │   ├── graphs/
│   │   │   └── insight_graph.py # LangGraph pipeline
│   │   │
│   │   ├── sql/
│   │   │   ├── allowlist.py     # Queries SQL predefinidas
│   │   │   └── schema_registry.py
│   │   │
│   │   ├── db/
│   │   │   └── supabase_client.py # Cliente REST para Supabase
│   │   │
│   │   ├── schemas/
│   │   │   ├── intent.py        # QueryRequest, QueryPlan
│   │   │   ├── payload.py       # DataPayload, KPIData, etc
│   │   │   └── dashboard.py     # DashboardSpec, SlotConfig
│   │   │
│   │   └── memory/
│   │       └── postgres_memory.py
│   │
│   ├── tests/
│   │   ├── test_contracts.py
│   │   └── test_sql_safety.py
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx             # Pagina principal con chat + dashboard
│   │   └── api/chat/route.ts    # Proxy opcional
│   │
│   ├── components/
│   │   ├── AgentTimeline.tsx    # Timeline de pasos del agente
│   │   ├── ChartRenderer.tsx    # Renderiza graficos con Recharts
│   │   ├── DashboardRenderer.tsx # Orquesta todo el dashboard
│   │   ├── DataTable.tsx        # Tablas de datos
│   │   ├── KpiCard.tsx          # Tarjetas de KPIs
│   │   └── NarrativePanel.tsx   # Panel de insights
│   │
│   ├── lib/
│   │   ├── api.ts               # Cliente API
│   │   ├── streamParts.ts       # Validadores Zod para SSE
│   │   ├── types.ts             # TypeScript types
│   │   └── utils.ts             # Utilidades
│   │
│   └── package.json
│
├── CLAUDE.md                    # Instrucciones para Claude Code
├── DOCS.md                      # Esta documentacion
└── .mcp.json                    # Config MCP servers
```

---

## Configuracion

### Variables de Entorno - Backend (.env)

```bash
# === Supabase ===
SUPABASE_URL=https://zaqpiuwacinvebfttygm.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...

# === LLM ===
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash-exp

# OpenRouter (opcional, fallback)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemini-3-flash-preview
USE_OPENROUTER_PRIMARY=false

# === LangSmith (opcional) ===
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=sql-agent
LANGSMITH_API_KEY=lsv2_...

# === Server ===
PORT=8000
FRONTEND_URL=http://localhost:3000
DEMO_MODE=false
```

### Variables de Entorno - Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Prompts del Sistema

### IntentRouter - System Prompt

El router usa **heuristicas primero** (sin LLM) basadas en keywords:

```python
# Patrones conversacionales
CONVERSATIONAL_PATTERNS = [
    (r"^(hola|hey|buenas|...)", "greeting"),
    (r"(que puedes hacer|ayuda|help)", "help"),
]

# Keywords de datos
DATA_KEYWORDS = ["cuanto", "ventas", "ordenes", "productos", "stock", ...]

# Keywords de dashboard
DASHBOARD_KEYWORDS = ["mostrame", "grafico", "tendencia", "analisis", ...]
```

### DataAgent - System Prompt

```python
system_prompt = """Eres un asistente que decide que queries ejecutar para responder preguntas de negocio.

QUERIES DISPONIBLES (SOLO puedes elegir de esta lista):
- kpi_sales_summary: Resumen de KPIs de ventas
- ts_sales_by_day: Ventas agrupadas por dia
- top_products_by_revenue: Top productos por ingresos
- ai_interactions_summary: Resumen de interacciones AI
- escalated_cases: Casos escalados a humano
...

REGLAS:
1. SOLO responde con un JSON valido
2. SOLO usa query_ids de la lista
3. Maximo 3 queries por request

FORMATO:
{"query_ids": ["query_id1", "query_id2"], "params": {"limit": 10}}
"""
```

### PresentationAgent - System Prompt (UltraThink)

```python
system_prompt = """Eres un analista de datos senior con capacidad de RAZONAMIENTO PROFUNDO (ULTRATHINK).

## PROCESO DE RAZONAMIENTO (ULTRATHINK)
1. ANALIZAR: Examina todos los datos disponibles
2. COMPARAR: Identifica patrones, anomalias y tendencias
3. CONTEXTUALIZAR: Pon los numeros en perspectiva de negocio
4. SINTETIZAR: Genera conclusiones accionables

## REGLAS ESTRICTAS
1. Responde SOLO en espanol
2. Cada insight DEBE mencionar numeros especificos
3. Si hay tendencia temporal, calcula el % de cambio
4. La conclusion debe responder directamente la pregunta
5. La recomendacion debe ser ESPECIFICA y ACCIONABLE

## FORMATO DE RESPUESTA (JSON):
{
  "thinking": "Tu proceso de razonamiento interno",
  "conclusion": "Respuesta directa en 1 frase",
  "summary": "Resumen ejecutivo",
  "insights": ["Insight 1", "Insight 2", "Insight 3"],
  "recommendation": "Accion especifica: [verbo] + [que] + [para que]"
}
"""
```

---

## API Endpoints

### POST /v1/chat/stream (AI SDK v5)

Endpoint principal con streaming SSE.

**Request:**
```json
{
  "question": "Como van las ventas?",
  "conversation_id": "optional-uuid",
  "user_id": "optional-user"
}
```

**Response (SSE Stream):**
```
data: {"type":"start","messageId":"msg-abc123"}
data: {"type":"text-start","textId":"text-abc123"}
data: {"type":"data-agent_step","data":{"step":"router","status":"progress",...}}
data: {"type":"data-dashboard","data":{"title":"Dashboard de Ventas",...}}
data: {"type":"data-payload","data":{"kpis":{...},"time_series":[...]}}
data: {"type":"text-delta","textId":"text-abc123","delta":"Ventas totales..."}
data: {"type":"text-end","textId":"text-abc123"}
data: {"type":"finish","finishReason":"complete","messageId":"msg-abc123"}
data: [DONE]
```

### POST /api/insights/run

Endpoint sincrono (sin streaming).

**Request:**
```json
{
  "question": "Como van las ventas?",
  "date_from": "2024-12-01",
  "date_to": "2024-12-22",
  "filters": {}
}
```

**Response:**
```json
{
  "success": true,
  "trace_id": "abc12345",
  "dashboard_spec": {...},
  "data_payload": {...},
  "data_meta": {...},
  "execution_time_ms": 1234.56
}
```

### GET /api/health

Health check.

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "database": "connected"
}
```

### GET /api/queries

Lista queries disponibles del allowlist.

```json
{
  "queries": {
    "kpi_sales_summary": "Resumen de KPIs de ventas",
    "ts_sales_by_day": "Ventas agrupadas por dia",
    ...
  }
}
```

---

## SQL Allowlist

El sistema usa un **allowlist de queries predefinidas**. El LLM NO genera SQL, solo elige de esta lista:

### Queries de Ventas

| Query ID | Descripcion | Output Type |
|----------|-------------|-------------|
| kpi_sales_summary | KPIs de ventas (total, ordenes, promedio) | kpi |
| ts_sales_by_day | Ventas por dia (time series) | time_series |
| top_products_by_revenue | Top productos por ingresos | top_items |
| recent_orders | Ultimas ordenes | table |
| sales_by_channel | Ventas por canal | top_items |

### Queries de Productos

| Query ID | Descripcion | Output Type |
|----------|-------------|-------------|
| products_inventory | Inventario completo | table |
| products_low_stock | Productos con stock < 10 | table |
| top_products_by_sales | Top por unidades vendidas | top_items |
| stock_alerts | Alertas de stock critico | table |

### Queries de AI/Interacciones

| Query ID | Descripcion | Output Type |
|----------|-------------|-------------|
| ai_interactions_summary | KPIs de interacciones AI | kpi |
| recent_ai_interactions | Ultimas conversaciones | table |
| escalated_cases | Casos escalados | table |
| interactions_by_case_type | Agrupado por tipo de caso | top_items |

---

## Comandos de Desarrollo

### Backend

```bash
cd backend

# Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables
cp .env.example .env
# Editar .env con tus keys

# Ejecutar servidor
python -m app.main
# -> http://localhost:8000
# -> Dashboard: http://localhost:8000/dashboard
```

### Frontend

```bash
cd frontend

# Instalar dependencias
npm install

# Configurar variables
cp .env.example .env.local
# Editar .env.local

# Ejecutar desarrollo
npm run dev
# -> http://localhost:3000
```

---

## Pruebas Locales

### Probar endpoint con curl

```bash
# Health check
curl http://localhost:8000/api/health

# Ejecutar insight (sincrono)
curl -X POST http://localhost:8000/api/insights/run \
  -H "Content-Type: application/json" \
  -d '{"question": "Como van las ventas?"}'

# Streaming (SSE)
curl -N http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Mostrame el inventario"}'
```

### Verificar base de datos

```bash
# Probar conexion Supabase
curl -s "https://zaqpiuwacinvebfttygm.supabase.co/rest/v1/ml_orders?select=order_id&limit=1" \
  -H "apikey: TU_ANON_KEY"
```

---

## Despliegue

### Backend (Railway / Render / EasyPanel)

```bash
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend (Vercel)

```bash
# vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs"
}
```

Variables de entorno en Vercel:
- `NEXT_PUBLIC_API_URL`: URL del backend desplegado

---

## Troubleshooting

### Error: Rate limit Gemini

El sistema tiene fallback automatico a OpenRouter:
```python
if "429" in error or "RESOURCE_EXHAUSTED" in error:
    # Usa OpenRouter como fallback
```

Para evitar: configura `USE_OPENROUTER_PRIMARY=true`

### Error: Conexion Supabase

Verificar:
1. `SUPABASE_URL` correcto (sin `/` al final)
2. `SUPABASE_SERVICE_KEY` tiene permisos (bypass RLS)
3. Las tablas existen: `ml_orders`, `ml_items`, etc.

### Dashboard vacio

1. Verificar que el backend responde: `curl http://localhost:8000/api/health`
2. Revisar consola del navegador para errores SSE
3. Verificar que hay datos en Supabase

---

## Proximos Pasos

- [ ] Agregar memoria conversacional (LangGraph checkpointer)
- [ ] Implementar cache Redis para queries pesadas
- [ ] Agregar autenticacion JWT
- [ ] Soporte para multiples tenants
- [ ] Export a PDF/Excel
