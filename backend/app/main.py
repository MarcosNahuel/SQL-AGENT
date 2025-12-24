"""
FastAPI Main - Entry point del backend de SQL-Agent

Endpoints:
- POST /api/insights/run - Ejecuta el grafo completo
- GET /api/health - Health check
- GET /api/queries - Lista queries disponibles
"""
import os
import uuid
from typing import Optional
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

from .schemas.intent import QueryRequest
from .schemas.dashboard import DashboardSpec
from .schemas.payload import DataPayload
from .graphs.insight_graph import run_insight_graph, run_insight_graph_streaming
from .graphs.cache import get_cache_stats, invalidate_cache
from .sql.allowlist import get_available_queries
from .db.supabase_client import get_db_client
from .api.v1_chat import router as v1_chat_router
from .observability.langsmith import is_langsmith_enabled


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager"""
    # Startup
    print("Starting SQL-Agent Backend...")
    # Test DB connection
    db = get_db_client()
    if db.test_connection():
        print("Database connection: OK")
    else:
        print("Database connection: FAILED (queries may not work)")
    yield
    # Shutdown
    print("Shutting down SQL-Agent Backend...")


app = FastAPI(
    title="SQL-Agent API",
    description="Backend para insights con LLM + SQL seguro",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "https://*.vercel.app",
        os.getenv("FRONTEND_URL", "*")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include AI SDK v5 chat router
app.include_router(v1_chat_router)


# Request/Response models
class InsightRequest(BaseModel):
    """Request para ejecutar insight"""
    question: str = Field(..., description="Pregunta en lenguaje natural")
    date_from: Optional[date] = Field(None, description="Fecha inicio")
    date_to: Optional[date] = Field(None, description="Fecha fin")
    filters: Optional[dict] = Field(default_factory=dict)


class InsightResponse(BaseModel):
    """Response del insight"""
    success: bool
    trace_id: str
    dashboard_spec: Optional[DashboardSpec] = None
    data_payload: Optional[dict] = None  # Datos reales resueltos
    data_meta: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    database: str
    langsmith: str
    cache: Optional[dict] = None


class QueriesResponse(BaseModel):
    """Lista de queries disponibles"""
    queries: dict


# Endpoints
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with cache stats"""
    db = get_db_client()
    db_status = "connected" if db.test_connection() else "disconnected"
    langsmith_status = "enabled" if is_langsmith_enabled() else "disabled"

    return HealthResponse(
        status="healthy",
        version="0.2.0",
        database=db_status,
        langsmith=langsmith_status,
        cache=get_cache_stats()
    )


@app.post("/api/cache/invalidate")
async def invalidate_all_cache():
    """Invalidate all caches"""
    invalidate_cache()
    return {"status": "ok", "message": "All caches invalidated"}


@app.get("/api/queries", response_model=QueriesResponse)
async def list_queries():
    """Lista las queries disponibles en el allowlist"""
    return QueriesResponse(queries=get_available_queries())


@app.post("/api/insights/stream")
async def stream_insights(request: InsightRequest):
    """
    Endpoint SSE - Ejecuta el grafo con streaming de eventos.

    Genera eventos Server-Sent Events (SSE) para mostrar el progreso:
    - start: Inicio del analisis
    - progress: Pasos intermedios (SQL query, analisis, etc)
    - complete: Resultado final con dashboard_spec
    - error: Si ocurre un error
    """
    trace_id = str(uuid.uuid4())[:8]

    # Convertir a QueryRequest
    query_request = QueryRequest(
        question=request.question,
        date_from=request.date_from,
        date_to=request.date_to,
        filters=request.filters or {}
    )

    async def event_generator():
        """Genera eventos SSE"""
        async for event_data in run_insight_graph_streaming(query_request, trace_id):
            yield f"data: {event_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.post("/api/insights/run", response_model=InsightResponse)
