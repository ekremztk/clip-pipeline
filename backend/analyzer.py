"""
analyzer.py (V2.0 - Supabase RAG + Schema Validation)
------------------------------------------------------
RAG sorguları artık Supabase PostgreSQL üzerinden yapılır.
DATABASE_URL tanımlı değilse Supabase connection string otomatik oluşturulur.
"""

import os
import psycopg2  # type: ignore
import json
import re
from google import genai  # type: ignore
from google.genai import types  # type: ignore

# --- AYARLAR ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# RAG veritabanı bağlantısı: Önce DATABASE_URL, yoksa Supabase
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")

MIN_CLIP_DURATION = 15
MAX_CLIP_DURATION = 35

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODELS = [
    "gemini-embedding-001",
    "models/gemini-embedding-001",
]


# ══════════════════════════════════════════════════════════════════════
# RAG
# ══════════════════════════════════════════════════════════════════════

def get_embedding(text):
    """Metni 768 boyutlu vektöre çevirir. Birden fazla model dener."""
    for model_name in EMBEDDING_MODELS:
        for attempt in range(3):
            try:
                result = client.models.embed_content(
                    model=model_name,
                    contents=text
                )
                print(f"[Analyzer] ✅ Embedding başarılı: {model_name} ({len(result.embeddings[0].values)} boyut)")
                return list(result.embeddings[0].values)
            except Exception as e:
                error_str = str(e)
                print(f"[Analyzer] ⚠️ Embedding hatası ({model_name}, deneme {attempt+1}): {e}")
                if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                    import time
                    time.sleep(30)
                    continue
                break
    
    print("[Analyzer] ❌ Tüm embedding modelleri başarısız.")
    return None


def find_similar_viral_dna(video_description, channel_id: str = "speedy_cast", limit=3):
    """Veritabanında en yakın viral örnekleri bulur (RAG)."""
    if not DATABASE_URL:
        print("[Analyzer] ⚠️ DATABASE_URL tanımlı değil, RAG atlanıyor.")
        return []
    
    query_vector = get_embedding(video_description)
    if not query_vector:
        return []
    
    references = []
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                search_query = """
                SELECT video_title, hook_text, why_it_went_viral, viral_score
                FROM viral_library
                WHERE channel_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """
                cur.execute(search_query, (channel_id, query_vector, limit))
                rows = cur.fetchall()
                for row in rows:
                    references.append({
                        "title": row[0],
                        "hook": row[1],
                        "reason": row[2],
                        "score": row[3]
                    })
    except Exception as e:
        print(f"[Analyzer] ⚠️ RAG DB Hatası: {e}")
        
    return references


# ══════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION
# ══════════════════════════════════════════════════════════════════════

def validate_clips(clips_raw: list, video_duration: float = 99999.0) -> list:
    validated = []
    for i, clip in enumerate(clips_raw):
        label = f"Klip {i+1}"
        
        required = ["start_time", "end_time", "hook_text", "virality_score"]
        missing = [f for f in required if f not in clip or clip[f] is None]
        if missing:
            print(f"[Validation] ⚠️ {label} REDDEDILDI — Eksik: {missing}")
            continue
        
        try:
            start = float(clip["start_time"])
            end = float(clip["end_time"])
            score = int(clip["virality_score"])
        except (ValueError, TypeError) as e:
            print(f"[Validation] ⚠️ {label} REDDEDILDI — {e}")
            continue
        
        duration = end - start
        if start < 0:
            start = 0.0
            clip["start_time"] = start
            duration = end - start
        if start >= end:
            print(f"[Validation] ⚠️ {label} REDDEDILDI — start >= end")
            continue
        if end > video_duration:
            end = video_duration
            clip["end_time"] = end
            duration = end - start
        if duration < MIN_CLIP_DURATION:
            print(f"[Validation] ⚠️ {label} REDDEDILDI — Çok kısa ({duration:.1f}s)")
            continue
        if not (0 <= score <= 100):
            clip["virality_score"] = 50
        
        hook = str(clip.get("hook_text", "")).strip()
        if len(hook) < 3:
            clip["hook_text"] = "Hook belirlenemedi"
        
        validated.append(clip)
        print(f"[Validation] ✅ {label} ONAYLANDI — {start:.1f}s→{end:.1f}s ({duration:.1f}s) Skor: {clip['virality_score']}")
    
    print(f"[Validation] Sonuç: {len(validated)}/{len(clips_raw)} klip doğrulandı.")
    return validated


