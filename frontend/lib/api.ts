import { InsightRequest, InsightResponse, StreamEvent } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function runInsight(request: InsightRequest): Promise<InsightResponse> {
  const response = await fetch(`${API_URL}/api/insights/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * SSE Streaming - Ejecuta insight con eventos en tiempo real
 * @param request - La consulta
 * @param onEvent - Callback para cada evento recibido
 * @returns Promise que resuelve con el resultado final
 */
export async function runInsightStream(
  request: InsightRequest,
  onEvent: (event: StreamEvent) => void
): Promise<InsightResponse | null> {
  const response = await fetch(`${API_URL}/api/insights/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: InsightResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events (format: "data: {...}\n\n")
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || ""; // Keep incomplete data for next iteration

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const jsonStr = line.slice(6); // Remove "data: " prefix
          const event: StreamEvent = JSON.parse(jsonStr);
          onEvent(event);

          // Si es el evento complete, extraer el resultado
          if (event.event === "complete" && event.result) {
            finalResult = {
              success: true,
              trace_id: event.trace_id || "",
              dashboard_spec: event.result.dashboard_spec,
              data_payload: event.result.data_payload,
              data_meta: event.result.data_meta,
            };
          }
        } catch (e) {
          console.error("Error parsing SSE event:", e);
        }
      }
    }
  }

  return finalResult;
}

export async function healthCheck(): Promise<{ status: string; version: string; database: string }> {
  const response = await fetch(`${API_URL}/api/health`);
  return response.json();
}

export async function getAvailableQueries(): Promise<{ queries: Record<string, string> }> {
  const response = await fetch(`${API_URL}/api/queries`);
  return response.json();
}
