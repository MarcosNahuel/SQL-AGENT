# Integracion con Vercel AI SDK v5

## Resumen

SQL Agent usa el protocolo de streaming de **AI SDK v5** para comunicacion en tiempo real entre el backend (FastAPI) y frontend (Next.js). Esto permite mostrar el progreso del agente mientras procesa la consulta.

---

## Protocolo de Streaming

### Formato SSE (Server-Sent Events)

El backend emite eventos en formato SSE con el protocolo DATA de AI SDK v5:

```
data: {"type":"start","messageId":"msg-abc123"}
data: {"type":"text-start","textId":"text-abc123"}
data: {"type":"data-agent_step","data":{...}}
data: {"type":"data-dashboard","data":{...}}
data: {"type":"data-payload","data":{...}}
data: {"type":"text-delta","textId":"text-abc123","delta":"Respuesta..."}
data: {"type":"text-end","textId":"text-abc123"}
data: {"type":"finish","finishReason":"complete","messageId":"msg-abc123"}
data: [DONE]
```

### Tipos de Eventos

| Tipo | Descripcion |
|------|-------------|
| `start` | Inicio del mensaje, incluye `messageId` |
| `text-start` | Inicio de bloque de texto |
| `text-delta` | Delta de texto (streaming) |
| `text-end` | Fin de bloque de texto |
| `data-trace` | Info de trazabilidad (trace_id) |
| `data-agent_step` | Paso del agente (router, data, presentation) |
| `data-dashboard` | DashboardSpec completo |
| `data-payload` | DataPayload con datos reales |
| `data-meta` | Metadata de datasets |
| `finish` | Fin del mensaje |

---

## Backend (FastAPI)

### Endpoint SSE

```python
# backend/app/api/v1_chat.py

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """AI SDK v5 compatible streaming chat endpoint."""
    trace_id = str(uuid.uuid4())[:8]

    return StreamingResponse(
        generate_ai_sdk_stream(
            question=request.question,
            trace_id=trace_id,
            conversation_id=request.conversation_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-ui-message-stream": "v1",  # Header especial AI SDK
        }
    )
```

### Emitir Eventos

```python
def emit_sse(event_type: str, data: dict) -> str:
    """Format a server-sent event in AI SDK v5 format"""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"

def emit_custom_data(data_type: str, data: dict) -> str:
    """Emit a custom data part (data-xxx format)"""
    payload = {"type": f"data-{data_type}", "data": data}
    return f"data: {json.dumps(payload)}\n\n"

# Uso:
yield emit_sse("start", {"messageId": message_id})
yield emit_custom_data("agent_step", {"step": "router", "status": "progress"})
yield emit_custom_data("dashboard", dashboard_spec.model_dump())
yield emit_sse("finish", {"finishReason": "complete", "messageId": message_id})
yield "data: [DONE]\n\n"
```

---

## Frontend (Next.js)

### Procesamiento SSE Manual

En lugar de usar `useChat` de AI SDK (que espera formato OpenAI), procesamos SSE manualmente:

```typescript
// frontend/app/page.tsx

const processSSEEvent = useCallback((eventData: string) => {
  if (eventData === "[DONE]") return;

  try {
    const parsed = JSON.parse(eventData);
    const partType = parsed.type;

    // Handle trace data
    if (partType === "data-trace" && parsed.data) {
      setCurrentTraceId(parsed.data.trace_id);
    }

    // Handle agent steps
    if (partType === "data-agent_step" && parsed.data) {
      const stepData = validateAgentStepPart(parsed.data);
      if (stepData) {
        setAgentSteps((prev) => [...prev, stepData]);
      }
    }

    // Handle dashboard spec
    if (partType === "data-dashboard" && parsed.data) {
      const dashboardSpec = validateDashboardPart(parsed.data);
      if (dashboardSpec) {
        setDashboards((prev) => [...prev, { spec: dashboardSpec, payload: null }]);
      }
    }

    // Handle data payload
    if (partType === "data-payload" && parsed.data) {
      const payloadData = validateDataPayload(parsed.data);
      if (payloadData) {
        setDashboards((prev) => {
          const updated = [...prev];
          updated[updated.length - 1].payload = payloadData;
          return updated;
        });
      }
    }

    // Handle text delta
    if (partType === "text-delta" && parsed.delta) {
      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg?.role === "assistant") {
          return [...prev.slice(0, -1), { ...lastMsg, content: lastMsg.content + parsed.delta }];
        }
        return prev;
      });
    }
  } catch (e) {
    console.warn("[SSE] Parse error:", e);
  }
}, []);
```

