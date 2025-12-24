#!/usr/bin/env python3
"""
refresh_schema.py - Extrae el esquema real de Supabase y genera schema_snapshot.json

Este script debe ejecutarse:
- Diariamente via cron
- Manualmente cuando cambie el esquema de BD
- En CI/CD antes de deploy

Uso:
    python scripts/refresh_schema.py
    python scripts/refresh_schema.py --output data/schema_snapshot.json
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Agregar el directorio raíz al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar .env
load_dotenv()


class SchemaExtractor:
    """Extrae el esquema de la base de datos Supabase"""

    # Tablas a incluir (whitelist)
    ALLOWED_TABLES = [
        'orders', 'order_items', 'products', 'buyers',
        'agent_interactions', 'escalations', 'conversations',
        'ml_items', 'ml_orders', 'ml_order_items', 'ml_buyers'
    ]

    # Tablas a excluir siempre (sistema/auth)
    EXCLUDED_TABLES = [
        'schema_migrations', 'auth_users', 'auth_tokens',
        'supabase_functions', 'storage_objects', 'pg_stat_statements'
    ]

    # Descripciones de negocio (enriquecimiento manual)
    TABLE_DESCRIPTIONS = {
        'orders': 'Ordenes de MercadoLibre - tabla principal de ventas',
        'order_items': 'Items de cada orden - detalle de productos vendidos',
        'products': 'Catalogo de productos con stock actual',
        'buyers': 'Compradores/clientes de MercadoLibre',
        'agent_interactions': 'Interacciones del agente AI con compradores',
        'escalations': 'Casos escalados a humanos para revisión',
        'conversations': 'Hilos de conversación con clientes',
        'ml_items': 'Productos de MercadoLibre (items)',
        'ml_orders': 'Ordenes de MercadoLibre (packs)',
        'ml_order_items': 'Items dentro de ordenes ML',
        'ml_buyers': 'Compradores de MercadoLibre'
    }

    # Keywords de búsqueda por tabla
    TABLE_KEYWORDS = {
        'orders': ['ventas', 'ordenes', 'facturacion', 'ingresos', 'pedidos'],
        'order_items': ['productos vendidos', 'items', 'unidades', 'detalle'],
        'products': ['inventario', 'stock', 'productos', 'catalogo'],
        'buyers': ['clientes', 'compradores', 'usuarios'],
        'agent_interactions': ['interacciones', 'agente AI', 'mensajes', 'casos'],
        'escalations': ['escalados', 'escalaciones', 'soporte', 'pendientes'],
        'conversations': ['conversaciones', 'chats', 'hilos'],
        'ml_items': ['productos ML', 'publicaciones'],
        'ml_orders': ['ordenes ML', 'packs'],
        'ml_order_items': ['items ML', 'detalle orden'],
        'ml_buyers': ['compradores ML', 'clientes ML']
    }

    def __init__(self, supabase_url: str, supabase_key: str):
        self.client: Client = create_client(supabase_url, supabase_key)

    def get_tables(self) -> List[Dict[str, Any]]:
        """Obtiene lista de tablas del schema public"""
        query = """
        SELECT
            table_name,
            obj_description((quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass) as comment
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        try:
            result = self.client.rpc('execute_sql', {'query': query}).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Error obteniendo tablas (usando método alternativo): {e}")
            # Fallback: intentar con una tabla conocida para verificar conexión
            return self._get_tables_fallback()

    def _get_tables_fallback(self) -> List[Dict[str, Any]]:
        """Fallback: obtener tablas consultando directamente"""
        tables = []
        for table in self.ALLOWED_TABLES:
            try:
                # Verificar si la tabla existe haciendo un count
                self.client.table(table).select('*', count='exact').limit(0).execute()
                tables.append({'table_name': table, 'comment': None})
            except:
                pass
        return tables

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Obtiene columnas de una tabla"""
        query = f"""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = '{table_name}'
        ORDER BY ordinal_position
        """
        try:
            result = self.client.rpc('execute_sql', {'query': query}).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Error obteniendo columnas de {table_name}: {e}")
            return self._get_columns_fallback(table_name)

    def _get_columns_fallback(self, table_name: str) -> List[Dict[str, Any]]:
        """Fallback: inferir columnas de una fila de datos"""
        try:
            result = self.client.table(table_name).select('*').limit(1).execute()
            if result.data and len(result.data) > 0:
                row = result.data[0]
                columns = []
                for col_name, value in row.items():
                    data_type = 'unknown'
                    if isinstance(value, bool):
                        data_type = 'boolean'
                    elif isinstance(value, int):
                        data_type = 'bigint'
                    elif isinstance(value, float):
                        data_type = 'numeric'
                    elif isinstance(value, str):
                        data_type = 'text'
                    columns.append({
                        'column_name': col_name,
                        'data_type': data_type,
                        'is_nullable': 'YES'
                    })
                return columns
        except Exception as e:
            print(f"Fallback también falló para {table_name}: {e}")
        return []

    def get_foreign_keys(self) -> List[Dict[str, Any]]:
        """Obtiene relaciones entre tablas"""
        query = """
        SELECT
            tc.table_name as from_table,
            kcu.column_name as from_column,
            ccu.table_name as to_table,
            ccu.column_name as to_column
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
        """
        try:
            result = self.client.rpc('execute_sql', {'query': query}).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Error obteniendo foreign keys: {e}")
            return []

    def get_primary_keys(self) -> Dict[str, List[str]]:
        """Obtiene primary keys por tabla"""
        query = """
        SELECT
            tc.table_name,
            kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
        AND tc.table_schema = 'public'
        """
        try:
            result = self.client.rpc('execute_sql', {'query': query}).execute()
            pks = {}
            for row in (result.data or []):
                table = row['table_name']
                col = row['column_name']
                if table not in pks:
                    pks[table] = []
                pks[table].append(col)
            return pks
        except Exception as e:
            print(f"Error obteniendo primary keys: {e}")
            return {}

    def build_column_description(self, col: Dict, is_pk: bool, fk_info: str = None) -> str:
        """Construye descripción de columna"""
        data_type = col.get('data_type', 'unknown')
        parts = [data_type]

        if is_pk:
            parts.insert(0, 'PK')
        if fk_info:
            parts.append(f'FK -> {fk_info}')
        if col.get('is_nullable') == 'NO' and not is_pk:
            parts.append('NOT NULL')

        return ' '.join(parts)

    def extract_full_schema(self) -> Dict[str, Any]:
        """Extrae el esquema completo y lo formatea"""
        print("Conectando a Supabase...")

        # Obtener metadatos
        tables_raw = self.get_tables()
        pks = self.get_primary_keys()
        fks = self.get_foreign_keys()

        # Construir mapa de FKs
        fk_map = {}
        for fk in fks:
            key = f"{fk['from_table']}.{fk['from_column']}"
            fk_map[key] = f"{fk['to_table']}.{fk['to_column']}"

        # Construir estructura de tablas
        tables = {}
        for table_info in tables_raw:
            table_name = table_info['table_name']

            # Filtrar tablas
            if table_name in self.EXCLUDED_TABLES:
                continue
            if self.ALLOWED_TABLES and table_name not in self.ALLOWED_TABLES:
                continue

            print(f"  Procesando tabla: {table_name}")

            columns = self.get_columns(table_name)
            table_pks = pks.get(table_name, [])

            columns_dict = {}
            for col in columns:
                col_name = col['column_name']
                is_pk = col_name in table_pks
                fk_key = f"{table_name}.{col_name}"
                fk_info = fk_map.get(fk_key)

                columns_dict[col_name] = self.build_column_description(col, is_pk, fk_info)

            tables[table_name] = {
                'description': self.TABLE_DESCRIPTIONS.get(table_name, table_info.get('comment') or f'Tabla {table_name}'),
                'columns': columns_dict,
                'key_queries': self.TABLE_KEYWORDS.get(table_name, [table_name])
            }

        # Construir relaciones
        relationships = []
        for fk in fks:
            if fk['from_table'] in tables and fk['to_table'] in tables:
                relationships.append({
                    'from': f"{fk['from_table']}.{fk['from_column']}",
                    'to': f"{fk['to_table']}.{fk['to_column']}",
                    'type': 'many-to-one'
                })

        # Construir queries comunes
        common_queries = {
            'ventas_totales': "SELECT SUM(total_amount) FROM orders WHERE status = 'paid'",
            'productos_vendidos': "SELECT oi.title, SUM(oi.quantity) as total FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE o.status = 'paid' GROUP BY oi.title ORDER BY total DESC",
            'stock_bajo': "SELECT id, title, available_quantity FROM products WHERE available_quantity < 10 AND status = 'active'",
            'tasa_escalado': "SELECT COUNT(*) FILTER (WHERE was_escalated) * 100.0 / NULLIF(COUNT(*), 0) FROM agent_interactions"
        }

        return {
            'version': '2.0.0',
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'source': 'refresh_schema.py',
            'tables': tables,
            'relationships': relationships,
            'common_queries': common_queries
        }


def main():
    parser = argparse.ArgumentParser(description='Extrae esquema de Supabase')
    parser.add_argument('--output', '-o', default='data/schema_snapshot.json',
                       help='Archivo de salida (default: data/schema_snapshot.json)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Solo mostrar, no guardar archivo')
    args = parser.parse_args()

    # Obtener credenciales
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_ANON_KEY')

    if not supabase_url or not supabase_key:
        print("ERROR: Faltan variables SUPABASE_URL y/o SUPABASE_SERVICE_KEY")
        sys.exit(1)

    print(f"Supabase URL: {supabase_url}")

    # Extraer esquema
    extractor = SchemaExtractor(supabase_url, supabase_key)
    schema = extractor.extract_full_schema()

    # Mostrar resumen
    print(f"\nEsquema extraído:")
    print(f"  - Tablas: {len(schema['tables'])}")
    print(f"  - Relaciones: {len(schema['relationships'])}")
    print(f"  - Generado: {schema['generated_at']}")

    if args.dry_run:
        print("\n[DRY RUN] JSON generado:")
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    else:
        # Guardar archivo
        output_path = Path(__file__).parent.parent / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)

        print(f"\nGuardado en: {output_path}")


if __name__ == '__main__':
    main()
