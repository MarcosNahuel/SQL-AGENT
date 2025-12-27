"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAgentChat, ChatMessage } from "@/hooks";
import { useAuth } from "@/contexts/AuthContext";
import { DashboardRenderer } from "@/components/DashboardRenderer";
import { DataPayload } from "@/lib/types";
import { AgentTimeline } from "@/components/AgentTimeline";
import { ConnectionStatusIndicator, ConnectionDot } from "@/components/ConnectionStatus";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  TrendingUp,
  Clock,
  Activity,
  X,
  RotateCcw,
  LogOut,
} from "lucide-react";

interface ConversationThread {
  id: string;
  question: string;
  conclusion: string;
  timestamp: Date;
  dashboardIndex: number;
}

const SUGGESTED_QUESTIONS = [
  "Como van las ventas?",
  "Mostrame el inventario",
  "Productos con stock bajo",
  "que producto puede necesitar reposicion debido a su bajo stock y alta rotacion?",
  "como me fue con el cyber monday?",
];

export default function Home() {
  const [input, setInput] = useState("");
  const [conversations, setConversations] = useState<ConversationThread[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auth context for user session
  const { user, conversationId, signOut, resetConversation, isLoading: authLoading } = useAuth();

  // Use our custom hook for all chat functionality
  const {
    messages,
    agentSteps,
    dashboards,
    currentDashboardIndex,
    isLoading,
    error,
    connectionStatus,
    currentTraceId,
    sendMessage,
    cancelRequest,
    clearError,
    setCurrentDashboardIndex,
    resetChat,
    currentDashboard,
  } = useAgentChat({
    // Direct backend call - CORS is configured
    apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1/chat/stream",
    userId: user?.id,
    conversationId: conversationId,
    onError: (err) => {
      console.error("[Chat Error]", err);
    },
  });

  // Handle new conversation (reset chat + generate new conversation ID)
  const handleNewConversation = useCallback(() => {
    resetChat();
    resetConversation();
  }, [resetChat, resetConversation]);

  // Handle logout
  const handleLogout = async () => {
    await signOut();
  };

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Handle suggested question click
  const handleSuggestedQuestion = (q: string) => {
    if (isLoading) return;
    sendMessage(q);
  };

  // Handle form submit
  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    sendMessage(input);
    setInput("");
  };

  // Navigate between dashboards
  const navigateDashboard = useCallback(
    (direction: "prev" | "next") => {
      if (dashboards.length === 0) return;
      if (direction === "prev") {
        setCurrentDashboardIndex(Math.max(0, currentDashboardIndex - 1));
      } else {
        setCurrentDashboardIndex(Math.min(dashboards.length - 1, currentDashboardIndex + 1));
      }
    },
    [dashboards.length, currentDashboardIndex, setCurrentDashboardIndex]
  );

  // Select conversation
  const selectConversation = (conv: ConversationThread) => {
    setCurrentDashboardIndex(conv.dashboardIndex);
  };

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-950">
        <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-gray-950 overflow-hidden">
      {/* Left Panel - Chat with Conversations (SCROLLABLE) */}
      <div className="w-[420px] border-r border-gray-800 flex flex-col bg-gray-900/50 h-full">
        {/* Header */}
        <div className="p-4 border-b border-gray-800 bg-gray-900">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white flex items-center gap-2">
                  SQL Agent
                  <ConnectionDot status={connectionStatus} />
                </h1>
                <p className="text-xs text-gray-500 truncate max-w-[150px]" title={user?.email || ""}>
                  {user?.email || "Dashboard Inteligente con IA"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {messages.length > 0 && (
                <button
                  onClick={handleNewConversation}
                  className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
                  title="Nueva conversacion"
                >
                  <RotateCcw className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={handleLogout}
                className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-red-400 transition-colors"
                title="Cerrar sesion"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
          {/* Connection status bar */}
          <div className="mt-3 flex items-center justify-between">
            <ConnectionStatusIndicator status={connectionStatus} />
            <div className="flex items-center gap-2">
              {conversationId && (
                <span className="text-xs text-blue-500/70 font-mono" title={conversationId}>
                  {conversationId.slice(0, 12)}
                </span>
              )}
              {currentTraceId && (
                <span className="text-xs text-gray-600 font-mono">
                  {currentTraceId.slice(0, 8)}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Conversations History */}
        {conversations.length > 0 && (
          <div className="border-b border-gray-800 max-h-48 overflow-y-auto">
            <div className="px-3 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-900/50">
              Conversaciones
            </div>
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => selectConversation(conv)}
                className={`w-full px-4 py-3 text-left border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors ${
                  currentDashboardIndex === conv.dashboardIndex
                    ? "bg-blue-900/20 border-l-2 border-l-blue-500"
                    : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  <MessageSquare className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-300 truncate">
                      {conv.question}
                    </p>
                    <p className="text-xs text-blue-400 mt-1 line-clamp-2">
                      {conv.conclusion}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <Clock className="w-3 h-3 text-gray-600" />
                      <span className="text-xs text-gray-600">
                        {conv.timestamp.toLocaleTimeString("es-AR", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="text-center py-8">
              <Bot className="w-16 h-16 text-gray-700 mx-auto mb-4" />
              <p className="text-gray-400 mb-2 font-medium">
                Bienvenido a SQL Agent
              </p>
              <p className="text-gray-600 text-sm mb-6">
                Pregunta en lenguaje natural sobre tus datos
              </p>
              <div className="space-y-2">
                {SUGGESTED_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSuggestedQuestion(q)}
                    className="w-full text-left px-4 py-3 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded-xl transition-all duration-200 border border-gray-800 hover:border-gray-700"
                  >
                    <div className="flex items-center gap-3">
                      <TrendingUp className="w-4 h-4 text-blue-500" />
                      {q}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg: ChatMessage) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${
                  msg.role === "user" ? "flex-row-reverse" : ""
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === "user"
                      ? "bg-blue-500"
                      : "bg-gradient-to-br from-gray-700 to-gray-800"
                  }`}
                >
                  {msg.role === "user" ? (
                    <User className="w-4 h-4 text-white" />
                  ) : (
                    <Bot className="w-4 h-4 text-white" />
                  )}
                </div>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-blue-500 text-white"
                      : "bg-gray-800 text-gray-200"
                  }`}
                >
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))
          )}

          {/* Loading state with Agent Timeline */}
          {isLoading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                <Loader2 className="w-4 h-4 text-white animate-spin" />
              </div>
              <div className="bg-gray-800/80 rounded-2xl px-4 py-3 min-w-[280px] max-w-[320px]">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-blue-400" />
                    <span className="text-sm text-blue-400 font-medium">
                      Procesando...
                    </span>
                  </div>
                  <button
                    onClick={cancelRequest}
                    className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-red-400 transition-colors"
                    title="Cancelar"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <AgentTimeline steps={agentSteps} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error display */}
        {error && (
          <div className="mx-4 mb-4 bg-red-500/10 border border-red-500/20 rounded-xl p-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
            <button
              onClick={clearError}
              className="p-1 rounded hover:bg-red-500/20 text-red-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Input */}
        <div className="p-4 border-t border-gray-800 bg-gray-900/50">
          <form onSubmit={handleFormSubmit} className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribe tu pregunta..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !(input || '').trim()}
              className="px-4 py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-xl transition-all duration-200 hover:scale-105 active:scale-95"
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 text-white animate-spin" />
              ) : (
                <Send className="w-5 h-5 text-white" />
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Right Panel - Dashboard with Navigation (FIXED - no scroll on outer) */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Navigation Header - Fixed at top */}
        {dashboards.length > 0 && (
          <div className="flex-shrink-0 px-6 py-3 border-b border-gray-800 bg-gray-900/30 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigateDashboard("prev")}
                disabled={currentDashboardIndex <= 0}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                <ChevronLeft className="w-5 h-5 text-gray-300" />
              </button>
              <div className="text-center">
                <span className="text-sm text-gray-400">Insight</span>
                <span className="mx-2 text-white font-bold">
                  {currentDashboardIndex + 1}
                </span>
                <span className="text-sm text-gray-400">
                  de {dashboards.length}
                </span>
              </div>
              <button
                onClick={() => navigateDashboard("next")}
                disabled={currentDashboardIndex >= dashboards.length - 1}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                <ChevronRight className="w-5 h-5 text-gray-300" />
              </button>
            </div>
            <div className="text-sm text-gray-500">
              {currentDashboard?.traceId && `Trace: ${currentDashboard.traceId}`}
            </div>
          </div>
        )}

        {/* Dashboard Content - Fixed viewport (scroll only if content overflows) */}
        <div className="flex-1 overflow-y-auto bg-gray-950">
          <div className="p-6 max-w-7xl mx-auto">
            {currentDashboard?.spec ? (
              <DashboardRenderer
                spec={currentDashboard.spec}
                payload={currentDashboard.payload as DataPayload | undefined}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-[70vh] text-center">
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center mb-6">
                  <Sparkles className="w-12 h-12 text-blue-400" />
                </div>
                <h2 className="text-2xl font-bold text-gray-300 mb-3">
                  Dashboard Inteligente
                </h2>
                <p className="text-gray-500 max-w-md leading-relaxed">
                  Haz una pregunta en el chat para ver insights sobre tus ventas,
                  inventario y rendimiento del agente AI.
                </p>
                <div className="mt-8 grid grid-cols-3 gap-4 text-center">
                  <div className="p-4 rounded-xl bg-gray-900/50 border border-gray-800">
                    <div className="text-2xl font-bold text-blue-400 mb-1">2</div>
                    <div className="text-xs text-gray-500">Graficos</div>
                  </div>
                  <div className="p-4 rounded-xl bg-gray-900/50 border border-gray-800">
                    <div className="text-2xl font-bold text-green-400 mb-1">4</div>
                    <div className="text-xs text-gray-500">KPIs</div>
                  </div>
                  <div className="p-4 rounded-xl bg-gray-900/50 border border-gray-800">
                    <div className="text-2xl font-bold text-purple-400 mb-1">AI</div>
                    <div className="text-xs text-gray-500">Insights</div>
                  </div>
                </div>
              </div>
            )}

            {/* Meta info */}
            {currentDashboard && (
              <div className="mt-8 pt-4 border-t border-gray-800 flex items-center justify-between text-sm text-gray-600">
                <span>Trace: {currentDashboard.traceId || "N/A"}</span>
                <span>SQL Agent v2.0 + UltraThink</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
