"""Director memory tools — save/query long-term semantic memory."""

import uuid
from typing import Any
from app.services.supabase_client import get_client
from app.services.gemini_client import embed_content


def save_memory(content: str, type: str, tags: list[str] | None = None, source: str = "director_inference") -> str:
    """
    Save a memory record with pgvector embedding.
    type: 'decision' | 'context' | 'plan' | 'note' | 'learning'
    Returns the new memory ID.
    """
    try:
        valid_types = {"decision", "context", "plan", "note", "learning"}
        if type not in valid_types:
            return f"[ERROR] Invalid type. Choose from: {valid_types}"

        embedding = embed_content(content)
        client = get_client()
        res = client.table("director_memory").insert({
            "type": type,
            "content": content,
            "embedding": embedding,
            "tags": tags or [],
            "source": source,
        }).execute()
        new_id = res.data[0]["id"] if res.data else "unknown"
        print(f"[DirectorMemory] Saved memory {new_id} ({type})")
        return new_id
    except Exception as e:
        print(f"[DirectorMemory] save_memory error: {e}")
        return f"[ERROR] {e}"


def query_memory(query: str, type: str | None = None, top_k: int = 5) -> list[dict]:
    """
    Semantic search over director_memory using pgvector cosine similarity.
    Returns top_k most relevant memories.
    """
    try:
        embedding = embed_content(query)
        client = get_client()

        # Use rpc for vector search
        params: dict[str, Any] = {
            "query_embedding": embedding,
            "match_count": top_k,
        }
        if type:
            params["filter_type"] = type

        # Try RPC first (requires function in Supabase)
        try:
            res = client.rpc("match_director_memory", params).execute()
            return res.data or []
        except Exception:
            # Fallback: fetch recent memories without vector search
            q = client.table("director_memory").select("id, type, content, tags, source, created_at")
            if type:
                q = q.eq("type", type)
            res = q.order("created_at", desc=True).limit(top_k).execute()
            return res.data or []
    except Exception as e:
        print(f"[DirectorMemory] query_memory error: {e}")
        return [{"error": str(e)}]


def list_memories(type: str | None = None) -> list[dict]:
    """List all memories, optionally filtered by type."""
    try:
        client = get_client()
        q = client.table("director_memory").select("id, type, content, tags, source, created_at")
        if type:
            q = q.eq("type", type)
        res = q.order("created_at", desc=True).limit(100).execute()
        return res.data or []
    except Exception as e:
        print(f"[DirectorMemory] list_memories error: {e}")
        return [{"error": str(e)}]


def delete_memory(memory_id: str) -> bool:
    """Delete a memory record by ID."""
    try:
        client = get_client()
        client.table("director_memory").delete().eq("id", memory_id).execute()
        return True
    except Exception as e:
        print(f"[DirectorMemory] delete_memory error: {e}")
        return False


def get_conversation_history(session_id: str, last_n: int = 20) -> list[dict]:
    """Fetch last N conversation turns for a session."""
    try:
        client = get_client()
        res = (client.table("director_conversations")
               .select("role, content, tool_calls, timestamp")
               .eq("session_id", session_id)
               .order("timestamp", desc=False)
               .limit(last_n)
               .execute())
        return res.data or []
    except Exception as e:
        print(f"[DirectorMemory] get_conversation_history error: {e}")
        return []


def save_conversation_turn(session_id: str, role: str, content: str, tool_calls: list | None = None) -> None:
    """Persist a conversation turn."""
    try:
        client = get_client()
        client.table("director_conversations").insert({
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_calls": tool_calls,
        }).execute()
    except Exception as e:
        print(f"[DirectorMemory] save_conversation_turn error: {e}")
