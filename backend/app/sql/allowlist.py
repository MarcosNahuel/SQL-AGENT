"""
SQL Allowlist - Queries seguras predefinidas

REGLAS DE SEGURIDAD:
- Solo SELECT
- Siempre con LIMIT
- Parametros validados
- No SQL dinamico
"""
from typing import Dict, Any, Optional
from datetime import date, timedelta


# Queries permitidas - El LLM solo puede elegir de esta lista
QUERY_ALLOWLIST: Dict[str, Dict[str, Any]] = {

    # ============== PRODUCTOS (ml_items) ==============

    "products_inventory": {
        "description": "Inventario de productos con stock y precios",
        "output_type": "table",
        "output_ref": "table.products_inventory",
        "template": """
            SELECT
                item_id as id,
                title,
                sku,
                price,
                available_quantity as stock,
                status,
                total_sold
            FROM ml_items
            ORDER BY available_quantity DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 50
        }
    },

    "products_low_stock": {
        "description": "Productos con stock bajo (menos de 10 unidades)",
        "output_type": "table",
        "output_ref": "table.products_low_stock",
        "template": """
            SELECT
                item_id as id,
                title,
                sku,
                price,
                available_quantity as stock,
                status
            FROM ml_items
            WHERE available_quantity < 10
              AND status = 'active'
            ORDER BY available_quantity ASC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    "top_products_by_sales": {
        "description": "Top productos por unidades vendidas",
        "output_type": "top_items",
        "output_ref": "top.products_by_sales",
        "template": """
            SELECT
                ROW_NUMBER() OVER (ORDER BY total_sold DESC NULLS LAST) as rank,
                item_id as id,
                title,
                total_sold as value,
                total_sold as units_sold
            FROM ml_items
            ORDER BY total_sold DESC NULLS LAST
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 10
        }
    },

    # ============== INTERACCIONES AI (agent_interactions) ==============

    "ai_interactions_summary": {
        "description": "Resumen de interacciones del agente AI (total, escaladas, por tipo)",
        "output_type": "kpi",
        "output_ref": "kpi.ai_interactions",
        "template": """
            SELECT
                COALESCE(conv.total_interactions, 0) as total_interactions,
                COALESCE(esc.escalated_count, 0) as escalated_count,
                COALESCE(ROUND(esc.escalated_count::numeric / NULLIF(conv.total_interactions, 0) * 100, 1), 0) as escalation_rate,
                COALESCE(conv.total_interactions, 0) - COALESCE(esc.escalated_count, 0) as auto_responded,
                COALESCE(
                    ROUND(
                        (COALESCE(conv.total_interactions, 0) - COALESCE(esc.escalated_count, 0))::numeric
                        / NULLIF(conv.total_interactions, 0) * 100,
                        1
                    ),
                    0
                ) as auto_response_rate,
                COALESCE(esc.pending, 0) as pendientes,
                COALESCE(esc.resolved, 0) as resueltos
            FROM
                (SELECT COUNT(*) as total_interactions FROM conversations) conv,
                (
                    SELECT
                        COUNT(*) as escalated_count,
                        COUNT(*) FILTER (WHERE status = 'resolved') as resolved,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending
                    FROM escalations
                ) esc
        """,
        "required_params": [],
        "default_params": {}
    },

    "recent_ai_interactions": {
        "description": "Ultimas interacciones del agente AI con compradores",
        "output_type": "table",
        "output_ref": "table.recent_ai_interactions",
        "template": """
            SELECT
                id,
                buyer_nickname,
                status,
                case_type,
                last_message_at
            FROM conversations
            ORDER BY last_message_at DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    "escalated_cases": {
        "description": "Casos escalados a humano con motivo",
        "output_type": "table",
        "output_ref": "table.escalated_cases",
        "template": """
            SELECT
                id,
                buyer_nickname,
                buyer_message,
                reason,
                case_type,
                status,
                priority,
                source,
                created_at
            FROM escalations
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    "interactions_by_case_type": {
        "description": "Interacciones agrupadas por tipo de caso",
        "output_type": "top_items",
        "output_ref": "top.interactions_by_case_type",
        "template": """
            SELECT
                ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) as rank,
                COALESCE(case_type, 'sin_tipo') as id,
                INITCAP(REPLACE(COALESCE(case_type, 'sin_tipo'), '_', ' ')) as title,
                COUNT(*) as value
            FROM escalations
            GROUP BY case_type
            ORDER BY value DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 10
        }
    },

    # ============== PREVENTA (preventa_queries) ==============

    "preventa_summary": {
        "description": "Resumen de consultas de preventa (total, respondidas, pendientes)",
        "output_type": "kpi",
        "output_ref": "kpi.preventa",
        "template": """
            SELECT
                COUNT(*) as total_queries,
                COUNT(*) FILTER (WHERE status = 'answered') as answered,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COALESCE(
                    ROUND(COUNT(*) FILTER (WHERE status = 'answered')::numeric / NULLIF(COUNT(*), 0) * 100, 1),
                    0
                ) as answer_rate
            FROM preventa_queries
        """,
        "required_params": [],
        "default_params": {}
    },

    "recent_preventa_queries": {
        "description": "Ultimas preguntas de preventa de compradores",
        "output_type": "table",
        "output_ref": "table.recent_preventa",
        "template": """
            SELECT
                id,
                buyer_nickname,
                question,
                status,
                created_at
            FROM preventa_queries
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    # ============== STOCK DASHBOARD (v_stock_dashboard) ==============

    "stock_alerts": {
        "description": "Alertas de stock critico y productos a reponer",
        "output_type": "table",
        "output_ref": "table.stock_alerts",
        "template": """
            SELECT
                item_id as id,
                title,
                available_quantity as stock,
                days_cover,
                severity,
                reorder_date
            FROM v_stock_dashboard
            WHERE severity IN ('critical', 'warning')
            ORDER BY severity DESC, days_cover ASC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    # ============== VENTAS (ml_orders) ==============

    # KPIs de ventas
    "kpi_sales_summary": {
        "description": "Resumen de KPIs de ventas (total, cantidad, promedio) - Solo ordenes PAID",
        "output_type": "kpi",
        "output_ref": "kpi",
        "template": """
            SELECT
                COALESCE(SUM(total_amount), 0) as total_sales,
                COUNT(*) as total_orders,
                COALESCE(AVG(total_amount), 0) as avg_order_value,
                COALESCE(SUM(quantity), 0) as total_units
            FROM ml_orders
            WHERE status = 'paid'
              AND date_created >= %(date_from)s
              AND date_created < %(date_to)s
        """,
        "required_params": ["date_from", "date_to"],
        "default_params": {
            "date_from": lambda: (date.today() - timedelta(days=395)).isoformat(),  # ~13 meses
            "date_to": lambda: (date.today() + timedelta(days=1)).isoformat()
        }
    },

    # Serie temporal de ventas por dia
    "ts_sales_by_day": {
        "description": "Ventas agrupadas por dia para grafico de linea",
        "output_type": "time_series",
        "output_ref": "ts.sales_by_day",
        "template": """
            SELECT
                DATE(date_created) as date,
                SUM(total_amount) as value,
                COUNT(*) as order_count
            FROM ml_orders
            WHERE date_created >= %(date_from)s
              AND date_created < %(date_to)s
            GROUP BY DATE(date_created)
            ORDER BY date ASC
            LIMIT %(limit)s
        """,
        "required_params": ["date_from", "date_to"],
        "default_params": {
            "date_from": lambda: (date.today() - timedelta(days=30)).isoformat(),
            "date_to": lambda: date.today().isoformat(),
            "limit": lambda: 31
        }
    },

    # Ventas agrupadas por mes
    "sales_by_month": {
        "description": "Ventas agrupadas por mes para analisis de estacionalidad",
        "output_type": "time_series",
        "output_ref": "ts.sales_by_month",
        "template": """
            SELECT
                TO_CHAR(date_created, 'YYYY-MM') as date,
                SUM(total_amount) as value,
                COUNT(*) as order_count
            FROM ml_orders
            WHERE status = 'paid'
              AND date_created >= %(date_from)s
              AND date_created < %(date_to)s
            GROUP BY TO_CHAR(date_created, 'YYYY-MM')
            ORDER BY date ASC
            LIMIT %(limit)s
        """,
        "required_params": ["date_from", "date_to"],
        "default_params": {
            "date_from": lambda: (date.today() - timedelta(days=395)).isoformat(),
            "date_to": lambda: (date.today() + timedelta(days=1)).isoformat(),
            "limit": lambda: 13
        }
    },

    # Top productos por revenue (filtrado por fecha)
    "top_products_by_revenue": {
        "description": "Top productos ordenados por ingresos en un periodo de tiempo",
        "output_type": "top_items",
        "output_ref": "top.products_by_revenue",
        "template": """
            SELECT
                ROW_NUMBER() OVER (ORDER BY SUM(o.total_amount) DESC) as rank,
                o.item_id as id,
                i.title,
                SUM(o.total_amount) as value,
                SUM(o.quantity) as units_sold
            FROM ml_orders o
            LEFT JOIN ml_items i ON o.item_id = i.item_id
            WHERE o.status = 'paid'
              AND o.date_created >= %(date_from)s
              AND o.date_created < %(date_to)s
            GROUP BY o.item_id, i.title
            ORDER BY value DESC
            LIMIT %(limit)s
        """,
        "required_params": ["date_from", "date_to"],
        "default_params": {
            "date_from": lambda: (date.today() - timedelta(days=30)).isoformat(),
            "date_to": lambda: (date.today() + timedelta(days=1)).isoformat(),
            "limit": lambda: 10
        }
    },

    # Ultimas ordenes (para tabla)
    "recent_orders": {
        "description": "Ultimas ordenes para mostrar en tabla",
        "output_type": "table",
        "output_ref": "table.recent_orders",
        "template": """
            SELECT
                order_id as id,
                buyer_nickname,
                item_title,
                total_amount,
                quantity,
                status,
                shipping_status,
                date_created
            FROM ml_orders
            ORDER BY date_created DESC
            LIMIT %(limit)s
        """,
        "required_params": [],
        "default_params": {
            "limit": lambda: 20
        }
    },

    # Ventas por canal/fuente
    "sales_by_channel": {
        "description": "Ventas agrupadas por canal (MercadoLibre, etc)",
        "output_type": "top_items",
        "output_ref": "top.sales_by_channel",
        "template": """
            SELECT
                ROW_NUMBER() OVER (ORDER BY SUM(total_amount) DESC) as rank,
                COALESCE(shipping_type, 'direct') as id,
                COALESCE(shipping_type, 'direct') as title,
                SUM(total_amount) as value,
                COUNT(*) as order_count
            FROM ml_orders
            WHERE date_created >= %(date_from)s
              AND date_created < %(date_to)s
            GROUP BY shipping_type
            ORDER BY value DESC
            LIMIT %(limit)s
        """,
        "required_params": ["date_from", "date_to"],
        "default_params": {
            "date_from": lambda: (date.today() - timedelta(days=30)).isoformat(),
            "date_to": lambda: date.today().isoformat(),
            "limit": lambda: 10
        }
    }
}


def get_query_template(query_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene el template de una query del allowlist"""
    return QUERY_ALLOWLIST.get(query_id)


def validate_query_id(query_id: str) -> bool:
    """Valida que un query_id exista en el allowlist"""
    return query_id in QUERY_ALLOWLIST


def get_available_queries() -> Dict[str, str]:
    """Retorna dict de query_id -> descripcion para el LLM"""
    return {
        qid: q["description"]
        for qid, q in QUERY_ALLOWLIST.items()
    }


def build_params(query_id: str, user_params: Dict[str, Any]) -> Dict[str, Any]:
    """Construye los parametros finales, aplicando defaults donde falten"""
    query_config = QUERY_ALLOWLIST.get(query_id)
    if not query_config:
        raise ValueError(f"Query {query_id} no existe en allowlist")

    # Comenzar con defaults
    params = {}
    for key, default_fn in query_config.get("default_params", {}).items():
        params[key] = default_fn() if callable(default_fn) else default_fn

    # Sobrescribir con params del usuario
    for key, value in user_params.items():
        if value is not None:
            params[key] = value

    # Validar required
    for req in query_config.get("required_params", []):
        if req not in params:
            raise ValueError(f"Parametro requerido faltante: {req}")

    return params
