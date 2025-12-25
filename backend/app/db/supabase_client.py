"""
Supabase REST API client para ejecutar queries seguras

Usa la API REST de Supabase (PostgREST) en lugar de conexion directa Postgres.
Esto permite conectarse a Supabase EasyPanel sin exponer el puerto 5432.
"""
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
import httpx
from functools import lru_cache

from ..sql.allowlist import get_query_template, validate_query_id, build_params
from ..schemas.payload import DatasetMeta


# Cache simple con TTL
class TTLCache:
    """Cache en memoria con TTL"""
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        self._cache[key] = (value, time.time())

    def clear(self):
        self._cache.clear()


# Cache global para queries pesadas (5 minutos TTL)
_query_cache = TTLCache(ttl_seconds=300)


class SupabaseRESTClient:
    """Cliente REST para Supabase/PostgREST"""

    def __init__(self):
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.getenv("SUPABASE_ANON_KEY", "")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY", self.api_key)

        # Headers por defecto - usar service_key para bypass RLS
        self.headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        # Cliente HTTP con timeout
        self.client = httpx.Client(timeout=30.0)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> List[Dict]:
        """Ejecuta una request a la API REST"""
        url = f"{self.base_url}/rest/v1/{endpoint}"

        response = self.client.request(
            method=method,
            url=url,
            headers=self.headers,
            params=params,
            json=json_data
        )

        if response.status_code >= 400:
            raise Exception(f"Supabase API error: {response.status_code} - {response.text}")

        return response.json() if response.text else []

    def _get_table(
        self,
        table: str,
        select: str = "*",
        filters: Optional[Dict] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """GET de una tabla con filtros opcionales"""
        params = {"select": select}

        if filters:
            for key, value in filters.items():
                params[key] = value

        if order:
            params["order"] = order

        if limit:
            params["limit"] = str(limit)

        return self._request("GET", table, params=params)

    def _get_table_paginated(
        self,
        table: str,
        select: str = "*",
        filters: Optional[Dict] = None,
        max_records: int = 100000
    ) -> tuple[List[Dict], int]:
        """
        Obtiene todos los registros de una tabla usando paginación.
        Retorna (registros, total_count)
        """
        all_records = []
        page_size = 10000
        offset = 0
        total_count = 0

        while True:
            # Construir parámetros
            params = {"select": select}
            if filters:
                for key, value in filters.items():
                    params[key] = value

            # Headers con count
            headers = {**self.headers, "Prefer": "count=exact"}
            headers["Range"] = f"{offset}-{offset + page_size - 1}"

            url = f"{self.base_url}/rest/v1/{table}"
            response = self.client.get(url, headers=headers, params=params)

            if response.status_code >= 400:
                raise Exception(f"Supabase API error: {response.status_code} - {response.text}")

            # Obtener total del header Content-Range
            content_range = response.headers.get("content-range", "")
            if "/" in content_range:
                total_str = content_range.split("/")[1]
                if total_str != "*":
                    total_count = int(total_str)

            records = response.json() if response.text else []
            all_records.extend(records)

            # Si no hay más registros o alcanzamos el máximo, salir
            if len(records) < page_size or len(all_records) >= max_records:
                break

            offset += page_size

        return all_records, total_count

    def execute_safe_query(
        self,
        query_id: str,
        params: Optional[Dict[str, Any]] = None
    ) -> tuple[List[Dict[str, Any]], DatasetMeta]:
        """
        Ejecuta una query del allowlist usando la API REST
        """
        # Validar que la query existe
        if not validate_query_id(query_id):
            raise ValueError(f"Query '{query_id}' no esta en el allowlist")

        query_config = get_query_template(query_id)
        if not query_config:
            raise ValueError(f"Query '{query_id}' no encontrada")

        # Construir parametros
        safe_params = build_params(query_id, params or {})

        start_time = time.time()

        # Ejecutar segun el tipo de query
        if query_id == "kpi_sales_summary":
            rows = self._execute_kpi_sales_summary(safe_params)
        elif query_id == "ts_sales_by_day":
            rows = self._execute_ts_sales_by_day(safe_params)
        elif query_id == "sales_by_month":
            rows = self._execute_sales_by_month(safe_params)
        elif query_id == "top_products_by_revenue":
            rows = self._execute_top_products(safe_params)
        elif query_id == "recent_orders":
            rows = self._execute_recent_orders(safe_params)
        elif query_id == "sales_by_channel":
            rows = self._execute_sales_by_channel(safe_params)
        elif query_id == "products_inventory":
            rows = self._execute_products_inventory(safe_params)
        elif query_id == "products_low_stock":
            rows = self._execute_products_low_stock(safe_params)
        elif query_id == "top_products_by_sales":
            rows = self._execute_top_products_by_sales(safe_params)
        elif query_id == "ai_interactions_summary":
            rows = self._execute_ai_interactions_summary(safe_params)
        elif query_id == "recent_ai_interactions":
            rows = self._execute_recent_ai_interactions(safe_params)
        elif query_id == "escalated_cases":
            rows = self._execute_escalated_cases(safe_params)
        elif query_id == "interactions_by_case_type":
            rows = self._execute_interactions_by_case_type(safe_params)
        elif query_id == "preventa_summary":
            rows = self._execute_preventa_summary(safe_params)
        elif query_id == "recent_preventa_queries":
            rows = self._execute_recent_preventa_queries(safe_params)
        elif query_id == "stock_alerts":
            rows = self._execute_stock_alerts(safe_params)
        elif query_id == "kpi_inventory_summary":
            rows = self._execute_kpi_inventory_summary(safe_params)
        else:
            raise ValueError(f"Query '{query_id}' no implementada para REST API")

        execution_time = (time.time() - start_time) * 1000

        meta = DatasetMeta(
            query_id=query_id,
            row_count=len(rows),
            execution_time_ms=round(execution_time, 2),
            executed_at=datetime.utcnow()
        )

        return rows, meta

    def _execute_kpi_sales_summary(self, params: Dict) -> List[Dict]:
        """KPIs de ventas - agregaciones sobre ml_orders (solo PAID)"""
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        # Usar cache para evitar queries de 50+ segundos
        cache_key = f"kpi_sales_paid_{date_from}_{date_to}"
        cached = _query_cache.get(cache_key)
        if cached:
            return cached

        # Obtener TODAS las ordenes paginadas
        orders, total_count = self._get_table_paginated(
            "ml_orders",
            select="total_amount,quantity,status,date_created",
            max_records=100000
        )

        # Filtrar por status='paid' y fecha
        filtered_orders = []
        for o in orders:
            # Solo ordenes PAID (excluir canceladas)
            if o.get("status") != "paid":
                continue
            created = (o.get("date_created") or "")[:10]
            if date_from and created < date_from:
                continue
            if date_to and created >= date_to:
                continue
            filtered_orders.append(o)

        # Calcular KPIs
        total_sales = sum(float(o.get("total_amount", 0) or 0) for o in filtered_orders)
        total_orders = len(filtered_orders)
        total_units = sum(int(o.get("quantity", 1) or 1) for o in filtered_orders)
        avg_order_value = total_sales / total_orders if total_orders > 0 else 0

        result = [{
            "total_sales": round(total_sales, 2),
            "total_orders": total_orders,
            "avg_order_value": round(avg_order_value, 2),
            "total_units": total_units,
            "data_coverage": f"{total_orders}/{total_count} (paid only)"
        }]

        _query_cache.set(cache_key, result)
        return result

    def _execute_ts_sales_by_day(self, params: Dict) -> List[Dict]:
        """Ventas por dia - time series"""
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = params.get("limit", 31)

        cache_key = f"ts_sales_{date_from}_{date_to}_{limit}"
        cached = _query_cache.get(cache_key)
        if cached:
            return cached

        orders, _ = self._get_table_paginated(
            "ml_orders",
            select="date_created,total_amount",
            max_records=100000
        )

        from collections import defaultdict
        daily_sales = defaultdict(lambda: {"value": 0, "order_count": 0})

        for order in orders:
            created = order.get("date_created")
            if not created:
                continue

            order_date = created[:10] if isinstance(created, str) else str(created)[:10]

            if date_from and order_date < date_from:
                continue
            if date_to and order_date >= date_to:
                continue

            amount = float(order.get("total_amount", 0) or 0)
            daily_sales[order_date]["value"] += amount
            daily_sales[order_date]["order_count"] += 1

        result = [
            {"date": d, "value": round(data["value"], 2), "order_count": data["order_count"]}
            for d, data in sorted(daily_sales.items())
        ]

        final_result = result[:limit]
        _query_cache.set(cache_key, final_result)
        return final_result

    def _execute_sales_by_month(self, params: Dict) -> List[Dict]:
        """Ventas por mes - time series mensual"""
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = params.get("limit", 13)

        cache_key = f"sales_month_{date_from}_{date_to}_{limit}"
        cached = _query_cache.get(cache_key)
        if cached:
            return cached

        orders, _ = self._get_table_paginated(
            "ml_orders",
            select="date_created,total_amount,status",
            max_records=100000
        )

        from collections import defaultdict
        monthly_sales = defaultdict(lambda: {"value": 0, "order_count": 0})

        for order in orders:
            # Solo ordenes pagadas
            if order.get("status") != "paid":
                continue

            created = order.get("date_created")
            if not created:
                continue

            order_date = created[:10] if isinstance(created, str) else str(created)[:10]
            order_month = order_date[:7]  # YYYY-MM

            if date_from and order_date < date_from:
                continue
            if date_to and order_date >= date_to:
                continue

            amount = float(order.get("total_amount", 0) or 0)
            monthly_sales[order_month]["value"] += amount
            monthly_sales[order_month]["order_count"] += 1

        result = [
            {"date": m, "value": round(data["value"], 2), "order_count": data["order_count"]}
            for m, data in sorted(monthly_sales.items())
        ]

        final_result = result[:limit]
        _query_cache.set(cache_key, final_result)
        return final_result

    def _execute_top_products(self, params: Dict) -> List[Dict]:
        """Top productos por revenue - FILTRADO POR FECHA"""
        import sys
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = params.get("limit", 10)

        print(f"[_execute_top_products] date_from={date_from}, date_to={date_to}, limit={limit}", file=sys.stderr, flush=True)

        # Cache key incluye fechas
        cache_key = f"top_products_{date_from}_{date_to}_{limit}"
        cached = _query_cache.get(cache_key)
        if cached:
            print(f"[_execute_top_products] Cache HIT: {len(cached)} items", file=sys.stderr, flush=True)
            return cached

        # Obtener ordenes filtradas por fecha (solo PAID)
        orders, _ = self._get_table_paginated(
            "ml_orders",
            select="item_id,item_title,total_amount,quantity,status,date_created",
            max_records=100000
        )

        # Obtener info de items para el titulo
        items = self._get_table(
            "ml_items",
            select="item_id,title",
            limit=10000
        )
        items_map = {item.get("item_id"): item.get("title") for item in items}

        # Agregar por item_id, filtrando por fecha y status
        from collections import defaultdict
        product_stats = defaultdict(lambda: {"revenue": 0, "units": 0, "title": ""})

        for order in orders:
            # Solo ordenes PAID
            if order.get("status") != "paid":
                continue

            # Filtrar por fecha
            created = (order.get("date_created") or "")[:10]
            if date_from and created < date_from:
                continue
            if date_to and created >= date_to:
                continue

            item_id = order.get("item_id")
            if not item_id:
                continue

            amount = float(order.get("total_amount", 0) or 0)
            qty = int(order.get("quantity", 1) or 1)

            product_stats[item_id]["revenue"] += amount
            product_stats[item_id]["units"] += qty
            # Usar titulo del item o de la orden
            if not product_stats[item_id]["title"]:
                product_stats[item_id]["title"] = items_map.get(item_id) or order.get("item_title") or "Sin titulo"

        # Ordenar por revenue y tomar top N
        sorted_products = sorted(
            product_stats.items(),
            key=lambda x: x[1]["revenue"],
            reverse=True
        )[:limit]

        result = [
            {
                "rank": i,
                "id": item_id,
                "title": (data["title"] or "Sin titulo")[:60],
                "value": round(data["revenue"], 2),
                "units_sold": data["units"]
            }
            for i, (item_id, data) in enumerate(sorted_products, 1)
        ]

        print(f"[_execute_top_products] Found {len(result)} products in date range", file=sys.stderr, flush=True)
        if result:
            print(f"[_execute_top_products] Top 3: {result[:3]}", file=sys.stderr, flush=True)

        _query_cache.set(cache_key, result)
        return result

    def _execute_recent_orders(self, params: Dict) -> List[Dict]:
        """Ultimas ordenes"""
        limit = params.get("limit", 20)

        orders = self._get_table(
            "ml_orders",
            select="order_id,buyer_nickname,item_title,total_amount,quantity,status,shipping_status,date_created",
            order="date_created.desc",
            limit=limit
        )

        return [
            {
                "id": o.get("order_id"),
                "buyer": o.get("buyer_nickname"),
                "producto": (o.get("item_title") or "")[:40],
                "monto": float(o.get("total_amount", 0) or 0),
                "cantidad": int(o.get("quantity", 1) or 1),
                "estado": o.get("status"),
                "envio": o.get("shipping_status"),
                "fecha": (o.get("date_created") or "")[:10]
            }
            for o in orders
        ]

    def _execute_sales_by_channel(self, params: Dict) -> List[Dict]:
        """Ventas por canal"""
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = params.get("limit", 10)

        cache_key = f"sales_channel_{date_from}_{date_to}_{limit}"
        cached = _query_cache.get(cache_key)
        if cached:
            return cached

        orders, _ = self._get_table_paginated(
            "ml_orders",
            select="shipping_type,total_amount,date_created",
            max_records=100000
        )

        from collections import defaultdict
        channels = defaultdict(lambda: {"value": 0, "order_count": 0})

        for order in orders:
            created = order.get("date_created", "")[:10] if order.get("date_created") else ""

            if date_from and created < date_from:
                continue
            if date_to and created >= date_to:
                continue

            channel = order.get("shipping_type") or "direct"
            amount = float(order.get("total_amount", 0) or 0)

            channels[channel]["value"] += amount
            channels[channel]["order_count"] += 1

        sorted_channels = sorted(
            channels.items(),
            key=lambda x: x[1]["value"],
            reverse=True
        )[:limit]

        result = [
            {
                "rank": i,
                "id": channel,
                "title": self._format_channel_name(channel),
                "value": round(data["value"], 2),
                "order_count": data["order_count"]
            }
            for i, (channel, data) in enumerate(sorted_channels, 1)
        ]

        _query_cache.set(cache_key, result)
        return result

    def _format_channel_name(self, channel: str) -> str:
        """Formatea nombre de canal para display"""
        names = {
            "fulfillment": "Mercado Envios Full",
            "cross_docking": "Mercado Envios",
            "drop_off": "Punto de despacho",
            "self_service": "Envio por cuenta propia",
            "direct": "Venta directa",
            "xd_drop_off": "Cross Docking",
        }
        return names.get(channel, channel.replace("_", " ").title())

    # ============== PRODUCTOS ==============

    def _execute_products_inventory(self, params: Dict) -> List[Dict]:
        """Inventario de productos"""
        limit = params.get("limit", 50)

        items = self._get_table(
            "ml_items",
            select="item_id,title,sku,price,available_quantity,status,total_sold",
            order="available_quantity.desc",
            limit=limit
        )

        return [
            {
                "id": item.get("item_id"),
                "title": item.get("title", "")[:60],
                "sku": item.get("sku"),
                "price": float(item.get("price", 0) or 0),
                "stock": int(item.get("available_quantity", 0) or 0),
                "status": item.get("status"),
                "sold": int(item.get("total_sold", 0) or 0)
            }
            for item in items
        ]

    def _execute_products_low_stock(self, params: Dict) -> List[Dict]:
        """Productos con stock bajo"""
        limit = params.get("limit", 20)

        items = self._get_table(
            "ml_items",
            select="item_id,title,sku,price,available_quantity,status",
            filters={"available_quantity": "lt.10", "status": "eq.active"},
            order="available_quantity.asc",
            limit=limit
        )

        return [
            {
                "id": item.get("item_id"),
                "title": item.get("title", "")[:50],
                "sku": item.get("sku"),
                "stock": int(item.get("available_quantity", 0) or 0),
                "status": "CRITICO" if int(item.get("available_quantity", 0) or 0) < 3 else "BAJO"
            }
            for item in items
        ]

    def _execute_top_products_by_sales(self, params: Dict) -> List[Dict]:
        """Top productos por ventas"""
        limit = params.get("limit", 10)

        items = self._get_table(
            "ml_items",
            select="item_id,title,price,total_sold",
            order="total_sold.desc.nullslast",
            limit=limit
        )

        return [
            {
                "rank": i,
                "id": item.get("item_id"),
                "title": item.get("title", "")[:50],
                "value": round(float(item.get("price", 0) or 0) * int(item.get("total_sold", 0) or 0), 2),
                "units_sold": int(item.get("total_sold", 0) or 0)
            }
            for i, item in enumerate(items, 1)
        ]

    # ============== INTERACCIONES AI ==============

    def _execute_ai_interactions_summary(self, params: Dict) -> List[Dict]:
        """KPIs de interacciones"""
        conversations = self._get_table(
            "conversations",
            select="id,status,case_type",
            limit=1000
        )

        escalations = self._get_table(
            "escalations",
            select="id,status,channel",
            limit=1000
        )

        total_conv = len(conversations)
        escalated = len(escalations)
        resolved = sum(1 for e in escalations if e.get("status") == "resolved")
        pending = sum(1 for e in escalations if e.get("status") == "pending")

        return [{
            "total_interactions": total_conv,
            "escalated_count": escalated,
            "escalation_rate": round((escalated / total_conv * 100) if total_conv > 0 else 0, 1),
            "auto_responded": total_conv - escalated,
            "auto_response_rate": round(((total_conv - escalated) / total_conv * 100) if total_conv > 0 else 0, 1),
            "pendientes": pending,
            "resueltos": resolved
        }]

    def _execute_recent_ai_interactions(self, params: Dict) -> List[Dict]:
        """Ultimas conversaciones"""
        limit = params.get("limit", 20)

        conversations = self._get_table(
            "conversations",
            select="id,buyer_nickname,status,case_type,updated_at",
            order="updated_at.desc",
            limit=limit
        )

        return [
            {
                "id": str(c.get("id"))[:8],
                "buyer": c.get("buyer_nickname"),
                "status": c.get("status"),
                "case_type": c.get("case_type"),
                "fecha": (c.get("updated_at") or "")[:16]
            }
            for c in conversations
        ]

    def _execute_escalated_cases(self, params: Dict) -> List[Dict]:
        """Casos escalados"""
        limit = params.get("limit", 20)

        escalations = self._get_table(
            "escalations",
            select="id,buyer_name,original_message,reason,case_type,status,priority,channel,created_at",
            order="created_at.desc",
            limit=limit
        )

        return [
            {
                "id": str(e.get("id"))[:8],
                "buyer": e.get("buyer_name"),
                "mensaje": (e.get("original_message") or "")[:50],
                "motivo": (e.get("reason") or "")[:40],
                "tipo": e.get("case_type"),
                "estado": e.get("status"),
                "prioridad": e.get("priority"),
                "fuente": e.get("channel"),
                "fecha": (e.get("created_at") or "")[:10]
            }
            for e in escalations
        ]

    def _execute_interactions_by_case_type(self, params: Dict) -> List[Dict]:
        """Escalaciones por tipo de caso"""
        limit = params.get("limit", 10)

        escalations = self._get_table(
            "escalations",
            select="case_type",
            limit=1000
        )

        from collections import Counter
        counts = Counter(e.get("case_type") or "sin_tipo" for e in escalations)

        return [
            {
                "rank": i,
                "id": case_type,
                "title": (case_type or "Sin tipo").replace("_", " ").title(),
                "value": count
            }
            for i, (case_type, count) in enumerate(counts.most_common(limit), 1)
        ]

    # ============== PREVENTA ==============

    def _execute_preventa_summary(self, params: Dict) -> List[Dict]:
        """KPIs de preventa - no existe en Tienda Lubbi"""
        return [{
            "total_queries": 0,
            "answered": 0,
            "pending": 0,
            "answer_rate": 0,
            "nota": "Modulo de preventa no configurado"
        }]

    def _execute_recent_preventa_queries(self, params: Dict) -> List[Dict]:
        """Consultas de preventa - no existe"""
        return []

    # ============== STOCK ==============

    def _execute_stock_alerts(self, params: Dict) -> List[Dict]:
        """Alertas de stock"""
        limit = params.get("limit", 20)

        try:
            items = self._get_table(
                "v_stock_dashboard",
                select="item_id,title,available_quantity,days_cover,severity,reorder_date",
                filters={"severity": "in.(critical,warning)"},
                order="severity.desc,days_cover.asc",
                limit=limit
            )
        except:
            items = self._get_table(
                "ml_items",
                select="item_id,title,available_quantity",
                filters={"available_quantity": "lt.5"},
                order="available_quantity.asc",
                limit=limit
            )
            return [
                {
                    "id": item.get("item_id"),
                    "title": (item.get("title") or "")[:50],
                    "stock": int(item.get("available_quantity", 0) or 0),
                    "severity": "critical" if int(item.get("available_quantity", 0) or 0) < 2 else "warning",
                    "days_cover": None,
                    "reorder_date": None
                }
                for item in items
            ]

        return [
            {
                "id": item.get("item_id"),
                "title": (item.get("title") or "")[:50],
                "stock": int(item.get("available_quantity", 0) or 0),
                "days_cover": item.get("days_cover"),
                "severity": item.get("severity"),
                "reorder_date": item.get("reorder_date")
            }
            for item in items
        ]

    def _execute_kpi_inventory_summary(self, params: Dict) -> List[Dict]:
        """KPIs de inventario - resumen de estado de stock"""
        try:
            # Obtener todos los items del dashboard de stock
            items = self._get_table(
                "v_stock_dashboard",
                select="severity,days_cover",
                limit=1000
            )

            if not items:
                return [{
                    "critical_count": 0,
                    "warning_count": 0,
                    "ok_count": 0,
                    "total_products": 0,
                    "avg_days_cover": 0
                }]

            critical = sum(1 for item in items if item.get("severity") == "critical")
            warning = sum(1 for item in items if item.get("severity") == "warning")
            ok = sum(1 for item in items if item.get("severity") == "ok")
            total = len(items)

            days_covers = [item.get("days_cover") for item in items if item.get("days_cover") is not None]
            avg_days = round(sum(days_covers) / len(days_covers), 1) if days_covers else 0

            return [{
                "critical_count": critical,
                "warning_count": warning,
                "ok_count": ok,
                "total_products": total,
                "avg_days_cover": avg_days
            }]
        except Exception as e:
            print(f"[_execute_kpi_inventory_summary] Error: {e}")
            # Fallback: contar desde ml_items
            items = self._get_table(
                "ml_items",
                select="item_id,available_quantity",
                filters={"status": "eq.active"},
                limit=1000
            )
            critical = sum(1 for item in items if int(item.get("available_quantity", 0) or 0) < 5)
            warning = sum(1 for item in items if 5 <= int(item.get("available_quantity", 0) or 0) < 10)
            ok = sum(1 for item in items if int(item.get("available_quantity", 0) or 0) >= 10)

            return [{
                "critical_count": critical,
                "warning_count": warning,
                "ok_count": ok,
                "total_products": len(items),
                "avg_days_cover": 0
            }]

    def test_connection(self) -> bool:
        """Prueba la conexion a Supabase REST API"""
        try:
            url = f"{self.base_url}/rest/v1/ml_orders?select=order_id&limit=1"
            response = self.client.get(url, headers=self.headers)
            return response.status_code == 200
        except Exception as e:
            print(f"Error de conexion REST: {e}")
            return False

    def get_tables_info(self) -> Dict[str, int]:
        """Obtiene info de las tablas principales"""
        tables = ["ml_orders", "ml_items", "conversations", "escalations", "messages"]
        info = {}

        for table in tables:
            try:
                url = f"{self.base_url}/rest/v1/{table}?select=id&limit=1"
                response = self.client.get(
                    url,
                    headers={**self.headers, "Prefer": "count=exact"}
                )
                content_range = response.headers.get("content-range", "")
                if "/" in content_range:
                    total = content_range.split("/")[1]
                    info[table] = int(total) if total != "*" else -1
                else:
                    info[table] = len(response.json()) if response.status_code == 200 else 0
            except:
                info[table] = -1

        return info


# Singleton
_client: Optional[SupabaseRESTClient] = None


def get_db_client() -> SupabaseRESTClient:
    """Obtiene el cliente singleton de DB"""
    global _client
    if _client is None:
        _client = SupabaseRESTClient()
    return _client
