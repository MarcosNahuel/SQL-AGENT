"""
robust_parser.py - Parsers JSON robustos con auto-corrección

Implementa OutputFixingParser y estrategias de retry para manejar
salidas LLM mal formateadas sin fallar catastróficamente.
"""
import re
import json
from typing import Type, TypeVar, Optional, Any, Dict
from pydantic import BaseModel, ValidationError

T = TypeVar('T', bound=BaseModel)


class RobustJSONParser:
    """
    Parser JSON robusto con múltiples estrategias de recuperación.

    Orden de intentos:
    1. Parse directo
    2. Limpiar markdown
    3. Extraer JSON con regex
    4. Fix de comillas simples
    5. OutputFixing con LLM (opcional)
    """

    def __init__(self, llm=None, max_retries: int = 2):
        """
        Args:
            llm: LLM para auto-corrección (opcional)
            max_retries: Intentos máximos de corrección con LLM
        """
        self.llm = llm
        self.max_retries = max_retries

    def parse(self, content: str, schema: Type[T] = None) -> Dict[str, Any]:
        """
        Parsea contenido JSON con múltiples estrategias.

        Args:
            content: Texto a parsear (puede contener markdown, texto extra)
            schema: Clase Pydantic para validación (opcional)

        Returns:
            Dict parseado y opcionalmente validado
        """
        if not content or not content.strip():
            return {}

        content = content.strip()
        parsed = None

        # Estrategia 1: Parse directo
        parsed = self._try_direct_parse(content)
        if parsed is not None:
            return self._validate_schema(parsed, schema)

        # Estrategia 2: Limpiar markdown
        cleaned = self._clean_markdown(content)
        if cleaned != content:
            parsed = self._try_direct_parse(cleaned)
            if parsed is not None:
                return self._validate_schema(parsed, schema)

        # Estrategia 3: Extraer JSON con regex
        extracted = self._extract_json_regex(content)
        if extracted:
            parsed = self._try_direct_parse(extracted)
            if parsed is not None:
                return self._validate_schema(parsed, schema)

        # Estrategia 4: Fix de comillas
        fixed = self._fix_quotes(content)
        if fixed != content:
            parsed = self._try_direct_parse(fixed)
            if parsed is not None:
                return self._validate_schema(parsed, schema)

        # Estrategia 5: OutputFixing con LLM
        if self.llm:
            parsed = self._fix_with_llm(content, schema)
            if parsed is not None:
                return self._validate_schema(parsed, schema)

        # Fallback: intento desesperado de extraer estructura
        return self._extract_structured_fallback(content)

    def _try_direct_parse(self, content: str) -> Optional[Dict]:
        """Intenta parsear JSON directamente"""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    def _clean_markdown(self, content: str) -> str:
        """Limpia bloques de código markdown"""
        # ```json ... ``` o ``` ... ```
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if match:
            return match.group(1).strip()
        return content

    def _extract_json_regex(self, content: str) -> Optional[str]:
        """Extrae objeto JSON usando regex"""
        # Buscar objeto { ... }
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            return match.group(0)

        # Buscar array [ ... ]
        match = re.search(r'\[[\s\S]*\]', content)
        if match:
            return match.group(0)

        return None

    def _fix_quotes(self, content: str) -> str:
        """Intenta arreglar comillas simples (Python dict syntax)"""
        # Solo si no tiene comillas dobles
        if "'" in content and '"' not in content:
            # Reemplazar 'key' por "key"
            fixed = re.sub(r"'(\w+)'", r'"\1"', content)
            # Reemplazar : 'value' por : "value"
            fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
            return fixed
        return content

    def _fix_with_llm(self, content: str, schema: Type[T] = None) -> Optional[Dict]:
        """Usa LLM para corregir JSON malformado"""
        if not self.llm:
            return None

        schema_hint = ""
        if schema:
            # Extraer campos esperados del schema
            fields = list(schema.model_fields.keys())
            schema_hint = f"\nCampos esperados: {fields}"

        prompt = f"""El siguiente texto debería ser un JSON válido pero tiene errores.
Corrige los errores y devuelve SOLO el JSON corregido, sin explicaciones.
{schema_hint}

Texto a corregir:
{content}

JSON corregido:"""

        for attempt in range(self.max_retries):
            try:
                from langchain_core.messages import HumanMessage
                response = self.llm.invoke([HumanMessage(content=prompt)])
                fixed = str(response.content).strip()
                fixed = self._clean_markdown(fixed)
                return json.loads(fixed)
            except Exception as e:
                print(f"[RobustParser] LLM fix attempt {attempt+1} failed: {e}")
                continue

        return None

    def _validate_schema(self, data: Dict, schema: Type[T] = None) -> Dict:
        """Valida contra schema Pydantic si se proporciona"""
        if not schema or not data:
            return data

        try:
            validated = schema.model_validate(data)
            return validated.model_dump()
        except ValidationError as e:
            print(f"[RobustParser] Schema validation failed: {e}")
            # Retornar datos sin validar
            return data

    def _extract_structured_fallback(self, content: str) -> Dict:
        """Fallback: intentar extraer estructura mínima con regex"""
        result = {}

        # Intentar extraer query_ids
        query_ids_match = re.search(
            r'query_ids["\']?\s*:\s*\[(.*?)\]',
            content,
            re.IGNORECASE
        )
        if query_ids_match:
            ids_str = query_ids_match.group(1)
            ids = re.findall(r'["\']([^"\']+)["\']', ids_str)
            if ids:
                result['query_ids'] = ids

        # Intentar extraer params
        params_match = re.search(
            r'params["\']?\s*:\s*\{([^}]*)\}',
            content,
            re.IGNORECASE
        )
        if params_match:
            result['params'] = {}

        print(f"[RobustParser] Fallback extracted: {result}")
        return result


