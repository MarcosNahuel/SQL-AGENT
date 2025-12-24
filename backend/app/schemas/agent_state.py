"""
Agent State Schemas - SQL-Agent v2 Architecture

Define los estados y tipos para el sistema multi-agente con:
- Supervisor Pattern
- Reflection/Auto-correction
- Chain-of-Thought SQL Generation
"""
from typing import TypedDict, Optional, List, Literal, Annotated, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

from .payload import DataPayload
from .dashboard import DashboardSpec

# Import RoutingDecision for type hints (avoid circular imports)
if TYPE_CHECKING:
    from ..agents.intent_router import RoutingDecision


# ============== Enums ==============

class AgentType(str, Enum):
    """Tipos de agentes disponibles en el sistema"""
    SUPERVISOR = "supervisor"
    SQL_WRITER = "sql_writer"
    DATA_EXECUTOR = "data_executor"
    PRESENTATION = "presentation"
    DIRECT_RESPONSE = "direct_response"


class ExecutionStatus(str, Enum):
    """Estados de ejecución de queries"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    CORRECTED = "corrected"


# ============== Structured Output Models ==============

class SQLOutput(BaseModel):
    """
    Salida estructurada del SQL Writer con Chain-of-Thought.
    Fuerza al LLM a razonar antes de generar SQL.
    """
    thought_process: str = Field(
        description="Explicación detallada de la lógica: qué tablas usar, qué JOINs, qué filtros y por qué."
    )
    sql_query: str = Field(
        description="La consulta SQL ejecutable en dialecto PostgreSQL. SOLO SELECT permitido."
    )
    tables_used: List[str] = Field(
        description="Lista de tablas involucradas en la consulta."
    )
    risk_assessment: str = Field(
        description="Evaluación de seguridad: confirmar solo lectura, sin datos sensibles expuestos."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Nivel de confianza en la query (0.0 - 1.0)"
    )


class SQLReflection(BaseModel):
    """
    Reflexión sobre un error de SQL para autocorrección.
    """
    error_analysis: str = Field(
        description="Análisis del error: qué falló y por qué."
    )
    correction_plan: str = Field(
        description="Plan de corrección: qué cambios hacer para arreglar el error."
    )
    corrected_sql: str = Field(
        description="La consulta SQL corregida."
    )
    learned_insight: str = Field(
        description="Insight aprendido para evitar este error en el futuro."
    )


class SupervisorDecision(BaseModel):
    """
    Decisión del Supervisor sobre qué agente invocar.
    """
    destination: Literal["sql_writer", "data_executor", "presentation", "direct_response", "__end__"] = Field(
        description="El agente al que delegar la tarea."
    )
    reasoning: str = Field(
        description="Justificación breve de la elección del agente."
    )
    task_description: str = Field(
        description="Descripción específica de la tarea para el agente."
    )


# ============== State Schemas ==============

class SQLExecutionResult(BaseModel):
    """Resultado de la ejecución de una query SQL"""
    query_id: str
    sql_query: str
    status: ExecutionStatus
    rows: Optional[List[dict]] = None
    row_count: int = 0
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0


class SQLAgentState(TypedDict):
    """
    Estado del subgrafo SQL Agent.
    Contiene campos específicos para reflexión y autocorrección.
    """
    # Input
    question: str
    date_from: Optional[str]
    date_to: Optional[str]

    # SQL Generation
    sql_output: Optional[SQLOutput]
    generated_queries: List[str]

    # Execution
    execution_results: List[SQLExecutionResult]
    current_error: Optional[str]

    # Reflection
    retry_count: int
    max_retries: int
    reflections: List[SQLReflection]

    # Schema Context
    schema_context: Optional[str]
    relevant_tables: List[str]

    # Output
    data_payload: Optional[DataPayload]


class InsightStateV2(TypedDict):
    """
    Estado del grafo principal v2 con Supervisor Pattern.

    Incluye:
    - Historial de mensajes con add_messages reducer
    - Campos para routing dinámico
    - Soporte para reflexión y corrección
    """
    # === Messages (con reducer para append automático) ===
    messages: Annotated[List[AnyMessage], add_messages]

    # === Input ===
    question: str
    date_from: Optional[str]
    date_to: Optional[str]
    filters: Optional[dict]

    # === Routing ===
    routing_decision: Optional[Any]  # RoutingDecision from intent_router
    current_agent: Optional[str]
    next_agent: Optional[str]
    supervisor_decision: Optional[SupervisorDecision]

    # === SQL Agent State (subgrafo) ===
    sql_output: Optional[SQLOutput]
    execution_results: List[SQLExecutionResult]
    retry_count: int
    max_retries: int
    current_error: Optional[str]
    reflections: List[SQLReflection]

    # === Data ===
    data_payload: Optional[DataPayload]

    # === Presentation ===
    dashboard_spec: Optional[DashboardSpec]
    direct_response: Optional[str]

    # === Metadata ===
    trace_id: Optional[str]
    error: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    agent_steps: List[dict]  # Historial de pasos para observabilidad


def create_initial_state(
    question: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    filters: Optional[dict] = None,
    trace_id: Optional[str] = None
) -> InsightStateV2:
    """
    Factory para crear el estado inicial del grafo.
    """
    import uuid

    return InsightStateV2(
        messages=[],
        question=question,
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        routing_decision=None,
        current_agent=None,
        next_agent=None,
        supervisor_decision=None,
        sql_output=None,
        execution_results=[],
        retry_count=0,
        max_retries=3,
        current_error=None,
        reflections=[],
        data_payload=None,
        dashboard_spec=None,
        direct_response=None,
        trace_id=trace_id or str(uuid.uuid4())[:8],
        error=None,
        started_at=datetime.utcnow().isoformat(),
        completed_at=None,
        agent_steps=[]
    )
