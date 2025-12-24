from .supabase_client import SupabaseRESTClient, get_db_client

# Alias para compatibilidad
SupabaseClient = SupabaseRESTClient

__all__ = ["SupabaseClient", "SupabaseRESTClient", "get_db_client"]
