"""
Intent Router - Decide que agentes invocar basado en la pregunta

El router analiza la pregunta del usuario y decide:
1. Si es conversacional (saludo, ayuda) -> respuesta directa
2. Si necesita SQL -> invocar DataAgent
3. Si necesita dashboard -> invocar PresentationAgent
4. Si es ambigua -> pedir clarificacion
"""
import re
import os
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


class ResponseType(str, Enum):
    """Tipos de respuesta que el sistema puede dar"""
    CONVERSATIONAL = "conversational"  # Saludo, pregunta general, explicacion
    DATA_ONLY = "data_only"            # Solo datos, sin dashboard
    DASHBOARD = "dashboard"            # Dashboard completo con graficos
    CLARIFICATION = "clarification"    # Pedir mas contexto


class RoutingDecision(BaseModel):
    """Decision del Router sobre que agentes invocar"""
    response_type: ResponseType = Field(..., description="Tipo de respuesta a generar")
    needs_sql: bool = Field(False, description="Si necesita ejecutar queries SQL")
    needs_dashboard: bool = Field(False, description="Si necesita generar visualizacion")
    needs_narrative: bool = Field(True, description="Si necesita generar texto explicativo")

    # Si es conversacional o clarification, respuesta directa
    direct_response: Optional[str] = Field(None, description="Respuesta directa sin agentes")

    # Si necesita SQL, que dominio
    domain: Optional[str] = Field(None, description="Dominio de datos: sales, inventory, conversations")

    # Metadata
    confidence: float = Field(0.8, ge=0, le=1, description="Confianza en la decision")
    reasoning: str = Field("", description="Razonamiento para debugging")


