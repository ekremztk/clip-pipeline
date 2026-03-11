import psycopg2
import json
from google import genai

# --- AYARLAR ---
GEMINI_API_KEY = "BURAYA_API_KEY"
DATABASE_URL = "POSTGRESQL_PUBLIC_URL_BURAYA"

client = genai.Client(api_key=GEMINI_API_KEY)

def get_embedding(text):
    """Metni 768 boyutlu vektöre çevirir. Çökmelere karşı korumalıdır."""
    try:
        result = client.models.embed_content(
            model="text-embedding-004",
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[!] API veya Ağ Hatası (Embedding): {e}")
        return None

def find_similar_viral_dna(video_description, limit=3):
    """Veritabanında en yakın viral örnekleri bulur (RAG). DB bağlantısı güvenlidir."""
    query_vector = get_embedding(video_description)
    
    # Eğer API çöktüyse ve vektör alamadıysak boş referans dön (sistemi çökertme)
    if not query_vector:
        print("[!] Vektör alınamadığı için RAG referansı olmadan devam ediliyor.")
        return []
    
    references = []
    # 'with' yapısı, işlem bitince veritabanı bağlantısını otomatik ve güvenli şekilde kapatır
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                search_query = """
                SELECT video_title, hook_text, why_it_went_viral, viral_score
                FROM viral_library
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """
                cur.execute(search_query, (query_vector, limit))
                rows = cur.fetchall()
                
                for row in rows:
                    references.append({
                        "title": row[0],
                        "hook": row[1],
                        "reason": row[2],
                        "score": row[3]
                    })
    except Exception as e:
        print(f"[!] Veritabanı Bağlantı Hatası: {e}")
        
    return references

def analyze_video_for_clips(audio_path, video_title):
    """Videonun içindeki viral potansiyelli anları bulur ve FFmpeg için saniye döner."""
    print(f"[*] '{video_title}' için RAG hafızası taranıyor...")
    refs = find_similar_viral_dna(video_title)
    ref_text = json.dumps(refs, ensure_ascii=False) if refs else "Referans bulunamadı, genel viral kurallarını uygula."

    print("[*] Gemini 2.5 Flash ile klip noktaları analiz ediliyor...")
    try:
        audio_file = client.files.upload(file=audio_path)
        
        prompt = f"""
        You are an elite Viral Video Architect and TikTok/Shorts Retention Algorithm Expert. 
        Your sole purpose is to analyze long-form video transcripts and extract the absolute best 15-35 second segments that are mathematically and psychologically optimized to go viral.

        RAG CONTEXT (PROVEN VIRAL DNA):
        {ref_text}

        CURRENT VIDEO TITLE: "{video_title}"

        YOUR MISSION & CONSTRAINTS:
        1. Extract exactly 3 highly viral potential segments.
        2. Determine timestamps by carefully listening to the speech start and end points. DO NOT cut mid-sentence.
        3. Add a 0.5-second buffer (pad) to the end_time. If the speech ends at 154.0, set end_time to 154.5 to avoid cutting the last word's tail and allow natural breathing room.
        4. The first 3 seconds of each segment MUST contain a powerful "Hook" (bold claim, open loop, extreme emotion).
        5. Clip duration MUST be strictly between 15 and 35 seconds.
        6. Timestamps MUST be in raw total SECONDS (float or int), NOT MM:SS. (e.g., 65.5 for 1 min 5.5 seconds).
        7. You must output ONLY a valid JSON array. Do not wrap it in markdown block quotes.

        EXPECTED JSON OUTPUT FORMAT:
        [
          {{
            "start_time": 124.5,
            "end_time": 154.0,
            "hook_text": "The exact first sentence spoken in the clip",
            "psychological_trigger": "Explain the psychological reason this holds attention",
            "rag_reference_used": "Which reference was used",
            "virality_score": 98
          }}
        ]
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config={"response_mime_type": "application/json"}
        )
        
        # İşlem bitince dosyayı Google sunucularından temizle
        client.files.delete(name=audio_file.name)
        
        return json.loads(response.text)
        
    except Exception as e:
        print(f"[!] Gemini Analiz Hatası: {e}")
        return []