"""
Schema Documentation - Documentacion del Modelo de Datos

Este modulo contiene la documentacion completa del esquema de base de datos,
contexto de negocio y descripciones de cada tabla y campo.

El agente SQL debe usar esta documentacion para:
1. Entender el contexto de negocio de cada tabla
2. Conocer el significado de cada campo
3. Construir queries relevantes para las preguntas del usuario
"""

# ============================================================================
# CONTEXTO DE NEGOCIO
# ============================================================================

BUSINESS_CONTEXT = """
## Contexto del Negocio

Este sistema es para una **tienda de e-commerce** que vende principalmente en **MercadoLibre Argentina**.

### Productos Principales:
- Accesorios automotrices (scanners OBD2, parasoles, fundas)
- Productos creativos (lapices 3D, marcadores, filamentos)
- Herramientas y accesorios varios

### Canales de Venta:
- MercadoLibre (principal)
- Tienda propia (secundario)

### Metricas Clave del Negocio:
- **Ventas**: Monto total facturado (solo ordenes con status='paid')
- **Ticket Promedio**: Monto promedio por orden
- **Unidades Vendidas**: Cantidad de productos vendidos
- **Tasa de Escalado**: % de conversaciones que requieren atencion humana
- **Stock Critico**: Productos con menos de 10 unidades

### Flujo de Ordenes:
1. Cliente compra en MercadoLibre
2. Orden llega via webhook (status inicial varia)
3. Se procesa pago -> status='paid'
4. Se envia -> shipping_status='shipped'
5. Se entrega -> shipping_status='delivered'

### Tipos de Envio (shipping_type):
- fulfillment: Mercado Envios Full (stock en deposito ML)
- cross_docking: Mercado Envios (seller envia a ML)
- drop_off: Punto de despacho
- self_service: Envio por cuenta propia
"""

# ============================================================================
# DOCUMENTACION DE TABLAS
# ============================================================================

