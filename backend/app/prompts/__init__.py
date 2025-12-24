"""
Prompts Module

Contains all system prompts for SQL-Agent with UltraThink reasoning.
"""
from .ultrathink import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    NARRATIVE_GENERATION_PROMPT,
    QUERY_DECISION_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    get_orchestrator_prompt,
    get_narrative_prompt,
    get_query_decision_prompt,
    get_intent_prompt
)

__all__ = [
    "ORCHESTRATOR_SYSTEM_PROMPT",
    "NARRATIVE_GENERATION_PROMPT",
    "QUERY_DECISION_PROMPT",
    "INTENT_CLASSIFICATION_PROMPT",
    "get_orchestrator_prompt",
    "get_narrative_prompt",
    "get_query_decision_prompt",
    "get_intent_prompt"
]