async def run_insights(request: InsightRequest):
    """
    Endpoint principal - Ejecuta el grafo de insights

    1. Recibe pregunta + filtros
    2. DataAgent decide y ejecuta queries
    3. PresentationAgent genera DashboardSpec
    4. Retorna spec + metadata
    """
    import time
    start_time = time.time()
    trace_id = str(uuid.uuid4())[:8]

    try:
        # Convertir a QueryRequest
        query_request = QueryRequest(
            question=request.question,
            date_from=request.date_from,
            date_to=request.date_to,
            filters=request.filters or {}
        )

        # Ejecutar grafo
        result = run_insight_graph(query_request, trace_id)

        execution_time = (time.time() - start_time) * 1000

        if result.get("error"):
            return InsightResponse(
                success=False,
                trace_id=trace_id,
                error=result["error"],
                execution_time_ms=round(execution_time, 2)
            )

        # Preparar metadata y datos reales
        data_meta = None
        data_payload_dict = None

        if result.get("data_payload"):
            payload = result["data_payload"]
            data_meta = {
                "available_refs": payload.available_refs,
                "datasets_count": len(payload.datasets_meta),
                "has_kpis": payload.kpis is not None,
                "has_time_series": payload.time_series is not None and len(payload.time_series) > 0,
                "has_top_items": payload.top_items is not None and len(payload.top_items) > 0
            }

            # Incluir datos reales para el frontend
            # Estructurar tables correctamente como {name, rows}
            tables_structured = []
            if payload.raw_data:
                # Agrupar por dataset_ref si está disponible
                tables_structured.append({
                    "name": "recent_orders",
                    "rows": payload.raw_data
                })

            data_payload_dict = {
                "kpis": payload.kpis.model_dump() if payload.kpis else None,
                "time_series": [ts.model_dump() for ts in payload.time_series] if payload.time_series else [],
                "top_items": [ti.model_dump() for ti in payload.top_items] if payload.top_items else [],
                "tables": tables_structured,
            }

        return InsightResponse(
            success=True,
            trace_id=trace_id,
            dashboard_spec=result.get("dashboard_spec"),
            data_payload=data_payload_dict,
            data_meta=data_meta,
            execution_time_ms=round(execution_time, 2)
        )

    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        print(f"[API] Error: {e}")
        return InsightResponse(
            success=False,
            trace_id=trace_id,
            error=str(e),
            execution_time_ms=round(execution_time, 2)
        )