class OutputFixingParser:
    """
    Parser que usa LLM para corregir salidas malformadas.
    Compatible con la interfaz de LangChain.
    """

    def __init__(self, schema: Type[T], llm, max_retries: int = 2):
        self.schema = schema
        self.llm = llm
        self.max_retries = max_retries
        self.robust_parser = RobustJSONParser(llm=llm, max_retries=max_retries)

    def parse(self, text: str) -> T:
        """
        Parsea texto y valida contra schema Pydantic.

        Raises:
            ValueError: Si no puede parsear después de todos los intentos
        """
        data = self.robust_parser.parse(text, self.schema)

        if not data:
            raise ValueError(f"Could not parse: {text[:200]}")

        try:
            return self.schema.model_validate(data)
        except ValidationError as e:
            # Intentar corrección con LLM
            if self.llm:
                corrected = self._correct_with_llm(text, e)
                if corrected:
                    return self.schema.model_validate(corrected)
            raise ValueError(f"Validation failed: {e}")

    def _correct_with_llm(self, original: str, error: ValidationError) -> Optional[Dict]:
        """Usa LLM para corregir errores de validación"""
        prompt = f"""El JSON tiene errores de validación:
Error: {error}

JSON original:
{original}

Corrige el JSON para que cumpla con los requisitos. Devuelve SOLO el JSON corregido."""

        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            cleaned = self.robust_parser._clean_markdown(str(response.content))
            return json.loads(cleaned)
        except Exception:
            return None


# Singleton para uso global
_global_parser: Optional[RobustJSONParser] = None


def get_robust_parser(llm=None) -> RobustJSONParser:
    """Obtiene el parser global o crea uno nuevo"""
    global _global_parser
    if _global_parser is None or llm is not None:
        _global_parser = RobustJSONParser(llm=llm)
    return _global_parser


def parse_json_robust(content: str, schema: Type[T] = None, llm=None) -> Dict[str, Any]:
    """
    Helper function para parsear JSON de forma robusta.

    Args:
        content: Texto a parsear
        schema: Clase Pydantic para validación (opcional)
        llm: LLM para auto-corrección (opcional)

    Returns:
        Dict parseado
    """
    parser = RobustJSONParser(llm=llm)
    return parser.parse(content, schema)
