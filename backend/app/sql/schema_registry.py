"""
Schema Registry - Database schema descriptions for SQL Specialist Agent

Provides detailed metadata about tables, columns, and relationships
for the LLM to understand the data structure.
"""
from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class ColumnInfo:
    """Column metadata"""
    name: str
    type: str
    description: str
    nullable: bool = True
    is_primary_key: bool = False
    foreign_key: str = None  # "table.column" format


@dataclass
class TableInfo:
    """Table metadata"""
    name: str
    description: str
    columns: List[ColumnInfo] = field(default_factory=list)
    sample_queries: List[str] = field(default_factory=list)


# =============================================================================
# DATABASE SCHEMA REGISTRY
# =============================================================================

SCHEMA_REGISTRY: Dict[str, TableInfo] = {

    # =========================================================================
    # MERCADOLIBRE TABLES
    # =========================================================================

    "ml_items": TableInfo(
        name="ml_items",
        description="Productos publicados en MercadoLibre. Contiene inventario, precios, y estadisticas de ventas.",
        columns=[
            ColumnInfo("id", "uuid", "ID interno (UUID)", is_primary_key=True),
            ColumnInfo("item_id", "text", "ID del item en MercadoLibre (ej: MLA123456)"),
            ColumnInfo("title", "text", "Titulo del producto"),
            ColumnInfo("sku", "text", "SKU/codigo interno del vendedor"),
            ColumnInfo("price", "numeric", "Precio actual del producto"),
            ColumnInfo("original_price", "numeric", "Precio original (sin descuento)"),
            ColumnInfo("currency_id", "text", "Moneda (ARS, USD)"),
            ColumnInfo("available_quantity", "integer", "Stock disponible para venta"),
            ColumnInfo("sold_quantity", "integer", "Unidades vendidas (historico)"),
            ColumnInfo("total_sold", "integer", "Total vendido (puede incluir variantes)"),
            ColumnInfo("status", "text", "Estado: active, paused, closed, under_review"),
            ColumnInfo("category_id", "text", "ID de categoria en ML"),
            ColumnInfo("listing_type", "text", "Tipo: gold_special, gold_pro, etc"),
            ColumnInfo("permalink", "text", "URL de la publicacion"),
            ColumnInfo("thumbnail", "text", "URL de imagen principal"),
            ColumnInfo("created_at", "timestamptz", "Fecha de creacion"),
            ColumnInfo("updated_at", "timestamptz", "Ultima actualizacion"),
        ],
        sample_queries=[
            "SELECT title, price, available_quantity FROM ml_items WHERE status = 'active'",
            "SELECT title, total_sold FROM ml_items ORDER BY total_sold DESC LIMIT 10",
        ]
    ),

    "ml_orders": TableInfo(
        name="ml_orders",
        description="Ordenes de compra de MercadoLibre. Cada fila es un item vendido (una orden puede tener multiples items).",
        columns=[
            ColumnInfo("id", "uuid", "ID interno (UUID)", is_primary_key=True),
            ColumnInfo("order_id", "bigint", "ID de la orden en MercadoLibre"),
            ColumnInfo("pack_id", "bigint", "ID del pack (si es compra multiple)"),
            ColumnInfo("buyer_id", "bigint", "ID del comprador en ML"),
            ColumnInfo("buyer_nickname", "text", "Nickname del comprador"),
            ColumnInfo("item_id", "text", "ID del producto vendido"),
            ColumnInfo("item_title", "text", "Titulo del producto al momento de la venta"),
            ColumnInfo("sku", "text", "SKU del producto"),
            ColumnInfo("quantity", "integer", "Cantidad comprada"),
            ColumnInfo("unit_price", "numeric", "Precio unitario"),
            ColumnInfo("total_amount", "numeric", "Monto total de la linea"),
            ColumnInfo("currency_id", "text", "Moneda"),
            ColumnInfo("status", "text", "Estado: paid, cancelled, pending"),
            ColumnInfo("shipping_id", "bigint", "ID del envio"),
            ColumnInfo("shipping_status", "text", "Estado del envio: delivered, shipped, pending"),
            ColumnInfo("shipping_type", "text", "Tipo: mercadoenvios, custom, etc"),
            ColumnInfo("date_created", "timestamptz", "Fecha de creacion de la orden"),
            ColumnInfo("date_closed", "timestamptz", "Fecha de cierre"),
            ColumnInfo("created_at", "timestamptz", "Fecha de registro en sistema"),
        ],
        sample_queries=[
            "SELECT SUM(total_amount) as total FROM ml_orders WHERE status = 'paid'",
            "SELECT DATE(date_created), SUM(total_amount) FROM ml_orders GROUP BY 1",
        ]
    ),

    # =========================================================================
    # CRM / CONVERSACIONES
    # =========================================================================

    "conversations": TableInfo(
        name="conversations",
        description="Conversaciones con compradores. Cada fila es un thread de chat con un buyer.",
        columns=[
            ColumnInfo("id", "uuid", "ID interno", is_primary_key=True),
            ColumnInfo("pack_id", "bigint", "ID del pack/orden relacionado"),
            ColumnInfo("buyer_id", "bigint", "ID del comprador"),
            ColumnInfo("buyer_nickname", "text", "Nickname del comprador"),
            ColumnInfo("status", "text", "Estado: active, closed, escalated"),
            ColumnInfo("case_type", "text", "Tipo: postventa, preventa, reclamo, consulta"),
            ColumnInfo("last_message_at", "timestamptz", "Fecha del ultimo mensaje"),
            ColumnInfo("message_count", "integer", "Cantidad de mensajes"),
            ColumnInfo("created_at", "timestamptz", "Inicio de la conversacion"),
        ],
        sample_queries=[
            "SELECT status, COUNT(*) FROM conversations GROUP BY status",
            "SELECT * FROM conversations WHERE status = 'active' ORDER BY last_message_at DESC",
        ]
    ),

    "escalations": TableInfo(
        name="escalations",
        description="Casos escalados a atencion humana. El agente AI determino que requiere intervencion.",
        columns=[
            ColumnInfo("id", "uuid", "ID interno", is_primary_key=True),
            ColumnInfo("conversation_id", "uuid", "ID de conversacion relacionada", foreign_key="conversations.id"),
            ColumnInfo("pack_id", "bigint", "ID del pack/orden"),
            ColumnInfo("buyer_id", "bigint", "ID del comprador"),
            ColumnInfo("buyer_nickname", "text", "Nickname del comprador"),
            ColumnInfo("buyer_message", "text", "Mensaje original del comprador"),
            ColumnInfo("reason", "text", "Motivo de la escalacion"),
            ColumnInfo("case_type", "text", "Tipo de caso: garantia, devolucion, factura, otro"),
            ColumnInfo("status", "text", "Estado: pending, in_progress, resolved"),
            ColumnInfo("priority", "text", "Prioridad: low, medium, high, urgent"),
            ColumnInfo("source", "text", "Origen: postventa, preventa"),
            ColumnInfo("assigned_to", "text", "Usuario asignado"),
            ColumnInfo("resolution", "text", "Descripcion de la resolucion"),
            ColumnInfo("created_at", "timestamptz", "Fecha de escalacion"),
            ColumnInfo("resolved_at", "timestamptz", "Fecha de resolucion"),
        ],
        sample_queries=[
            "SELECT case_type, COUNT(*) FROM escalations GROUP BY case_type",
            "SELECT * FROM escalations WHERE status = 'pending' ORDER BY priority DESC",
        ]
    ),

    "preventa_queries": TableInfo(
        name="preventa_queries",
        description="Preguntas de preventa de compradores potenciales sobre productos.",
        columns=[
            ColumnInfo("id", "uuid", "ID interno", is_primary_key=True),
            ColumnInfo("question_id", "bigint", "ID de la pregunta en ML"),
            ColumnInfo("item_id", "text", "ID del producto consultado"),
            ColumnInfo("buyer_id", "bigint", "ID del comprador"),
            ColumnInfo("buyer_nickname", "text", "Nickname del comprador"),
            ColumnInfo("question", "text", "Texto de la pregunta"),
            ColumnInfo("answer", "text", "Respuesta dada (si existe)"),
            ColumnInfo("status", "text", "Estado: pending, answered"),
            ColumnInfo("ai_suggested_answer", "text", "Respuesta sugerida por IA"),
            ColumnInfo("created_at", "timestamptz", "Fecha de la pregunta"),
            ColumnInfo("answered_at", "timestamptz", "Fecha de respuesta"),
        ],
        sample_queries=[
            "SELECT status, COUNT(*) FROM preventa_queries GROUP BY status",
            "SELECT * FROM preventa_queries WHERE status = 'pending'",
        ]
    ),

    # =========================================================================
    # VISTAS
    # =========================================================================

    "v_stock_dashboard": TableInfo(
        name="v_stock_dashboard",
        description="Vista calculada de stock con alertas. Incluye dias de cobertura y severidad.",
        columns=[
            ColumnInfo("item_id", "text", "ID del producto"),
            ColumnInfo("title", "text", "Titulo del producto"),
            ColumnInfo("sku", "text", "SKU"),
            ColumnInfo("available_quantity", "integer", "Stock actual"),
            ColumnInfo("daily_avg_sales", "numeric", "Promedio de ventas diarias"),
            ColumnInfo("days_cover", "integer", "Dias de cobertura de stock"),
            ColumnInfo("severity", "text", "Severidad: critical, warning, ok"),
            ColumnInfo("reorder_date", "date", "Fecha sugerida de reposicion"),
        ],
        sample_queries=[
            "SELECT * FROM v_stock_dashboard WHERE severity = 'critical'",
        ]
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_schema_context() -> str:
    """
    Generate a text description of the schema for LLM context.

    Returns:
        str: Formatted schema description
    """
    lines = ["# Database Schema\n"]

    for table_name, table in SCHEMA_REGISTRY.items():
        lines.append(f"## {table_name}")
        lines.append(f"{table.description}\n")
        lines.append("| Column | Type | Description |")
        lines.append("|--------|------|-------------|")

        for col in table.columns:
            pk = " (PK)" if col.is_primary_key else ""
            fk = f" -> {col.foreign_key}" if col.foreign_key else ""
            lines.append(f"| {col.name}{pk}{fk} | {col.type} | {col.description} |")

        lines.append("")

    return "\n".join(lines)


def get_table_info(table_name: str) -> TableInfo:
    """Get info for a specific table"""
    return SCHEMA_REGISTRY.get(table_name)


def get_available_tables() -> List[str]:
    """Get list of available table names"""
    return list(SCHEMA_REGISTRY.keys())


def get_column_names(table_name: str) -> List[str]:
    """Get column names for a table"""
    table = SCHEMA_REGISTRY.get(table_name)
    if not table:
        return []
    return [col.name for col in table.columns]


# Pre-generate schema context for embedding in prompts
SCHEMA_CONTEXT = get_schema_context()
