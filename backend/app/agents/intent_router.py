"""
Intent Router - Decide que agentes invocar basado en la pregunta

El router analiza la pregunta del usuario y decide:
1. Si es conversacional (saludo, ayuda) -> respuesta directa
2. Si necesita SQL -> invocar DataAgent
3. Si necesita dashboard -> invocar PresentationAgent
4. Si es ambigua -> pedir clarificacion con opciones contextuales
"""
import re
import os
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field


class ClarificationData(BaseModel):
    """Datos para preguntas de clarificacion"""
    question: str = Field(..., description="Pregunta para el usuario")
    options: List[str] = Field(default_factory=list, description="Opciones sugeridas")
    understood_context: str = Field("", description="Lo que entendimos de la pregunta")

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

    # Datos de clarificacion (cuando response_type == CLARIFICATION)
    clarification: Optional[ClarificationData] = Field(None, description="Pregunta de clarificacion con opciones")

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

    # Patrones que indican ambiguedad
    AMBIGUITY_PATTERNS = [
        # Pronombres sin contexto claro
        (r"^(eso|esto|aquello|ese|este|aquel)\b", "pronoun_without_context"),
        (r"^(lo|la|los|las|le|les)\s+\w+$", "short_pronoun"),
        # Preguntas muy cortas sin dominio claro
        (r"^(cuanto|cuantos|cuantas|que|como)\s*\?*$", "too_short"),
        # "Mostrame" sin objeto claro
        (r"^(mostrame|muestrame|dame|dime)\s*\?*$", "show_without_object"),
        # Comparaciones sin especificar qué
        (r"^(comparar?|versus|vs)\s*$", "compare_without_subject"),
    ]

    # Palabras que indican multiples dominios (posible ambiguedad)
    MULTI_DOMAIN_INDICATORS = {
        "ventas e inventario": ["sales", "inventory"],
        "productos vendidos": ["sales", "inventory"],  # Podria ser ambos
        "ordenes y stock": ["sales", "inventory"],
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

        # Paso 2: Detectar ambiguedad ANTES de procesar
        is_ambiguous, ambiguity_type = self._detect_ambiguity(q_lower)
        if is_ambiguous:
            clarification = self._generate_clarification(question, ambiguity_type)
            print(f"[IntentRouter] Ambiguous query detected: {ambiguity_type}")
            return RoutingDecision(
                response_type=ResponseType.CLARIFICATION,
                needs_sql=False,
                needs_dashboard=False,
                needs_narrative=False,
                clarification=clarification,
                direct_response=f"{clarification.understood_context}\n\n{clarification.question}",
                confidence=0.7,
                reasoning=f"Ambiguous query: {ambiguity_type}"
            )

        # Paso 3: Detectar si necesita datos
        needs_data = any(kw in q_lower for kw in self.DATA_KEYWORDS)

        # Paso 4: Detectar si necesita dashboard
        needs_dashboard = any(kw in q_lower for kw in self.DASHBOARD_KEYWORDS)

        # Paso 5: Si pide dashboard explicitamente, tambien necesita datos
        if needs_dashboard and not needs_data:
            needs_data = True

        # Paso 6: Detectar dominio
        domain = self._detect_domain(q_lower)

        # Paso 7: Determinar tipo de respuesta
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

    def _detect_ambiguity(self, q_lower: str) -> tuple[bool, str]:
        """
        Detecta si la pregunta es ambigua y necesita clarificacion.

        Returns:
            (is_ambiguous, ambiguity_type)
        """
        # Verificar patrones de ambiguedad explicitos
        for pattern, ambiguity_type in self.AMBIGUITY_PATTERNS:
            if re.search(pattern, q_lower):
                return True, ambiguity_type

        # Pregunta muy corta (menos de 3 palabras) sin keywords claros
        words = q_lower.split()
        if len(words) < 3:
            has_clear_keyword = any(kw in q_lower for kw in self.DATA_KEYWORDS + self.DASHBOARD_KEYWORDS)
            if not has_clear_keyword:
                return True, "too_short"

        # Detectar multiples dominios en conflicto
        domain_scores = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > 0:
                domain_scores[domain] = score

        # Si hay 2+ dominios con scores similares, es ambiguo
        if len(domain_scores) >= 2:
            scores = sorted(domain_scores.values(), reverse=True)
            if len(scores) >= 2 and scores[0] == scores[1]:
                return True, "multi_domain"

        # Preguntas de comparacion sin periodo claro
        if any(kw in q_lower for kw in ["comparar", "comparacion", "versus", "vs"]):
            has_time_ref = any(kw in q_lower for kw in [
                "mes", "semana", "dia", "año", "ayer", "hoy",
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
            ])
            if not has_time_ref:
                return True, "comparison_without_period"

        return False, ""

    def _generate_clarification(self, question: str, ambiguity_type: str) -> ClarificationData:
        """
        Genera una pregunta de clarificacion contextual basada en el tipo de ambiguedad.
        """
        q_lower = question.lower()

        if ambiguity_type == "pronoun_without_context":
            return ClarificationData(
                question="No tengo contexto previo. Que datos te gustaria ver?",
                options=[
                    "Ventas del mes actual",
                    "Estado del inventario",
                    "Rendimiento del agente AI",
                    "Ordenes recientes"
                ],
                understood_context="Detecte una referencia a algo previo, pero no tengo ese contexto."
            )

        elif ambiguity_type == "too_short":
            # Intentar detectar intencion parcial
            partial_domain = self._detect_domain(q_lower) if len(q_lower) > 2 else None
            if partial_domain == "sales":
                return ClarificationData(
                    question="Sobre ventas, que te gustaria saber?",
                    options=[
                        "Total de ventas del mes",
                        "Productos mas vendidos",
                        "Tendencia de ventas",
                        "Comparar con mes anterior"
                    ],
                    understood_context="Parece que preguntas sobre ventas."
                )
            elif partial_domain == "inventory":
                return ClarificationData(
                    question="Sobre inventario, que te gustaria saber?",
                    options=[
                        "Productos con stock bajo",
                        "Resumen de inventario",
                        "Productos que necesitan reposicion",
                        "Alertas de stock"
                    ],
                    understood_context="Parece que preguntas sobre inventario."
                )
            else:
                return ClarificationData(
                    question="Tu pregunta es muy breve. Sobre que area te gustaria saber?",
                    options=[
                        "Ventas y ordenes",
                        "Inventario y stock",
                        "Agente AI e interacciones",
                        "Casos escalados"
                    ],
                    understood_context="No pude identificar claramente el tema."
                )

        elif ambiguity_type == "show_without_object":
            return ClarificationData(
                question="Que te gustaria que te muestre?",
                options=[
                    "Dashboard de ventas",
                    "Estado del inventario",
                    "Metricas del agente AI",
                    "Ordenes recientes"
                ],
                understood_context="Quieres ver algo, pero no especificaste que."
            )

        elif ambiguity_type == "compare_without_subject":
            return ClarificationData(
                question="Que te gustaria comparar y en que periodo?",
                options=[
                    "Ventas: este mes vs anterior",
                    "Inventario: actual vs hace 30 dias",
                    "Rendimiento AI: esta semana vs anterior"
                ],
                understood_context="Quieres hacer una comparacion."
            )

        elif ambiguity_type == "multi_domain":
            domains_found = []
            for domain, keywords in self.DOMAIN_KEYWORDS.items():
                if any(kw in q_lower for kw in keywords):
                    domains_found.append(domain)

            domain_names = {
                "sales": "ventas",
                "inventory": "inventario",
                "conversations": "interacciones AI",
                "escalations": "casos escalados",
                "presale": "preventa"
            }
            domain_labels = [domain_names.get(d, d) for d in domains_found]

            return ClarificationData(
                question=f"Mencionas varios temas ({', '.join(domain_labels)}). En cual te enfoco?",
                options=[domain_names.get(d, d).capitalize() for d in domains_found],
                understood_context=f"Detecte multiples temas: {', '.join(domain_labels)}."
            )

        elif ambiguity_type == "comparison_without_period":
            return ClarificationData(
                question="Que periodos quieres comparar?",
                options=[
                    "Este mes vs mes anterior",
                    "Esta semana vs semana anterior",
                    "Ultimos 7 dias vs 7 dias previos",
                    "Este año vs año anterior"
                ],
                understood_context="Quieres comparar, pero no especificaste los periodos."
            )

        # Fallback generico
        return ClarificationData(
            question="Podrias ser mas especifico? Que datos necesitas?",
            options=[
                "Ventas y ordenes",
                "Inventario y stock",
                "Agente AI",
                "Casos escalados"
            ],
            understood_context="No pude interpretar completamente tu pregunta."
        )

    def _route_with_llm(self, question: str) -> RoutingDecision:
        """
        Usa LLM para clasificación semántica cuando las heurísticas no son claras.
        Ahora puede decidir pedir clarificación si la pregunta es ambigua.
        """
        import json

        system_prompt = """Eres un clasificador de intenciones para un sistema de analytics de e-commerce.
Analiza la pregunta del usuario y determina:
1. response_type:
   - "dashboard" (necesita visualización/análisis de datos)
   - "data_only" (solo números, sin gráficos)
   - "conversational" (saludo/ayuda/pregunta general)
   - "clarification" (la pregunta es ambigua y necesitas más contexto)
2. domain: "sales" (ventas/órdenes), "inventory" (productos/stock), "conversations" (agente AI/escalados)
3. Si response_type es "clarification", incluye:
   - clarification_question: pregunta concisa para el usuario
   - clarification_options: lista de 2-4 opciones sugeridas
   - understood_context: qué entendiste de la pregunta original

IMPORTANTE: Usa "clarification" solo cuando:
- La pregunta es muy vaga o corta (ej: "datos", "mostrame")
- Falta contexto crítico (periodo, dominio, métrica específica)
- Hay múltiples interpretaciones válidas

Responde SOLO con JSON válido:
{"response_type": "...", "domain": "...", "reasoning": "...", "clarification_question": "...", "clarification_options": [...], "understood_context": "..."}"""

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Pregunta: {question}")
            ])

            content = str(response.content).strip()
            # Intentar parsear JSON
            if "```" in content:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    content = match.group(1).strip()

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group(0)

            data = json.loads(content)
            resp_type = data.get("response_type", "dashboard")
            domain = data.get("domain", "sales")

            if resp_type == "clarification":
                clarification = ClarificationData(
                    question=data.get("clarification_question", "Podrias ser mas especifico?"),
                    options=data.get("clarification_options", ["Ventas", "Inventario", "Agente AI"]),
                    understood_context=data.get("understood_context", "")
                )
                print(f"[IntentRouter] LLM decided clarification: {clarification.question}")
                return RoutingDecision(
                    response_type=ResponseType.CLARIFICATION,
                    needs_sql=False,
                    needs_dashboard=False,
                    needs_narrative=False,
                    clarification=clarification,
                    direct_response=f"{clarification.understood_context}\n\n{clarification.question}" if clarification.understood_context else clarification.question,
                    confidence=0.75,
                    reasoning=f"LLM semantic clarification: {data.get('reasoning', 'N/A')}"
                )
            elif resp_type == "conversational":
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
