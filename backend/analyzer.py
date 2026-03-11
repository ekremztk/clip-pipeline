"""
analyzer.py (V1.5.1 - Embedding Fix + Schema Validation)
---------------------------------------------------------
RAG + Gemini 2.5 Flash ile viral klip analizi.
Embedding modeli uyumluluk düzeltmesi uygulandı.
"""

import os
import psycopg2
import json
import re
from google import genai
from google.genai import types

# --- AYARLAR ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")

MIN_CLIP_DURATION = 15
MAX_CLIP_DURATION = 35

client = genai.Client(api_key=GEMINI_API_KEY)

# Embedding modelleri — sırayla denenir
EMBEDDING_MODELS = [
    "text-embedding-004",
    "models/text-embedding-004",
    "embedding-001",
    "models/embedding-001",
]


# ══════════════════════════════════════════════════════════════════════
# RAG - Vektörel Hafıza
# ══════════════════════════════════════════════════════════════════════

def get_embedding(text):
    """Metni 768 boyutlu vektöre çevirir. Birden fazla model dener."""
    for model_name in EMBEDDING_MODELS:
        try:
            result = client.models.embed_content(
                model=model_name,
                contents=text
            )
            print(f"[Analyzer] ✅ Embedding başarılı: {model_name}")
            return result.embeddings[0].values
        except Exception as e:
            print(f"[Analyzer] ⚠️ Embedding hatası ({model_name}): {e}")
            continue
    
    print("[Analyzer] ❌ Tüm embedding modelleri başarısız.")
    return None


def find_similar_viral_dna(video_description, limit=3):
    """Veritabanında en yakın viral örnekleri bulur (RAG)."""
    if not DATABASE_URL:
        print("[Analyzer] ⚠️ DATABASE_URL tanımlı değil, RAG atlanıyor.")
        return []
    
    query_vector = get_embedding(video_description)
    
    if not query_vector:
        print("[Analyzer] ⚠️ Vektör alınamadı, RAG referansı olmadan devam ediliyor.")
        return []
    
    references = []
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
        print(f"[Analyzer] ⚠️ Veritabanı Bağlantı Hatası: {e}")
        
    return references


# ══════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION
# ══════════════════════════════════════════════════════════════════════

def validate_clips(clips_raw: list, video_duration: float = 99999.0) -> list:
    """Gemini'den dönen klip listesini doğrular."""
    validated = []
    
    for i, clip in enumerate(clips_raw):
        clip_label = f"Klip {i+1}"
        
        required_fields = ["start_time", "end_time", "hook_text", "virality_score"]
        missing = [f for f in required_fields if f not in clip or clip[f] is None]
        if missing:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Eksik alanlar: {missing}")
            continue
        
        try:
            start = float(clip["start_time"])
            end = float(clip["end_time"])
            score = int(clip["virality_score"])
        except (ValueError, TypeError) as e:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Sayısal dönüşüm hatası: {e}")
            continue
        
        duration = end - start
        
        if start < 0:
            start = 0.0
            clip["start_time"] = start
            duration = end - start
        
        if start >= end:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — start_time ({start}) >= end_time ({end})")
            continue
        
        if end > video_duration:
            end = video_duration
            clip["end_time"] = end
            duration = end - start
        
        if duration < MIN_CLIP_DURATION:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Süre çok kısa ({duration:.1f}s)")
            continue
        
        if duration > MAX_CLIP_DURATION + 10:
            print(f"[Validation] ⚠️ {clip_label} — Süre uzun ({duration:.1f}s), cutter kırpacak.")
        
        if not (0 <= score <= 100):
            clip["virality_score"] = 50
        
        hook = str(clip.get("hook_text", "")).strip()
        if len(hook) < 3:
            clip["hook_text"] = "Hook belirlenemedi"
        
        validated.append(clip)
        print(f"[Validation] ✅ {clip_label} ONAYLANDI — {start:.1f}s→{end:.1f}s ({duration:.1f}s) Skor: {clip['virality_score']}")
    
    print(f"[Validation] Sonuç: {len(validated)}/{len(clips_raw)} klip doğrulandı.")
    return validated


# ══════════════════════════════════════════════════════════════════════
# ANA ANALİZ FONKSİYONU
# ══════════════════════════════════════════════════════════════════════