### Fetch con Streaming

```typescript
const sendMessage = async (question: string) => {
  const response = await fetch("http://localhost:8000/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data) processSSEEvent(data);
      }
    }
  }
};
```

---

## Validacion con Zod

Usamos Zod v4 para validar los datos del stream:

```typescript
// frontend/lib/streamParts.ts

import { z } from 'zod';

// Agent Step
export const AgentStepPartSchema = z.object({
  step: z.string(),
  status: z.enum(['start', 'progress', 'done', 'error']),
  ts: z.string(),
  message: z.string().optional(),
  detail: z.record(z.string(), z.unknown()).optional(),
});

// Dashboard Spec
export const DashboardSpecSchema = z.object({
  title: z.string(),
  subtitle: z.string().nullable().optional(),
  conclusion: z.string().nullable().optional(),
  slots: SlotConfigSchema,
});

// Validators
export function validateAgentStepPart(data: unknown): AgentStepPart | null {
  const result = AgentStepPartSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateDashboardPart(data: unknown): DashboardPart | null {
  const result = DashboardSpecSchema.safeParse(data);
  return result.success ? result.data : null;
}
```

---

## Flujo Completo

```
1. Usuario escribe: "Como van las ventas?"

2. Frontend hace POST /v1/chat/stream

3. Backend emite eventos SSE:

   data: {"type":"start","messageId":"msg-abc123"}

   data: {"type":"data-trace","data":{"trace_id":"abc123"}}

   data: {"type":"data-agent_step","data":{"step":"router","status":"progress"}}

   data: {"type":"data-agent_step","data":{"step":"data_agent","status":"progress"}}

   data: {"type":"data-agent_step","data":{"step":"presentation","status":"progress"}}

   data: {"type":"data-dashboard","data":{"title":"Dashboard de Ventas",...}}

   data: {"type":"data-payload","data":{"kpis":{...},"time_series":[...]}}

   data: {"type":"text-start","textId":"text-abc123"}
   data: {"type":"text-delta","textId":"text-abc123","delta":"Ventas totales: $4.5M"}
   data: {"type":"text-end","textId":"text-abc123"}

   data: {"type":"finish","finishReason":"complete"}
   data: [DONE]

4. Frontend procesa cada evento:
   - AgentTimeline muestra pasos en tiempo real
   - DashboardRenderer recibe spec + payload
   - Chat muestra el texto

5. Usuario ve:
   - Timeline animado con pasos del agente
   - Dashboard con KPIs y graficos
   - Respuesta en el chat
```

---

## Diferencias vs OpenAI Format

| Aspecto | OpenAI Format | AI SDK v5 DATA |
|---------|---------------|----------------|
| Provider | Solo OpenAI | Cualquier backend |
| Custom Data | No soportado | `data-{type}` |
| Estructura | Rigida | Flexible |
| useChat | Compatible | Requiere procesamiento manual |

---

## Headers Importantes

```python
headers={
    "Cache-Control": "no-cache, no-transform",  # No cachear
    "Connection": "keep-alive",                  # Mantener conexion
    "X-Accel-Buffering": "no",                   # Desactivar buffering nginx
    "x-vercel-ai-ui-message-stream": "v1",       # Identificar como AI SDK
}
```

---

## Troubleshooting

### Stream no llega al frontend

1. Verificar CORS en backend
2. Verificar que `X-Accel-Buffering: no` esta presente
3. Verificar que no hay proxy buffeando

### Datos no se renderizan

1. Verificar que `data-dashboard` llega antes que `data-payload`
2. Verificar validacion Zod (usar `safeParse`)
3. Verificar refs en DashboardSpec vs DataPayload

### Timeline no se actualiza

1. Verificar que `data-agent_step` se emite
2. Verificar que el estado se actualiza correctamente
3. Verificar que el componente AgentTimeline recibe steps

---

## Recursos

- [Vercel AI SDK Docs](https://sdk.vercel.ai/docs)
- [SSE Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/concepts/streaming/)
