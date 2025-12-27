"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  validateDashboardPart,
  validateAgentStepPart,
  validateDataPayload,
  DashboardSpec,
  DataPayload,
} from "@/lib/streamParts";

// Types
export interface AgentStep {
  step: string;
  status: "start" | "progress" | "done" | "error";
  ts: string;
  detail?: Record<string, unknown>;
  message?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export interface DashboardState {
  spec: DashboardSpec | null;
  payload: DataPayload | null;
  traceId: string | null;
}

export type ConnectionStatus = "idle" | "connecting" | "streaming" | "error" | "disconnected";

interface UseAgentChatOptions {
  apiUrl?: string;
  userId?: string | null;
  conversationId?: string | null;
  onDashboardUpdate?: (dashboard: DashboardState) => void;
  onAgentStep?: (step: AgentStep) => void;
  onError?: (error: Error) => void;
  retryAttempts?: number;
  retryDelay?: number;
}

interface UseAgentChatReturn {
  // State
  messages: ChatMessage[];
  agentSteps: AgentStep[];
  dashboards: DashboardState[];
  currentDashboardIndex: number;
  isLoading: boolean;
  error: string | null;
  connectionStatus: ConnectionStatus;
  currentTraceId: string | null;

  // Actions
  sendMessage: (question: string) => Promise<void>;
  cancelRequest: () => void;
  clearError: () => void;
  setCurrentDashboardIndex: (index: number) => void;
  resetChat: () => void;