# ══════════════════════════════════════════════════════════════════════
# ANA ANALİZ
# ══════════════════════════════════════════════════════════════════════

def analyze_video_for_clips(audio_path: str, video_title: str, 
                            transcript_text: str = "", 
                            energy_summary: str = "",
                            channel_id: str = "speedy_cast") -> list:
    
    # Kanal config yükle (dinamik — yeni kanal ekleyince bu kod değişmez)
    from channels.channel_registry import get_channel_config
    ch_config = get_channel_config(channel_id)
    if ch_config:
        ch_min = ch_config.MIN_CLIP_DURATION
        ch_max = ch_config.MAX_CLIP_DURATION
        ch_system_prompt = ch_config.SYSTEM_PROMPT
    else:
        ch_min = MIN_CLIP_DURATION
        ch_max = MAX_CLIP_DURATION
        ch_system_prompt = ""

    print(f"[Analyzer] RAG hafızası taranıyor...")
    refs = find_similar_viral_dna(video_title, channel_id=channel_id)
    ref_text = json.dumps(refs, ensure_ascii=False) if refs else "Referans bulunamadı, genel viral kurallarını uygula."

    transcript_block = ""
    if transcript_text and len(transcript_text.strip()) > 50:
        truncated = transcript_text[:15000]  # type: ignore[index]
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
        
        IMPORTANT: Energy peaks indicate emotional moments.
        Prioritize clips that OVERLAP with high-energy timestamps.
        Silence zones are natural cut points.
        """

    print("[Analyzer] Gemini 2.5 Flash ile analiz ediliyor...")
    try:
        audio_file = client.files.upload(file=audio_path)
        
        channel_context = f"\nCHANNEL CONTEXT:\n{ch_system_prompt}\n" if ch_system_prompt else ""
        
        prompt = f"""
        {channel_context}
        You are an elite Viral Video Architect and TikTok/Shorts Retention Algorithm Expert. 
        Your sole purpose is to analyze long-form video content and extract the absolute best 
        15-35 second segments optimized to go viral.

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
        2. Use transcript timestamps for EXACT sentence boundaries. Do NOT cut mid-sentence.
        3. Add 0.5s buffer to end_time.
        4. First 3 seconds MUST contain a powerful "Hook".
        5. Duration MUST be {ch_min}-{ch_max} seconds.
        6. Timestamps in raw SECONDS (float/int), NOT MM:SS.
        7. Output ONLY valid JSON array, no markdown.
        8. Prioritize segments overlapping with energy peaks.
        9. Generate YouTube Shorts metadata for each clip.

        JSON FORMAT:
        [
          {{
            "start_time": 124.5,
            "end_time": 154.0,
            "hook_text": "Exact first sentence in clip",
            "psychological_trigger": "Why this holds attention",
            "rag_reference_used": "Which reference or 'None'",
            "virality_score": 92,
            "why_selected": "Why THIS moment was chosen",
            "suggested_title": "YouTube Shorts title (max 70 chars)",
            "suggested_description": "2-3 sentence description",
            "suggested_hashtags": "#relevant #hashtags",
            "audio_energy_note": "Energy correlation note",
            "trim_note": "Edit suggestion or 'none'"
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
        except Exception:
            pass

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)
            
        print(f"[Analyzer] Gemini cevap boyutu: {len(raw_text)} karakter")

        try:
            parsed_json = json.loads(raw_text)
        except json.JSONDecodeError as je:
            print(f"[Analyzer] ⚠️ JSON Parse Hatası: {je}")
            return []
        
        return validate_clips(parsed_json)
            
    except Exception as e:
        print(f"[Analyzer] ❌ Gemini Hatası: {e}")
        return []