def analyze_video_for_clips(audio_path: str, video_title: str, 
                            transcript_text: str = "", 
                            energy_summary: str = "") -> list:
    """Videonun içindeki viral potansiyelli anları bulur."""
    
    print(f"[Analyzer] '{video_title[:80]}...' için RAG hafızası taranıyor...")
    refs = find_similar_viral_dna(video_title)
    ref_text = json.dumps(refs, ensure_ascii=False) if refs else "Referans bulunamadı, genel viral kurallarını uygula."

    transcript_block = ""
    if transcript_text and len(transcript_text.strip()) > 50:
        truncated = transcript_text[:15000]
        transcript_block = f"""
        TRANSCRIPT (Word-level timestamps from Whisper):
        {truncated}
        {"[...TRUNCATED...]" if len(transcript_text) > 15000 else ""}
        
        IMPORTANT: Use this transcript to find EXACT sentence boundaries. 
        Do NOT cut mid-sentence.
        """
    
    energy_block = ""
    if energy_summary and len(energy_summary.strip()) > 20:
        energy_block = f"""
        AUDIO ENERGY ANALYSIS (Mathematical - from Librosa):
        {energy_summary}
        
        IMPORTANT: Energy peaks indicate emotional moments (laughter, shouting, excitement).
        Prioritize clips that OVERLAP with these high-energy timestamps.
        Silence zones are natural cut points.
        """

    print("[Analyzer] Gemini 2.5 Flash ile klip noktaları analiz ediliyor...")
    try:
        audio_file = client.files.upload(file=audio_path)
        
        prompt = f"""
        You are an elite Viral Video Architect and TikTok/Shorts Retention Algorithm Expert. 
        Your sole purpose is to analyze long-form video content and extract the absolute best 
        15-35 second segments that are mathematically and psychologically optimized to go viral.

        ═══════════════════════════════════════════════════════
        RAG CONTEXT (PROVEN VIRAL DNA FROM DATABASE):
        {ref_text}
        ═══════════════════════════════════════════════════════

        {transcript_block}

        {energy_block}

        ═══════════════════════════════════════════════════════
        CURRENT VIDEO: "{video_title}"
        ═══════════════════════════════════════════════════════

        YOUR MISSION & CONSTRAINTS:
        1. Extract exactly 3 highly viral potential segments.
        2. Determine timestamps by carefully listening to the speech AND cross-referencing 
           the transcript timestamps if available. DO NOT cut mid-sentence.
        3. Add a 0.5-second buffer (pad) to the end_time.
        4. The first 3 seconds of each segment MUST contain a powerful "Hook".
        5. Clip duration MUST be strictly between 15 and 35 seconds.
        6. Timestamps MUST be in raw total SECONDS (float or int), NOT MM:SS. (e.g., 65.5).
        7. You must output ONLY a valid JSON array. DO NOT include markdown formatting.
        8. If energy peaks data is available, PRIORITIZE segments that overlap with high-energy moments.
        9. For each clip, also generate YouTube Shorts metadata (title, description, hashtags).

        EXPECTED JSON OUTPUT FORMAT:
        [
          {{
            "start_time": 124.5,
            "end_time": 154.0,
            "hook_text": "The exact first sentence spoken in the clip",
            "psychological_trigger": "Why this segment holds attention (psychology-based)",
            "rag_reference_used": "Which viral reference was most similar, or 'None'",
            "virality_score": 92,
            "why_selected": "Brief explanation of why THIS moment was chosen over others",
            "suggested_title": "Catchy YouTube Shorts title (max 70 chars)",
            "suggested_description": "2-3 sentence YouTube description with context",
            "suggested_hashtags": "#relevant #hashtags #for #discovery",
            "audio_energy_note": "If energy data was available, note the energy correlation",
            "trim_note": "Any editing suggestion (e.g., 'trim first 0.5s of silence') or 'none'"
          }}
        ]
        """
        
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=json_config
        )
        
        try:
            client.files.delete(name=audio_file.name)
        except:
            pass

        raw_text = response.text.strip()
        
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)
            
        print(f"[Analyzer] Gemini'den gelen ham cevap boyutu: {len(raw_text)} karakter")

        try:
            parsed_json = json.loads(raw_text)
        except json.JSONDecodeError as je:
            print(f"[Analyzer] ⚠️ JSON Parse Hatası: {je}")
            print(f"[Analyzer] Hatalı Metin (İlk 500 karakter): {raw_text[:500]}...")
            return []
        
        validated = validate_clips(parsed_json)
        return validated
            
    except Exception as e:
        print(f"[Analyzer] ❌ Gemini Analiz Hatası: {e}")
        return []