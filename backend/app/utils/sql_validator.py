"""
SQL Validator - Validación AST de queries SQL

Implementa validación de seguridad mediante análisis del AST:
- Solo permite SELECT (no INSERT, UPDATE, DELETE, DROP, etc.)
- Detecta operaciones peligrosas
- Valida estructura de la query
"""
from typing import Tuple, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

try:
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import ParseError
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    print("[SQL Validator] WARNING: sqlglot not installed. Using basic validation only.")


class SQLValidationError(Exception):
    """Error de validación de SQL"""
    pass


class SQLRiskLevel(str, Enum):
    """Niveles de riesgo de una query"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SQLValidationResult:
    """Resultado de la validación de SQL"""
    is_valid: bool
    risk_level: SQLRiskLevel
    tables_accessed: List[str]
    operations_found: List[str]
    errors: List[str]
    warnings: List[str]


# Operaciones prohibidas (destructivas)
FORBIDDEN_OPERATIONS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXECUTE", "CALL",
    "MERGE", "REPLACE", "UPSERT"
}

# Funciones peligrosas
DANGEROUS_FUNCTIONS = {
    "pg_read_file", "pg_read_binary_file", "pg_write_file",
    "lo_import", "lo_export", "dblink", "dblink_exec",
    "pg_execute_server_program", "copy"
}

# Tablas sensibles que requieren aprobación
SENSITIVE_TABLES = {
    "users", "credentials", "passwords", "secrets", "tokens",
    "api_keys", "auth_tokens", "sessions"
}


def validate_sql_basic(sql: str) -> Tuple[bool, str]:
    """
    Validación básica sin sqlglot.
    Detecta operaciones peligrosas mediante búsqueda de texto.
    """
    sql_upper = sql.upper().strip()

    # Verificar que empiece con SELECT
    if not sql_upper.startswith("SELECT"):
        # Permitir WITH ... SELECT (CTEs)
        if not (sql_upper.startswith("WITH") and "SELECT" in sql_upper):
            return False, "Solo se permiten queries SELECT"

    # Buscar operaciones prohibidas
    for op in FORBIDDEN_OPERATIONS:
        # Buscar la operación como palabra completa
        import re
        if re.search(rf'\b{op}\b', sql_upper):
            return False, f"Operación prohibida detectada: {op}"

    # Buscar funciones peligrosas
    sql_lower = sql.lower()
    for func in DANGEROUS_FUNCTIONS:
        if func in sql_lower:
            return False, f"Función peligrosa detectada: {func}"

    # Buscar comentarios SQL (posible inyección)
    if "--" in sql or "/*" in sql:
        return False, "Comentarios SQL no permitidos"

    # Buscar múltiples statements
    if sql.count(";") > 1:
        return False, "Solo se permite un statement por query"

    return True, "OK"


def validate_sql_ast(sql: str) -> SQLValidationResult:
    """
    Validación completa mediante análisis AST con sqlglot.
    """
    errors = []
    warnings = []
    tables_accessed = []
    operations_found = []

    # Validación básica primero
    is_basic_valid, basic_msg = validate_sql_basic(sql)
    if not is_basic_valid:
        return SQLValidationResult(
            is_valid=False,
            risk_level=SQLRiskLevel.CRITICAL,
            tables_accessed=[],
            operations_found=[],
            errors=[basic_msg],
            warnings=[]
        )

    if not SQLGLOT_AVAILABLE:
        # Sin sqlglot, solo validación básica
        return SQLValidationResult(
            is_valid=True,
            risk_level=SQLRiskLevel.LOW,
            tables_accessed=[],
            operations_found=["SELECT"],
            errors=[],
            warnings=["AST validation not available (sqlglot not installed)"]
        )

    try:
        # Parsear SQL a AST
        parsed = sqlglot.parse(sql, dialect="postgres")

        if not parsed:
            return SQLValidationResult(
                is_valid=False,
                risk_level=SQLRiskLevel.HIGH,
                tables_accessed=[],
                operations_found=[],
                errors=["No se pudo parsear el SQL"],
                warnings=[]
            )

        for statement in parsed:
            # Obtener tipo de statement
            stmt_type = type(statement).__name__
            operations_found.append(stmt_type)

            # Solo permitir SELECT
            if not isinstance(statement, exp.Select):
                if isinstance(statement, exp.With):
                    # CTEs son permitidos si el body es SELECT
                    if hasattr(statement, 'this') and isinstance(statement.this, exp.Select):
                        operations_found.append("WITH_SELECT")
                    else:
                        errors.append(f"CTE debe contener SELECT, encontrado: {type(statement.this).__name__}")
                else:
                    errors.append(f"Operación no permitida: {stmt_type}")
                    continue

            # Extraer tablas accedidas
            for table in statement.find_all(exp.Table):
                table_name = table.name.lower() if table.name else ""
                if table_name and table_name not in tables_accessed:
                    tables_accessed.append(table_name)

                # Verificar tablas sensibles
                if table_name in SENSITIVE_TABLES:
                    warnings.append(f"Acceso a tabla sensible: {table_name}")

            # Buscar subqueries que podrían ser peligrosas
            for subquery in statement.find_all(exp.Subquery):
                # Las subqueries deben ser SELECT
                if hasattr(subquery, 'this') and not isinstance(subquery.this, exp.Select):
                    errors.append("Subquery debe ser SELECT")

            # Buscar funciones peligrosas en el AST
            for func in statement.find_all(exp.Func):
                func_name = func.name.lower() if hasattr(func, 'name') else ""
                if func_name in DANGEROUS_FUNCTIONS:
                    errors.append(f"Función peligrosa: {func_name}")

            # Buscar UNION/INTERSECT/EXCEPT que podrían ocultar operaciones
            for union in statement.find_all(exp.Union):
                operations_found.append("UNION")
                # Verificar que ambos lados sean SELECT
                if hasattr(union, 'this') and not isinstance(union.this, exp.Select):
                    errors.append("UNION debe contener solo SELECT")
                if hasattr(union, 'expression') and not isinstance(union.expression, exp.Select):
                    errors.append("UNION debe contener solo SELECT")

    except ParseError as e:
        errors.append(f"Error de sintaxis SQL: {str(e)}")

    except Exception as e:
        errors.append(f"Error validando SQL: {str(e)}")

    # Determinar nivel de riesgo
    if errors:
        risk_level = SQLRiskLevel.CRITICAL
        is_valid = False
    elif warnings:
        risk_level = SQLRiskLevel.MEDIUM
        is_valid = True
    elif len(tables_accessed) > 5:
        risk_level = SQLRiskLevel.LOW
        is_valid = True
    else:
        risk_level = SQLRiskLevel.SAFE
        is_valid = True

    return SQLValidationResult(
        is_valid=is_valid,
        risk_level=risk_level,
        tables_accessed=tables_accessed,
        operations_found=operations_found,
        errors=errors,
        warnings=warnings
    )


def sanitize_sql(sql: str) -> str:
    """
    Sanitiza una query SQL eliminando elementos peligrosos.
    """
    # Remover comentarios
    import re
    sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)

    # Remover punto y coma extra
    sql = sql.strip().rstrip(';') + ';'

    # Remover espacios múltiples
    sql = ' '.join(sql.split())

    return sql


def extract_tables_from_query(sql: str) -> List[str]:
    """
    Extrae las tablas mencionadas en una query SQL.
    """
    if not SQLGLOT_AVAILABLE:
        # Extracción básica con regex
        import re
        # Buscar patrones FROM/JOIN table_name
        pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        return list(set(matches))

    try:
        tables = []
        parsed = sqlglot.parse(sql, dialect="postgres")
        for statement in parsed:
            for table in statement.find_all(exp.Table):
                if table.name:
                    tables.append(table.name.lower())
        return list(set(tables))
    except:
        return []


def validate_and_sanitize(sql: str) -> Tuple[bool, str, SQLValidationResult]:
    """
    Valida y sanitiza una query SQL.

    Returns:
        Tuple[is_valid, sanitized_sql, validation_result]
    """
    sanitized = sanitize_sql(sql)
    result = validate_sql_ast(sanitized)
    return result.is_valid, sanitized, result


# Test básico
if __name__ == "__main__":
    test_queries = [
        "SELECT * FROM users",
        "SELECT id, name FROM products WHERE price > 100",
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE products",
        "SELECT * FROM users; DROP TABLE users;",
        "WITH sales AS (SELECT * FROM orders) SELECT * FROM sales",
        "SELECT * FROM users -- comment",
    ]

    for query in test_queries:
        result = validate_sql_ast(query)
        print(f"\nQuery: {query[:50]}...")
        print(f"  Valid: {result.is_valid}")
        print(f"  Risk: {result.risk_level}")
        print(f"  Tables: {result.tables_accessed}")
        print(f"  Errors: {result.errors}")
