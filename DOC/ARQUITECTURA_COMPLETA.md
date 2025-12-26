# SQL-AGENT - Arquitectura Completa

> **Ultima actualizacion**: 2025-12-25
> **Version**: 2.5.0

## 1. Vision General

SQL-Agent es un asistente de analytics con IA que permite hacer consultas en lenguaje natural sobre datos de e-commerce (MercadoLibre). Utiliza un sistema multi-agente orquestado con LangGraph.

```
┌─────────────────┐     SSE Stream      ┌─────────────────────────────┐
│   Frontend      │ ◄─────────────────► │         Backend             │
│   Next.js 14    │                     │   FastAPI + LangGraph       │
│   localhost:3000│                     │   localhost:8001            │
└─────────────────┘                     └─────────────────────────────┘
                                                    │
                                                    ▼
                                        ┌─────────────────────────────┐
                                        │   Supabase PostgreSQL       │
                                        │   (REST API)                │
                                        └─────────────────────────────┘
```

## 2. Estructura del Proyecto

```
SQL-AGENT/
├── backend/                    # FastAPI + LangGraph
│   ├── app/
│   │   ├── agents/             # IntentRouter, DataAgent, PresentationAgent
│   │   ├── api/                # Endpoints REST y SSE
│   │   ├── graphs/             # LangGraph orchestration
│   │   ├── schemas/            # Pydantic models
│   │   ├── sql/                # Allowlist queries (seguridad)
│   │   ├── db/                 # Supabase REST client
│   │   ├── memory/             # Persistencia de chat
│   │   ├── prompts/            # Templates LLM
│   │   └── main.py             # Entry point
│   └── migrations/             # SQL migrations
│
├── frontend/                   # Next.js 14
│   ├── app/                    # Pages (App Router)
│   ├── components/             # React components
│   ├── hooks/                  # useAgentChat (SSE streaming)
│   └── lib/                    # Types, utils
│
└── DOC/                        # Documentacion
```

## 3. Flujo de Datos

### 3.1 Request Flow

```
Usuario escribe pregunta
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend (page.tsx)                                        │
│  useAgentChat.sendMessage(question)                         │
│  POST /v1/chat/stream                                       │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ SSE Stream
┌─────────────────────────────────────────────────────────────┐
│  Backend (v1_chat.py)                                       │
│  1. Guardar mensaje en chat_memory                          │
│  2. Extraer fechas del lenguaje natural                     │
│  3. Ejecutar LangGraph                                      │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph (insight_graph.py)                               │
│                                                             │
│  ROUTER ─┬─► CONVERSATIONAL ──► direct_response ──► END     │
│          │                                                  │
│          └─► DATA_QUERY ──► data_agent ──► presentation ──► END
│                                │                            │
│                                └─► [error] ──► reflection ──┘
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Response                                                   │
│  - DashboardSpec (visual slots)                             │
│  - DataPayload (KPIs, charts, tables)                       │
│  - Narrative (conclusion, insights)                         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Agentes

| Agente | Responsabilidad | Output |
|--------|-----------------|--------|
| **IntentRouter** | Clasifica la pregunta | RoutingDecision |
| **DataAgent** | Ejecuta queries SQL seguras | DataPayload |
| **PresentationAgent** | Genera dashboard visual | DashboardSpec |

## 4. Estado del Grafo (InsightStateV2)

```python
InsightStateV2 = {
    # Input
    "question": str,
    "date_from": Optional[str],
    "date_to": Optional[str],

    # Routing
    "routing_decision": RoutingDecision,

    # Data
    "data_payload": DataPayload,      # KPIs, series, top_items
    "dashboard_spec": DashboardSpec,  # Visual slots

    # Memory
    "messages": List[AnyMessage],     # Historial con add_messages

    # Error handling
    "error": Optional[str],
    "retry_count": int,
    "max_retries": int  # default: 3
}
```

## 5. Seguridad SQL

**IMPORTANTE**: No se permite SQL dinamico. Solo queries del allowlist.

```python
# backend/app/sql/allowlist.py
QUERY_ALLOWLIST = {
    "kpi_sales_summary": {...},
    "ts_sales_by_day": {...},
    "top_products_by_revenue": {...},
    "products_low_stock": {...},
    # ... mas queries predefinidas
}
```

Cada query tiene:
- Template SQL parametrizado
- Validacion de parametros
- Output type (kpi, time_series, top_items, table)

## 6. API Endpoints

### POST /v1/chat/stream (SSE - AI SDK v5)
```json
// Request
{
  "question": "Como van las ventas?",
  "conversation_id": "thread-123",
  "user_id": "user-abc"
}

// Response: Server-Sent Events
data: {"type":"start","messageId":"msg-xxx"}
data: {"type":"data-agent_step","data":{"step":"router",...}}
data: {"type":"data-dashboard","data":{...DashboardSpec...}}
data: {"type":"data-payload","data":{...DataPayload...}}
data: {"type":"finish","finishReason":"complete"}
data: [DONE]
```

### POST /api/insights/run (Sync)
```json
// Request
{
  "question": "Mostrame inventario",
  "date_from": "2024-01-01",
  "date_to": "2024-12-25"
}

// Response
{
  "success": true,
  "trace_id": "abc123",
  "dashboard_spec": {...},
  "data_payload": {...},
  "execution_time_ms": 2341.50
}
```

### GET /api/health
```json
{
  "status": "healthy",
  "database": "connected",
  "checkpointer": "memory"
}
```

## 7. Configuracion

### Backend (.env)
```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...

# LLM
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash-exp
USE_OPENROUTER_PRIMARY=true
OPENROUTER_API_KEY=...

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...

# Server
PORT=8001
```

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8001/v1/chat/stream
```

## 8. Comandos de Desarrollo

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 9. Base de Datos

### Tablas Principales

| Tabla | Proposito |
|-------|-----------|
| `ml_orders` | Ordenes de MercadoLibre |
| `ml_items` | Productos/inventario |
| `conversations` | Conversaciones AI |
| `escalations` | Casos escalados |
| `conversation_history` | Historial de chat |
| `langgraph_checkpoints` | Estado del grafo |

### Conexion
- **Metodo**: REST API (PostgREST)
- **Config critica**: `prepare_threshold=None` (para PgBouncer)

## 10. Troubleshooting

### Error: "[Errno 22] Invalid argument"
- Causa: Problema de async sockets en Windows
- Solucion: Reiniciar servidor en puerto limpio

### Error: "Max retries exceeded"
- Causa: LLM rate limit o error de conexion
- Solucion: Verificar API keys, usar OpenRouter como fallback

### Frontend no conecta
- Verificar `NEXT_PUBLIC_API_URL` apunta al puerto correcto
- Verificar CORS en backend

## 11. Stack Tecnologico

| Capa | Tecnologia |
|------|------------|
| Frontend | Next.js 14, Tailwind, Recharts |
| Backend | FastAPI, LangGraph, LangChain |
| LLM | Gemini 2.0 Flash, OpenRouter |
| Database | Supabase PostgreSQL |
| Observability | LangSmith |

---

*Documento generado automaticamente. Usar `/documentacion` para actualizar.*