SCHEMA_DOCUMENTATION = {
    # ========== VENTAS Y ORDENES ==========
    "ml_orders": {
        "description": "Ordenes de venta de MercadoLibre. Tabla principal para metricas de ventas.",
        "business_context": """
            Esta tabla contiene TODAS las ordenes sincronizadas desde MercadoLibre.

            IMPORTANTE para queries de ventas:
            - Filtrar por status='paid' para ventas efectivas
            - El campo total_amount es el monto final pagado por el cliente
            - date_created es la fecha de la orden (usar para filtros temporales)
            - Una orden puede tener multiples unidades (campo quantity)
        """,
        "fields": {
            "id": "UUID interno (PK)",
            "order_id": "ID unico de MercadoLibre (bigint). Usar para referencias externas.",
            "pack_id": "ID del pack si la orden es parte de un carrito multiple",
            "buyer_id": "ID del comprador en MercadoLibre (FK a buyers)",
            "buyer_nickname": "Nickname del comprador (ej: COMPRADOR123)",
            "item_id": "ID del producto vendido (FK a ml_items)",
            "item_title": "Titulo del producto al momento de la venta",
            "item_sku": "SKU interno del producto",
            "quantity": "Cantidad de unidades vendidas en esta orden",
            "unit_price": "Precio unitario del producto",
            "total_amount": "Monto TOTAL pagado (precio * cantidad + envio). USAR PARA REPORTES DE VENTAS.",
            "shipping_id": "ID del envio en MercadoLibre",
            "shipping_status": "Estado del envio: pending, ready_to_ship, shipped, delivered",
            "shipping_type": "Tipo de envio: fulfillment, cross_docking, drop_off, self_service",
            "date_shipped": "Fecha de despacho",
            "date_delivered": "Fecha de entrega al cliente",
            "status": "Estado de la orden: paid, cancelled, refunded. FILTRAR POR 'paid' PARA VENTAS.",
            "date_created": "Fecha de creacion de la orden. USAR PARA FILTROS DE FECHA.",
            "date_closed": "Fecha de cierre/finalizacion"
        },
        "common_queries": [
            "Ventas totales: SUM(total_amount) WHERE status='paid'",
            "Cantidad de ordenes: COUNT(*) WHERE status='paid'",
            "Ticket promedio: AVG(total_amount) WHERE status='paid'",
            "Ventas por dia: GROUP BY DATE(date_created)"
        ]
    },

    "ml_items": {
        "description": "Catalogo de productos publicados en MercadoLibre.",
        "business_context": """
            Contiene todos los productos activos y pausados del seller.

            IMPORTANTE:
            - total_sold es el acumulado historico de unidades vendidas
            - available_quantity es el stock actual disponible
            - price es el precio actual (puede cambiar)
            - Para calcular revenue historico: price * total_sold
        """,
        "fields": {
            "item_id": "ID unico del producto en MercadoLibre (ej: MLA1234567890)",
            "title": "Titulo del producto (max 60 chars para reportes)",
            "permalink": "URL de la publicacion en MercadoLibre",
            "thumbnail": "URL de la imagen miniatura",
            "price": "Precio actual de venta",
            "available_quantity": "Stock disponible. CRITICO si < 10.",
            "status": "Estado: active, paused, closed",
            "sku": "Codigo interno del producto",
            "category_id": "Categoria de MercadoLibre",
            "seller_id": "ID del vendedor",
            "total_sold": "Total historico de unidades vendidas",
            "last_synced": "Ultima sincronizacion con MercadoLibre"
        },
        "common_queries": [
            "Top productos por revenue: ORDER BY (price * total_sold) DESC",
            "Stock bajo: WHERE available_quantity < 10 AND status='active'",
            "Productos activos: WHERE status='active'"
        ]
    },

    # ========== COMPRADORES ==========
    "buyers": {
        "description": "Informacion de compradores de MercadoLibre.",
        "business_context": "Datos de clientes para CRM y facturacion.",
        "fields": {
            "id": "ID del comprador en MercadoLibre (PK)",
            "nickname": "Nickname publico del comprador",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Email (puede estar enmascarado por ML)",
            "doc_type": "Tipo de documento (DNI, CUIT, etc)",
            "doc_number": "Numero de documento",
            "can_receive_factura_a": "Si puede recibir factura A (monotributista/RI)",
            "city": "Ciudad",
            "state": "Provincia",
            "country": "Pais (default AR)"
        }
    },

    # ========== AGENTE AI - INTERACCIONES ==========
    "agent_interactions": {
        "description": "Registro de TODAS las interacciones del agente AI con compradores.",
        "business_context": """
            Cada vez que el agente AI procesa un mensaje de un comprador,
            se guarda un registro aqui.

            IMPORTANTE:
            - was_escalated=true indica que el agente no pudo resolver solo
            - case_type clasifica el tipo de consulta
            - source indica si es 'preventa' o 'postventa'
        """,
        "fields": {
            "id": "UUID de la interaccion",
            "buyer_id": "ID del comprador",
            "buyer_nickname": "Nickname del comprador",
            "message_original": "Mensaje original del comprador",
            "ai_response": "Respuesta generada por el agente AI",
            "case_type": "Tipo de caso: envio, producto, devolucion, garantia, etc",
            "was_escalated": "True si se escalo a humano",
            "escalation_reason": "Motivo de escalado",
            "source": "Origen: 'preventa' o 'postventa'",
            "was_sent_to_ml": "Si la respuesta se envio a MercadoLibre",
            "product_id": "ID del producto relacionado",
            "product_title": "Titulo del producto",
            "envio_status": "Estado del envio relacionado",
            "created_at": "Fecha de la interaccion"
        },
        "common_queries": [
            "Total interacciones: COUNT(*)",
            "Tasa de escalado: COUNT(*) FILTER (WHERE was_escalated) / COUNT(*)",
            "Por tipo de caso: GROUP BY case_type"
        ]
    },

    "escalations": {
        "description": "Casos escalados a atencion humana.",
        "business_context": """
            Cuando el agente AI no puede resolver un caso, lo escala aqui.
            El equipo humano debe atender estos casos priorizando por:
            1. priority (1=urgente, 5=normal, 10=bajo)
            2. created_at (mas antiguos primero)
        """,
        "fields": {
            "id": "UUID del escalado",
            "buyer_id": "ID del comprador",
            "buyer_nickname": "Nickname",
            "buyer_name": "Nombre completo",
            "pack_id": "ID del pack/carrito",
            "order_id": "ID de la orden relacionada",
            "message_original": "Mensaje original del comprador",
            "reason": "Motivo del escalado (ej: 'cliente enojado', 'caso complejo')",
            "case_type": "Tipo: envio, devolucion, garantia, reclamo, etc",
            "source": "Origen: preventa o postventa",
            "status": "Estado: pending, in_progress, resolved",
            "priority": "Prioridad 1-10 (1=mas urgente)",
            "assigned_to": "Usuario asignado",
            "human_response": "Respuesta del humano",
            "resolved_at": "Fecha de resolucion",
            "resolution_notes": "Notas de la resolucion"
        },
        "common_queries": [
            "Pendientes: WHERE status='pending' ORDER BY priority, created_at",
            "Resueltos hoy: WHERE resolved_at >= CURRENT_DATE",
            "Por tipo: GROUP BY case_type"
        ]
    },

    "conversations": {
        "description": "Conversaciones/hilos de chat con compradores.",
        "business_context": """
            Agrupa multiples mensajes en una conversacion.
            Una conversacion puede tener muchos mensajes.
        """,
        "fields": {
            "id": "UUID de la conversacion",
            "buyer_id": "ID del comprador",
            "pack_id": "ID del pack/carrito",
            "status": "Estado: active, resolved, escalated",
            "case_type": "Tipo de caso principal",
            "message_count": "Cantidad de mensajes",
            "first_message_at": "Primer mensaje",
            "last_message_at": "Ultimo mensaje",
            "resolved_at": "Fecha de resolucion",
            "resolution_time_seconds": "Tiempo de resolucion en segundos"
        }
    },

    "messages": {
        "description": "Mensajes individuales dentro de conversaciones.",
        "fields": {
            "id": "UUID del mensaje",
            "conversation_id": "FK a conversations",
            "sender_type": "Quien envio: buyer, agent, human",
            "content": "Contenido del mensaje",
            "created_at": "Fecha del mensaje"
        }
    },

    # ========== PREVENTA ==========
    "preventa_queries": {
        "description": "Preguntas de preventa de MercadoLibre.",
        "business_context": """
            Preguntas que hacen los usuarios ANTES de comprar.
            El agente AI puede responder automaticamente o escalar.
        """,
        "fields": {
            "id": "UUID",
            "question_id": "ID de la pregunta en MercadoLibre",
            "item_id": "Producto sobre el que preguntan",
            "buyer_id": "ID del comprador",
            "question_text": "Pregunta del usuario",
            "ai_response": "Respuesta del agente",
            "status": "Estado: pending, answered, escalated",
            "was_answered": "Si ya se respondio",
            "product_title": "Titulo del producto",
            "question_date": "Fecha de la pregunta",
            "answered_at": "Fecha de respuesta"
        }
    },

    # ========== METRICAS DE STOCK ==========
    "ml_item_metrics": {
        "description": "Metricas calculadas de productos para alertas de stock.",
        "fields": {
            "item_id": "FK a ml_items",
            "days_of_stock": "Dias estimados de stock restante",
            "avg_daily_sales": "Promedio de ventas diarias",
            "velocity": "Velocidad de venta: fast, medium, slow",
            "reorder_point": "Punto de reorden sugerido",
            "severity": "Severidad de alerta: critical, warning, ok"
        }
    }
}

