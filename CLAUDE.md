# SQL Agent - Asistente de Analytics con IA

## Estructura del Proyecto

```
SQL-AGENT/
├── backend/           # FastAPI + LangGraph
│   ├── app/
│   │   ├── agents/    # IntentRouter, DataAgent, PresentationAgent
│   │   ├── api/       # Endpoints (v1_chat.py)
│   │   ├── graphs/    # LangGraph orchestration
│   │   ├── sql/       # Allowlist queries, schema
│   │   └── db/        # Supabase client
│   └── tests/
├── frontend/          # Next.js 14 + Tailwind
│   ├── app/           # Pages (App Router)
│   ├── components/    # React components
│   └── lib/           # Utils, types, validation
└── .claude/           # Claude Code config
```

## Stack Tecnologico

### Backend
- FastAPI + Uvicorn
- LangGraph (orquestacion multi-agente)
- LangSmith (observabilidad)
- Google Gemini / OpenRouter (LLM)
- Supabase (PostgreSQL)

### Frontend
- Next.js 14 (App Router)
- Tailwind CSS (dark theme)
- Recharts (graficos)
- Zod v4 (validacion)
- AI SDK v5 protocol (SSE streaming)

## Comandos

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python -m app.main
# Server: http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
# App: http://localhost:3000
```

## API Endpoints

- `POST /v1/chat/stream` - SSE streaming (AI SDK v5)
- `POST /api/insights/run` - Request unico
- `GET /api/health` - Health check

## Supabase

- Project: `zaqpiuwacinvebfttygm`
- URL: https://zaqpiuwacinvebfttygm.supabase.co

## Notas de Desarrollo

- El IntentRouter usa heuristicas (keywords) para clasificar queries
- Los typos comunes estan mapeados (ej: "ventesa" -> ventas)
- El frontend usa Zod v4 (syntax diferente a v3)
- SSE usa protocol DATA de AI SDK v5

## Comandos Personalizados

### /documentacion
Actualiza la documentacion completa del repositorio en `DOC/ARQUITECTURA_COMPLETA.md`.

**Cuando se ejecuta este comando:**
1. Analiza toda la estructura del proyecto
2. Revisa los archivos clave de cada directorio
3. Documenta el flujo de datos frontend → backend → database
4. Actualiza la arquitectura de agentes LangGraph
5. Lista los endpoints API actuales
6. Actualiza configuracion y troubleshooting

**Archivo generado:** `DOC/ARQUITECTURA_COMPLETA.md`

### /test-local
Ejecuta pruebas del sistema en localhost:
1. Verifica health del backend
2. Prueba queries de stock, ventas, productos
3. Reporta resultados

## Documentacion

- **CLAUDE.md** - Este archivo (instrucciones para Claude)
- **DOC/ARQUITECTURA_COMPLETA.md** - Documentacion tecnica completa
- **DOC/ARQUITECTURA_IA.md** - Arquitectura de agentes IA
