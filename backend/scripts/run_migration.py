"""
Script para ejecutar migraciones de checkpointer en PostgreSQL.
Soporta tanto el servidor local como Supabase.
"""
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2

def run_migration(postgres_url: str = None):
    """Ejecuta la migración 002_checkpoints.sql"""

    # Obtener URL de PostgreSQL
    url = postgres_url or os.getenv("POSTGRES_URL")
    if not url:
        print("ERROR: No se encontró POSTGRES_URL en .env")
        return False

    print(f"Conectando a PostgreSQL...")
    print(f"URL: {url[:50]}...")

    try:
        # Conectar
        conn = psycopg2.connect(url)
        conn.autocommit = True
        cursor = conn.cursor()

        print("Conexión exitosa!")

        # Leer archivo de migración
        migration_path = Path(__file__).parent.parent / "migrations" / "002_checkpoints.sql"

        if not migration_path.exists():
            print(f"ERROR: No se encontró {migration_path}")
            return False

        print(f"Leyendo migración: {migration_path}")
        sql = migration_path.read_text(encoding="utf-8")

        # Ejecutar migración
        print("Ejecutando migración...")
        cursor.execute(sql)

        print("✅ Migración ejecutada exitosamente!")

        # Verificar tablas creadas
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('checkpoints', 'checkpoint_writes', 'checkpoint_blobs', 'agent_memory')
            ORDER BY table_name
        """)
        tables = cursor.fetchall()

        print(f"\nTablas creadas:")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


if __name__ == "__main__":
    # Permitir pasar URL como argumento
    url = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_migration(url)
    sys.exit(0 if success else 1)
