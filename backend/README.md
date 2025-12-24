# SQL Agent Backend

Backend API for SQL Agent - An intelligent analytics assistant powered by LangGraph and LLMs.

## Features

- Multi-agent orchestration with LangGraph
- Natural language to SQL queries
- Intelligent intent routing (dashboard/data_only/conversational)
- Real-time SSE streaming with AI SDK v5 protocol
- Integration with Supabase database

## Tech Stack

- **Framework**: FastAPI
- **Agent Orchestration**: LangGraph
- **LLM**: Google Gemini / OpenRouter
- **Database**: Supabase (PostgreSQL)
- **Observability**: LangSmith

## Installation

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Run the server:
```bash
python -m app.main
```

Server runs at http://localhost:8000

## API Endpoints

- `POST /v1/chat/stream` - SSE streaming chat endpoint (AI SDK v5)
- `POST /api/insights/run` - Single request insights
- `GET /api/health` - Health check
- `GET /api/queries` - List available queries

## Architecture

```
app/
  agents/
    - intent_router.py    # Classifies user intent
    - data_agent.py       # Executes SQL queries
    - presentation_agent.py # Generates dashboard specs
  graphs/
    - insight_graph.py    # LangGraph orchestration
  api/
    - v1_chat.py          # SSE streaming endpoint
  sql/
    - allowlist.py        # Pre-approved SQL queries
    - schema_registry.py  # Database schema
```

## License

MIT
