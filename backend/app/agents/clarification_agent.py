"""
Clarification Agent - Generates dynamic, context-aware clarification questions using LLM

Este agente usa LLM para:
1. Determinar si realmente se necesita clarificacion
2. Generar preguntas contextuales y especificas
3. Proponer opciones inteligentes basadas en el contexto

Reemplaza el sistema determinista de templates en IntentRouter.
"""
import os
from typing import Optional, List
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..observability.langsmith import traced


class ClarificationAnalysis(BaseModel):
    """Salida estructurada del agente de clarificacion"""
    needs_clarification: bool = Field(
        description="Si realmente se necesita pedir clarificacion al usuario"
    )
    reasoning: str = Field(
        description="Razonamiento sobre por que se necesita o no clarificacion"
    )
    inferred_intent: Optional[str] = Field(
        default=None,
        description="Si no necesita clarificacion, cual es la intencion inferida"
    )
    inferred_domain: Optional[str] = Field(
        default=None,
        description="Dominio inferido: sales, inventory, conversations"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Pregunta de clarificacion contextual y especifica"
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="2-4 opciones sugeridas para el usuario"
    )
    understood_context: Optional[str] = Field(
        default=None,
        description="Lo que el agente entendio de la pregunta original"
    )


class ClarificationAgent:
    """
    Agente que usa LLM para generar clarificaciones dinamicas.

    A diferencia del sistema determinista anterior, este agente:
    - Analiza semanticamente si la pregunta realmente es ambigua
    - Genera preguntas contextuales especificas a lo que se detecto
    - Puede inferir la intencion y evitar pedir clarificacion innecesaria
    """

    SYSTEM_PROMPT = """Eres un agente de clarificacion para un sistema de Business Intelligence de e-commerce.

Tu trabajo es analizar preguntas ambiguas y decidir:
1. Si REALMENTE necesitan clarificacion (muchas veces puedes inferir la intencion)
2. Si necesitan clarificacion, generar una pregunta contextual y especifica

CONTEXTO DEL SISTEMA:
- Base de datos de e-commerce con: ventas/ordenes, inventario/productos, interacciones de agente AI
- Los usuarios preguntan sobre metricas de negocio, tendencias, alertas de stock, etc.

REGLAS IMPORTANTES:
1. NO pidas clarificacion si puedes inferir razonablemente la intencion
2. "producto mas vendido" claramente es sobre VENTAS (no inventario), no pidas clarificacion
3. "como van las ventas" es claro, no necesita clarificacion
4. "mostrame inventario" es claro, no necesita clarificacion
5. Solo pide clarificacion cuando hay AMBIGUEDAD REAL (ej: "comparar" sin especificar que)

CUANDO PEDIR CLARIFICACION:
- "mostrame" sin objeto (mostrame que?)
- "comparar" sin especificar periodos o metricas
- Pronombres sin contexto ("eso", "esto")
- Preguntas de 1-2 palabras muy vagas ("datos?", "ventas?")

CUANDO NO PEDIR CLARIFICACION (inferir intencion):
- "producto mas vendido" -> inferir: quiere saber que producto vendio mas (dominio: sales)
- "stock bajo" -> inferir: productos con stock critico (dominio: inventory)
- "como va el agente" -> inferir: metricas del agente AI (dominio: conversations)

Si decides que SI necesita clarificacion:
- Genera una pregunta corta y especifica
- Ofrece 2-4 opciones claras
- Menciona lo que entendiste de la pregunta original"""

    def __init__(self):
        """Inicializa el agente con LLM configurado"""
        use_openrouter = os.getenv("USE_OPENROUTER_PRIMARY", "false").lower() == "true"
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        if openrouter_key and use_openrouter:
            self.llm = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
                default_headers={
                    "HTTP-Referer": "https://sql-agent.local",
                    "X-Title": "SQL-Agent-ClarificationAgent"
                }
            )
        else:
            self.llm = ChatGoogleGenerativeAI(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
                google_api_key=os.getenv("GEMINI_API_KEY"),
                temperature=0.1
            )

    @traced("ClarificationAgent")
    def analyze(self, question: str, detected_ambiguity: Optional[str] = None) -> ClarificationAnalysis:
        """
        Analiza una pregunta y determina si necesita clarificacion.

        Args:
            question: La pregunta original del usuario
            detected_ambiguity: Tipo de ambiguedad detectada por heuristicas (opcional)

        Returns:
            ClarificationAnalysis con la decision y datos de clarificacion si aplica
        """
        context_msg = ""
        if detected_ambiguity:
            ambiguity_descriptions = {
                "multi_domain": "La pregunta menciona terminos de multiples dominios (ventas, inventario, etc)",
                "too_short": "La pregunta es muy corta y podria ser ambigua",
                "pronoun_without_context": "La pregunta usa pronombres sin contexto previo",
                "show_without_object": "Pide mostrar algo pero no especifica que",
                "comparison_without_period": "Pide comparar pero no especifica periodos"
            }
            context_msg = f"\n\nNOTA: El sistema detecto posible ambiguedad tipo '{detected_ambiguity}': {ambiguity_descriptions.get(detected_ambiguity, detected_ambiguity)}"

        try:
            structured_llm = self.llm.with_structured_output(ClarificationAnalysis)
            result: ClarificationAnalysis = structured_llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=f"Pregunta del usuario: \"{question}\"{context_msg}")
            ])

            print(f"[ClarificationAgent] needs_clarification={result.needs_clarification}, reasoning={result.reasoning[:50]}...")
            return result

        except Exception as e:
            print(f"[ClarificationAgent] Error: {e}")
            # Fallback: asumir que no necesita clarificacion, dejar que el sistema intente procesar
            return ClarificationAnalysis(
                needs_clarification=False,
                reasoning=f"Error en analisis, asumiendo intencion clara: {str(e)[:50]}",
                inferred_intent="dashboard de datos",
                inferred_domain="sales"
            )


# Singleton
_clarification_agent: Optional[ClarificationAgent] = None


def get_clarification_agent() -> ClarificationAgent:
    """Obtiene o crea instancia del agente de clarificacion"""
    global _clarification_agent
    if _clarification_agent is None:
        _clarification_agent = ClarificationAgent()
    return _clarification_agent