class IntentRouter:
    """
    Router inteligente que decide que agentes invocar.

    Usa heuristicas primero (rapido, sin costo de LLM).
    Fallback a LLM para casos ambiguos.
    """

    # Patrones conversacionales - respuesta directa sin SQL
    CONVERSATIONAL_PATTERNS = [
        (r"^(hola|hey|buenas|buenos dias|buenas tardes|buenas noches|saludos)", "greeting"),
        (r"^(gracias|muchas gracias|thanks|ok|perfecto|genial|excelente)", "thanks"),
        (r"(que puedes hacer|que sabes hacer|ayuda|help|como funciona)", "help"),
        (r"(quien eres|que eres|como te llamas)", "identity"),
    ]

    # Keywords que indican necesidad de datos
    DATA_KEYWORDS = [
        "cuanto", "cuantos", "cuantas", "total", "suma", "cantidad",
        "vendimos", "ventas", "venta", "vendido", "ventesa", "vetas",  # Typos comunes
        "ordenes", "orden", "pedidos", "pedido",
        "productos", "producto", "inventario", "stock",
        "escalados", "escalaciones", "casos",
        "agente", "ai", "bot", "interacciones",
        "preventa", "preguntas",
        "ingresos", "revenue", "facturacion",
        "promedio", "media", "kpi", "metricas",
        # Meses y fechas
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        "mes", "semana", "dia", "año", "trimestre", "periodo",
        # Verbos de consulta
        "dime", "dame", "decime", "quiero", "necesito", "busco"
    ]

    # Keywords que indican necesidad de dashboard/visualizacion
    DASHBOARD_KEYWORDS = [
        "mostrame", "muestrame", "muestra", "ver", "visualiza",
        "grafico", "graficos", "gráfico", "gráficos", "chart", "charts",
        "dashboard", "panel", "reporte",
        "tendencia", "tendencias", "evolucion", "evolución",
        "comparar", "comparacion", "comparación", "versus", "vs",
        "analisis", "análisis", "analiza", "analizar",  # Con y sin acento
        "pareto", "insight", "insights", "resumen", "ticket",
        # Preguntas analiticas complejas
        "reposicion", "reposición", "reponer", "necesitar", "recomendar",
        "bajo stock", "alta rotacion", "rotacion", "rotación",
        "quebrar", "quiebre", "agotar", "agotarse", "agotando", "faltante",
        "critico", "criticos", "crítico", "críticos", "alertas", "alerta",
        "proyeccion", "proyectar", "estimar", "predecir",
        "margen", "ganancia", "beneficio",
        "cyber", "cybermonday", "black friday", "hot sale",
        "crecimiento", "ciclo", "temporada",
        # Preguntas de estado/resumen (implican dashboard)
        "como van", "como estan", "como esta", "que tal", "como vamos",
        "como fue", "como fueron", "como estuvo", "como me fue",
        "resumen", "resume", "resumir", "resumime",
        "situacion", "estado de", "status",
        "ultimos", "ultimas", "recientes", "hoy", "ayer", "actualmente", "actual",
        "este mes", "esta semana", "este año",
        # Preguntas analíticas que requieren respuesta narrativa
        "cual fue", "cuál fue", "cual es", "cuál es",
        "mas vendido", "más vendido", "menos vendido",
        "mejor mes", "peor mes", "mejor dia", "peor dia",
        "que mes", "qué mes", "en que mes", "en qué mes",
        "que producto", "qué producto", "cuales", "cuáles",
        "aumentar stock", "aumentar inventario", "ponderar",
        "debo hacer", "deberia", "debería", "recomienda", "sugieres",
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    # Dominios de datos
    DOMAIN_KEYWORDS = {
        "sales": ["venta", "vendido", "orden", "pedido", "factura", "ingreso", "revenue"],
        "inventory": ["producto", "inventario", "stock", "disponible"],
        "conversations": ["agente", "ai", "bot", "interaccion", "conversacion", "mensaje"],
        "escalations": ["escalado", "escalacion", "caso", "soporte", "ticket"],
        "presale": ["preventa", "pregunta", "consulta"]
    }

    # Respuestas directas para casos conversacionales
    DIRECT_RESPONSES = {
        "greeting": "Hola! Soy SQL Agent, tu asistente de datos. Puedo ayudarte con:\n- Ventas y ordenes\n- Inventario y productos\n- Rendimiento del agente AI\n- Casos escalados\n\nQue te gustaria saber?",
        "thanks": "De nada! Si tienes mas preguntas sobre tus datos, estoy aqui para ayudarte.",
        "help": "Puedo ayudarte a analizar tus datos de negocio. Prueba preguntas como:\n- Como van las ventas?\n- Mostrame el inventario\n- Productos con stock bajo\n- Como esta el agente AI?\n- Ultimas ordenes",
        "identity": "Soy SQL Agent, un asistente de BI potenciado por IA. Analizo tus datos de ventas, inventario y servicio al cliente para darte insights accionables.",
        "clarification": "No estoy seguro de que necesitas. Puedo ayudarte con:\n- Ventas y ordenes\n- Inventario y stock\n- Agente AI e interacciones\n- Casos escalados\n\nQue area te interesa?"
    }

    def __init__(self):
        """Inicializa el router con LLM opcional para casos complejos"""
        self.use_openrouter = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        if openrouter_key and self.use_openrouter:
            self.llm = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent-Router"
                }
            )
        else:
            self.llm = ChatGoogleGenerativeAI(
                model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
                google_api_key=os.getenv("GEMINI_API_KEY"),
                temperature=0.1
            )

    def route(self, question: str) -> RoutingDecision:
        """
        Analiza la pregunta y decide que agentes invocar.

        Args:
            question: Pregunta del usuario

        Returns:
            RoutingDecision con la decision de routing
        """
        q_lower = question.lower().strip()

        # Paso 1: Verificar patrones conversacionales
        for pattern, response_key in self.CONVERSATIONAL_PATTERNS:
            if re.search(pattern, q_lower):
                return RoutingDecision(
                    response_type=ResponseType.CONVERSATIONAL,
                    needs_sql=False,
                    needs_dashboard=False,
                    needs_narrative=False,
                    direct_response=self.DIRECT_RESPONSES.get(response_key, ""),
                    confidence=0.95,
                    reasoning=f"Matched conversational pattern: {response_key}"
                )

        # Paso 2: Detectar si necesita datos
        needs_data = any(kw in q_lower for kw in self.DATA_KEYWORDS)

        # Paso 3: Detectar si necesita dashboard
        needs_dashboard = any(kw in q_lower for kw in self.DASHBOARD_KEYWORDS)

        # Paso 4: Si pide dashboard explicitamente, tambien necesita datos
        if needs_dashboard and not needs_data:
            needs_data = True

        # Paso 5: Detectar dominio
        domain = self._detect_domain(q_lower)

        # Paso 6: Determinar tipo de respuesta
        if not needs_data and not needs_dashboard:
            # No hay keywords claros - usar LLM para clasificación semántica
            print(f"[IntentRouter] No clear keywords, using LLM semantic routing...")
            return self._route_with_llm(question)

        if needs_dashboard:
            return RoutingDecision(
                response_type=ResponseType.DASHBOARD,
                needs_sql=True,
                needs_dashboard=True,
                needs_narrative=True,
                domain=domain,
                confidence=0.9,
                reasoning=f"Dashboard requested for domain: {domain}"
            )
        else:
            return RoutingDecision(
                response_type=ResponseType.DATA_ONLY,
                needs_sql=True,
                needs_dashboard=False,
                needs_narrative=True,
                domain=domain,
                confidence=0.85,
                reasoning=f"Data query for domain: {domain}"
            )

    def _detect_domain(self, q_lower: str) -> str:
        """Detecta el dominio de la pregunta"""
        domain_scores = {}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > 0:
                domain_scores[domain] = score

        if domain_scores:
            return max(domain_scores, key=domain_scores.get)

        return "sales"  # Default

    def _route_with_llm(self, question: str) -> RoutingDecision:
        """
        Usa LLM para clasificación semántica cuando las heurísticas no son claras.
        """
        import json

        system_prompt = """Eres un clasificador de intenciones para un sistema de analytics de e-commerce.
Analiza la pregunta del usuario y determina:
1. response_type: "dashboard" (necesita visualización/análisis), "data_only" (solo números), "conversational" (saludo/ayuda)
2. domain: "sales" (ventas/órdenes), "inventory" (productos/stock), "conversations" (agente AI/escalados)

Responde SOLO con JSON válido:
{"response_type": "dashboard|data_only|conversational", "domain": "sales|inventory|conversations", "reasoning": "explicación breve"}"""

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Pregunta: {question}")
            ])

            content = str(response.content).strip()
            # Intentar parsear JSON
            if "```" in content:
                import re
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    content = match.group(1).strip()

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group(0)

            data = json.loads(content)
            resp_type = data.get("response_type", "dashboard")
            domain = data.get("domain", "sales")

            if resp_type == "conversational":
                return RoutingDecision(
                    response_type=ResponseType.CONVERSATIONAL,
                    needs_sql=False,
                    needs_dashboard=False,
                    needs_narrative=False,
                    direct_response=self.DIRECT_RESPONSES.get("help", ""),
                    confidence=0.8,
                    reasoning=f"LLM semantic: {data.get('reasoning', 'N/A')}"
                )
            elif resp_type == "data_only":
                return RoutingDecision(
                    response_type=ResponseType.DATA_ONLY,
                    needs_sql=True,
                    needs_dashboard=False,
                    needs_narrative=True,
                    domain=domain,
                    confidence=0.8,
                    reasoning=f"LLM semantic: {data.get('reasoning', 'N/A')}"
                )
            else:  # dashboard
                return RoutingDecision(
                    response_type=ResponseType.DASHBOARD,
                    needs_sql=True,
                    needs_dashboard=True,
                    needs_narrative=True,
                    domain=domain,
                    confidence=0.8,
                    reasoning=f"LLM semantic: {data.get('reasoning', 'N/A')}"
                )

        except Exception as e:
            print(f"[IntentRouter] LLM fallback error: {e}")
            # Fallback seguro a dashboard con dominio sales
            return RoutingDecision(
                response_type=ResponseType.DASHBOARD,
                needs_sql=True,
                needs_dashboard=True,
                needs_narrative=True,
                domain="sales",
                confidence=0.5,
                reasoning=f"LLM error fallback: {str(e)[:50]}"
            )


# Singleton
_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """Obtiene o crea instancia del router"""
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router