# ============================================================================
# FUNCIONES DE AYUDA
# ============================================================================

def get_schema_context() -> str:
    """
    Genera el contexto de esquema para el system prompt del agente.
    """
    context = [BUSINESS_CONTEXT, "\n## Tablas Principales\n"]

    for table_name, table_info in SCHEMA_DOCUMENTATION.items():
        context.append(f"\n### {table_name}")
        context.append(f"**{table_info['description']}**\n")

        if "business_context" in table_info:
            context.append(table_info["business_context"])

        context.append("\nCampos clave:")
        for field, desc in list(table_info["fields"].items())[:8]:  # Top 8 campos
            context.append(f"- `{field}`: {desc}")

        if "common_queries" in table_info:
            context.append("\nPatrones de query:")
            for q in table_info["common_queries"][:3]:
                context.append(f"- {q}")

    return "\n".join(context)


def get_table_documentation(table_name: str) -> dict:
    """
    Obtiene la documentacion de una tabla especifica.
    """
    return SCHEMA_DOCUMENTATION.get(table_name, {})


def get_all_tables() -> list:
    """
    Lista todas las tablas documentadas.
    """
    return list(SCHEMA_DOCUMENTATION.keys())


# Exportar contexto pre-generado para uso rapido
SCHEMA_CONTEXT = get_schema_context()
