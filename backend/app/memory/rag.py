import psycopg2
from psycopg2.extras import RealDictCursor
from app.services.gemini_client import get_gemini_client
from app.services.supabase_client import get_client
from app.config import settings

def embed_text(text: str) -> list | None:
    try:
        print(f"[RAG] Generating embedding for text (length: {len(text)})")
        gemini = get_gemini_client()
        result = gemini.models.embed_content(
            model="text-embedding-004",
            contents=text
        )
        if not result or not result.embeddings:
            print("[RAG] Failed to get embedding from Gemini response")
            return None
            
        print("[RAG] Successfully generated embedding")
        return result.embeddings[0].values
    except Exception as e:
        print(f"[RAG] Error generating embedding: {e}")
        return None

def search_similar_clips(query_text: str, channel_id: str, limit: int = 3) -> list:
    try:
        print(f"[RAG] Searching for similar clips for channel {channel_id}")
        embedding = embed_text(query_text)
        if not embedding:
            print("[RAG] Embedding failed, cannot search")
            return []
            
        conn = psycopg2.connect(settings.DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                cur.execute("""
                    SELECT id, hook_text, content_type, clip_summary, what_makes_it_work, views
                    FROM reference_clips
                    WHERE channel_id = %s
                    ORDER BY clip_summary_embedding <=> %s::vector
                    LIMIT %s
                """, (channel_id, embedding_str, limit))
                results = cur.fetchall()
                print(f"[RAG] Found {len(results)} similar clips")
                return [dict(row) for row in results]
        finally:
            conn.close()
    except Exception as e:
        print(f"[RAG] Error searching similar clips: {e}")
        return []

def add_to_rag(clip_id: str, channel_id: str, summary_text: str) -> bool:
    try:
        print(f"[RAG] Adding clip {clip_id} to RAG for channel {channel_id}")
        embedding = embed_text(summary_text)
        if not embedding:
            print("[RAG] Embedding failed, cannot add to RAG")
            return False
            
        supabase = get_client()
        
        # Update clips table
        print(f"[RAG] Updating clip {clip_id} with summary and embedding")
        supabase.table("clips").update({
            "clip_summary": summary_text,
            "clip_summary_embedding": embedding
        }).eq("id", clip_id).execute()
        
        # Insert into reference_clips
        print(f"[RAG] Inserting clip {clip_id} into reference_clips")
        conn = psycopg2.connect(settings.DATABASE_URL)
        try:
            with conn.cursor() as cur:
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                cur.execute("""
                    INSERT INTO reference_clips (
                        channel_id, source, source_clip_id,
                        clip_summary, clip_summary_embedding, analyzed_at
                    ) VALUES (
                        %s, 'own_successful', %s,
                        %s, %s::vector, NOW()
                    )
                """, (channel_id, clip_id, summary_text, embedding_str))
            conn.commit()
        finally:
            conn.close()
            
        print(f"[RAG] Successfully added clip {clip_id} to RAG")
        return True
    except Exception as e:
        print(f"[RAG] Error adding to RAG: {e}")
        return False

def format_rag_context(similar_clips: list) -> str:
    try:
        if not similar_clips:
            return ""
            
        lines = ["Similar successful clips from this channel:"]
        for i, clip in enumerate(similar_clips, 1):
            hook = clip.get('hook_text', '')
            c_type = clip.get('content_type', '')
            what_worked = clip.get('what_makes_it_work', '')
            lines.append(f" {i}. Hook: '{hook}' | Type: {c_type} | What worked: {what_worked}")
            
        return "\n".join(lines)
    except Exception as e:
        print(f"[RAG] Error formatting context: {e}")
        return ""
