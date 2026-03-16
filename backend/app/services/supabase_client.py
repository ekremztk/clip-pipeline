from supabase import create_client, Client
from app.config import settings

_supabase_client = None

def get_client() -> Client | None:
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
        
    try:
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_SERVICE_KEY
        
        if not url or not key:
            print("[SupabaseClient] Error: SUPABASE_URL or SUPABASE_SERVICE_KEY is missing.")
            return None
            
        _supabase_client = create_client(url, key)
        print("[SupabaseClient] Successfully connected to Supabase.")
        return _supabase_client
    except Exception as e:
        print(f"[SupabaseClient] Error: {e}")
        return None

def get_db_url() -> str | None:
    try:
        url = settings.DATABASE_URL
        if not url:
            print("[SupabaseClient] Error: DATABASE_URL is missing.")
            return None
        return url
    except Exception as e:
        print(f"[SupabaseClient] Error retrieving DATABASE_URL: {e}")
        return None