@app.get("/")
async def root():
    """Root endpoint - redirect to dashboard"""
    return HTMLResponse(content="""
    <html><head><meta http-equiv="refresh" content="0; url=/dashboard"></head></html>
    """)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard UI"""
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SQL Agent Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .loader { border-top-color: #3498db; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <div class="mb-8">
            <h1 class="text-3xl font-bold text-blue-400">SQL Agent Dashboard</h1>
            <p class="text-gray-400">Pregunta en lenguaje natural sobre tus datos</p>
        </div>
        <div class="mb-8 flex gap-4">
            <input type="text" id="question" placeholder="Ej: Como van las ventas? / Inventario / Agente AI"
                class="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-blue-500">
            <button onclick="runQuery()" class="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold">Consultar</button>
        </div>
        <div id="loading" class="hidden text-center py-8">
            <div class="loader w-12 h-12 border-4 border-gray-600 rounded-full mx-auto"></div>
            <p class="mt-4 text-gray-400">Procesando...</p>
        </div>
        <div id="error" class="hidden bg-red-900/50 border border-red-500 rounded-lg p-4 mb-8"></div>
        <div id="dashboard" class="hidden">
            <div class="mb-6"><h2 id="dashTitle" class="text-2xl font-bold"></h2><p id="dashSubtitle" class="text-gray-400"></p></div>
            <div id="kpis" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8"></div>
            <div id="narrative" class="bg-gray-800 rounded-lg p-6 mb-8"></div>
            <div id="meta" class="text-sm text-gray-500 mt-4"></div>
        </div>
        <div class="mt-8 border-t border-gray-700 pt-6">
            <p class="text-gray-400 mb-3">Consultas rapidas:</p>
            <div class="flex flex-wrap gap-2">
                <button onclick="quickQuery('Como van las ventas?')" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">Ventas</button>
                <button onclick="quickQuery('Mostrame el inventario')" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">Inventario</button>
                <button onclick="quickQuery('Productos con stock bajo')" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">Stock Bajo</button>
                <button onclick="quickQuery('Como esta el agente AI?')" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">Agente AI</button>
                <button onclick="quickQuery('Casos escalados')" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">Escalados</button>
            </div>
        </div>
    </div>
    <script>
        function quickQuery(q) { document.getElementById('question').value = q; runQuery(); }
        async function runQuery() {
            const question = document.getElementById('question').value.trim();
            if (!question) return;
            document.getElementById('loading').classList.remove('hidden');
            document.getElementById('dashboard').classList.add('hidden');
            document.getElementById('error').classList.add('hidden');
            try {
                const response = await fetch('/api/insights/run', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });
                const data = await response.json();
                if (!data.success) throw new Error(data.error || 'Error');
                renderDashboard(data);
            } catch (err) {
                document.getElementById('error').classList.remove('hidden');
                document.getElementById('error').textContent = err.message;
            } finally {
                document.getElementById('loading').classList.add('hidden');
            }
        }
        function resolveRef(ref, payload) {
            if (!payload || !ref) return 'N/A';
            const parts = ref.split('.');
            if (parts[0] === 'kpi' && payload.kpis) {
                return payload.kpis[parts[1]];
            }
            return ref;
        }
        function formatValue(value, format) {
            if (value === undefined || value === null) return 'N/A';
            if (format === 'currency') return '$' + Number(value).toLocaleString('es-AR', {minimumFractionDigits: 0, maximumFractionDigits: 0});
            if (format === 'number') return Number(value).toLocaleString('es-AR');
            if (format === 'percent') return value.toFixed(1) + '%';
            return value;
        }
        function renderDashboard(data) {
            const spec = data.dashboard_spec;
            const payload = data.data_payload || {};
            document.getElementById('dashTitle').textContent = spec.title;
            document.getElementById('dashSubtitle').textContent = spec.subtitle;

            // Render KPIs with real values
            const kpis = document.getElementById('kpis');
            kpis.innerHTML = '';
            (spec.slots.series || []).forEach(kpi => {
                const value = resolveRef(kpi.value_ref, payload);
                const formatted = formatValue(value, kpi.format);
                kpis.innerHTML += '<div class="bg-gray-800 rounded-lg p-4"><p class="text-gray-400 text-sm">'+kpi.label+'</p><p class="text-2xl font-bold text-blue-400">'+formatted+'</p></div>';
            });

            // Render Charts
            const chartsDiv = document.getElementById('charts') || createChartsDiv();
            chartsDiv.innerHTML = '<h3 class="font-semibold mb-3 text-blue-400">Gráficos</h3>';
            (spec.slots.charts || []).forEach(chart => {
                if (chart.type === 'table') {
                    const tableData = payload.tables?.find(t => t.name === chart.dataset_ref?.replace('table.','')) || {rows: []};
                    let tableHtml = '<div class="mb-6"><h4 class="text-lg font-medium mb-2">'+chart.title+'</h4>';
                    tableHtml += '<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b border-gray-700">';
                    (chart.columns || []).forEach(col => { tableHtml += '<th class="text-left py-2 px-3 text-gray-400">'+col+'</th>'; });
                    tableHtml += '</tr></thead><tbody>';
                    (tableData.rows || []).slice(0, chart.max_rows || 10).forEach(row => {
                        tableHtml += '<tr class="border-b border-gray-800">';
                        (chart.columns || []).forEach(col => {
                            let val = row[col];
                            if (col === 'monto' && val) val = '$' + Number(val).toLocaleString('es-AR');
                            tableHtml += '<td class="py-2 px-3">'+(val || '-')+'</td>';
                        });
                        tableHtml += '</tr>';
                    });
                    tableHtml += '</tbody></table></div></div>';
                    chartsDiv.innerHTML += tableHtml;
                } else if (chart.type === 'bar_chart') {
                    const topData = payload.top_items?.find(t => t.ranking_name === chart.dataset_ref?.replace('top.','')) || {items: []};
                    let barHtml = '<div class="mb-6"><h4 class="text-lg font-medium mb-2">'+chart.title+'</h4>';
                    (topData.items || []).forEach(item => {
                        const pct = Math.min(100, (item.value / (topData.items[0]?.value || 1)) * 100);
                        barHtml += '<div class="mb-2"><div class="flex justify-between text-sm mb-1"><span>'+item.title+'</span><span class="text-blue-400">$'+Number(item.value).toLocaleString('es-AR')+'</span></div>';
                        barHtml += '<div class="h-4 bg-gray-700 rounded"><div class="h-4 bg-blue-500 rounded" style="width:'+pct+'%"></div></div></div>';
                    });
                    barHtml += '</div>';
                    chartsDiv.innerHTML += barHtml;
                }
            });

            // Render Narrative
            const narrative = document.getElementById('narrative');
            narrative.innerHTML = '<h3 class="font-semibold mb-3 text-blue-400">Insights</h3>';
            (spec.slots.narrative || []).forEach(n => {
                narrative.innerHTML += '<p class="mb-2 text-gray-300">'+(n.type==='headline'?'<strong>':'')+n.text+(n.type==='headline'?'</strong>':'')+'</p>';
            });

            document.getElementById('meta').innerHTML = 'Trace: '+data.trace_id+' | Tiempo: '+(data.execution_time_ms/1000).toFixed(1)+'s | Refs: '+(data.data_meta?.available_refs?.length||0);
            document.getElementById('dashboard').classList.remove('hidden');
        }
        function createChartsDiv() {
            const div = document.createElement('div');
            div.id = 'charts';
            div.className = 'bg-gray-800 rounded-lg p-6 mb-8';
            document.getElementById('narrative').before(div);
            return div;
        }
        document.getElementById('question').addEventListener('keypress', e => { if (e.key === 'Enter') runQuery(); });
    </script>
</body>
</html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