  // Computed
  currentDashboard: DashboardState | null;
}

export function useAgentChat(options: UseAgentChatOptions = {}): UseAgentChatReturn {
  const {
    apiUrl = "http://localhost:8000/v1/chat/stream",  // Direct backend
    userId,
    conversationId,
    onDashboardUpdate,
    onAgentStep,
    onError,
    retryAttempts = 2,
    retryDelay = 1000,
  } = options;

  // State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [dashboards, setDashboards] = useState<DashboardState[]>([]);
  const [currentDashboardIndex, setCurrentDashboardIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [currentTraceId, setCurrentTraceId] = useState<string | null>(null);

  // Refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentTraceIdRef = useRef<string | null>(null);
  const currentDashboardIndexRef = useRef(-1);
  const retryCountRef = useRef(0);

  // Keep refs in sync
  useEffect(() => {
    currentTraceIdRef.current = currentTraceId;
  }, [currentTraceId]);

  useEffect(() => {
    currentDashboardIndexRef.current = currentDashboardIndex;
  }, [currentDashboardIndex]);

  // Process SSE event
  const processSSEEvent = useCallback((eventData: string) => {
    if (eventData === "[DONE]") {
      setConnectionStatus("idle");
      return;
    }

    try {
      const parsed = JSON.parse(eventData);
      const partType = parsed.type;

      console.log("[SSE] Processing:", partType);

      // Handle trace data
      if (partType === "data-trace" && parsed.data) {
        const traceData = parsed.data as { trace_id?: string };
        if (traceData.trace_id) {
          setCurrentTraceId(traceData.trace_id);
        }
      }

      // Handle agent steps
      if (partType === "data-agent_step" && parsed.data) {
        const stepData = validateAgentStepPart(parsed.data);
        if (stepData) {
          const step = stepData as AgentStep;
          setAgentSteps((prev) => [...prev, step]);
          onAgentStep?.(step);
        }
      }

      // Handle dashboard spec
      if (partType === "data-dashboard" && parsed.data) {
        const dashboardSpec = validateDashboardPart(parsed.data);
        if (dashboardSpec) {
          setDashboards((prev) => {
            const newDashboard: DashboardState = {
              spec: dashboardSpec,
              payload: null,
              traceId: currentTraceIdRef.current,
            };
            const updated = [...prev, newDashboard];
            const newIndex = updated.length - 1;
            currentDashboardIndexRef.current = newIndex;
            setCurrentDashboardIndex(newIndex);
            onDashboardUpdate?.(newDashboard);
            return updated;
          });
        }
      }

      // Handle data payload
      if (partType === "data-payload" && parsed.data) {
        const payloadData = validateDataPayload(parsed.data);
        if (payloadData) {
          setDashboards((prev) => {
            const idx = currentDashboardIndexRef.current;
            if (idx >= 0 && prev[idx]) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], payload: payloadData };
              onDashboardUpdate?.(updated[idx]);
              return updated;
            }
            return prev;
          });
        }
      }

      // Handle text delta
      if (partType === "text-delta" && parsed.delta) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.role === "assistant") {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...lastMsg,
              content: lastMsg.content + parsed.delta,
            };
            return updated;
          }
          return prev;
        });
      }

    } catch (e) {
      console.warn("[SSE] Parse error:", e);
    }
  }, [onAgentStep, onDashboardUpdate]);

  // Send message with retry logic
  const sendMessageWithRetry = useCallback(async (
    question: string,
    signal: AbortSignal,
    attempt: number = 0
  ): Promise<void> => {
    console.log("[SSE] Sending to:", apiUrl, "question:", question, "userId:", userId, "conversationId:", conversationId);
    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          user_id: userId || null,
          conversation_id: conversationId || null,
        }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      setConnectionStatus("streaming");
      retryCountRef.current = 0;

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

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

      // Process remaining buffer
      if (buffer.startsWith("data: ")) {
        const data = buffer.slice(6).trim();
        if (data) processSSEEvent(data);
      }

    } catch (err) {
      const error = err as Error;
      console.error("[SSE] Fetch error:", error.name, error.message, "URL:", apiUrl);

      // Don't retry on abort
      if (error.name === "AbortError") {
        throw error;
      }

      // Retry on network errors
      if (attempt < retryAttempts) {
        console.log(`[SSE] Retry attempt ${attempt + 1}/${retryAttempts}`);
        retryCountRef.current = attempt + 1;
        setConnectionStatus("connecting");
        await new Promise(resolve => setTimeout(resolve, retryDelay * (attempt + 1)));
        return sendMessageWithRetry(question, signal, attempt + 1);
      }

      throw error;
    }
  }, [apiUrl, userId, conversationId, processSSEEvent, retryAttempts, retryDelay]);

  // Send message
  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isLoading) return;

    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Add placeholder assistant message
    const assistantMsg: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);

    // Reset state for new request
    setIsLoading(true);
    setAgentSteps([]);
    setError(null);
    setConnectionStatus("connecting");

    try {
      await sendMessageWithRetry(question, abortControllerRef.current.signal);
      setConnectionStatus("idle");
    } catch (err) {
      const error = err as Error;
      if (error.name !== "AbortError") {
        console.error("[Chat] Error:", error);
        setError(error.message);
        setConnectionStatus("error");
        onError?.(error);
      } else {
        setConnectionStatus("disconnected");
      }
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, sendMessageWithRetry, onError]);

  // Cancel request
  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsLoading(false);
      setConnectionStatus("disconnected");
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
    setConnectionStatus("idle");
  }, []);

  // Reset chat
  const resetChat = useCallback(() => {
    cancelRequest();
    setMessages([]);
    setAgentSteps([]);
    setDashboards([]);
    setCurrentDashboardIndex(-1);
    setError(null);
    setCurrentTraceId(null);
    setConnectionStatus("idle");
  }, [cancelRequest]);

  // Computed
  const currentDashboard = currentDashboardIndex >= 0 ? dashboards[currentDashboardIndex] : null;

  return {
    // State
    messages,
    agentSteps,
    dashboards,
    currentDashboardIndex,
    isLoading,
    error,
    connectionStatus,
    currentTraceId,

    // Actions
    sendMessage,
    cancelRequest,
    clearError,
    setCurrentDashboardIndex,
    resetChat,

    // Computed
    currentDashboard,
  };
}
