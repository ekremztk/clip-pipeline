"""
analyzer.py (V1.5 - Full Context + Schema Validation)
------------------------------------------------------
RAG + Gemini 2.5 Flash ile viral klip analizi.
Artık transkript ve ses enerji verisi de Gemini'ye gönderiliyor.
Çıktı, zorunlu schema validation'dan geçiriliyor.
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

# Klip süre limitleri (saniye)
MIN_CLIP_DURATION = 15
MAX_CLIP_DURATION = 35

client = genai.Client(api_key=GEMINI_API_KEY)


# ══════════════════════════════════════════════════════════════════════
# RAG - Vektörel Hafıza
# ══════════════════════════════════════════════════════════════════════

def get_embedding(text):
    """Metni 768 boyutlu vektöre çevirir. Çökmelere karşı korumalıdır."""
    try:
        result = client.models.embed_content(
            model="text-embedding-004",
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[!] Embedding Hatası: {e}")
        try:
            print("[*] Embedding için 'models/text-embedding-004' deneniyor...")
            result = client.models.embed_content(
                model="models/text-embedding-004",
                contents=text
            )
            return result.embeddings[0].values
        except Exception as e2:
            print(f"[!] Alternatif Embedding de başarısız: {e2}")
            return None


def find_similar_viral_dna(video_description, limit=3):
    """Veritabanında en yakın viral örnekleri bulur (RAG). DB bağlantısı güvenlidir."""
    query_vector = get_embedding(video_description)
    
    if not query_vector:
        print("[!] Vektör alınamadığı için RAG referansı olmadan devam ediliyor.")
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
        print(f"[!] Veritabanı Bağlantı Hatası: {e}")
        
    return references


# ══════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION - Gemini Çıktı Koruması
# ══════════════════════════════════════════════════════════════════════

def validate_clips(clips_raw: list, video_duration: float = 99999.0) -> list:
    """
    Gemini'den dönen klip listesini doğrular.
    Geçersiz klipleri loglar ve listeden çıkarır. Pipeline çökmez.
    
    Kontroller:
    - Zorunlu alanlar mevcut mu (start_time, end_time, hook_text, virality_score)
    - start_time < end_time mi
    - Süre MIN_CLIP_DURATION - MAX_CLIP_DURATION arasında mı
    - virality_score 0-100 arası mı
    - start_time ve end_time sayısal mı
    """
    validated = []
    
    for i, clip in enumerate(clips_raw):
        clip_label = f"Klip {i+1}"
        
        # --- Zorunlu alan kontrolü ---
        required_fields = ["start_time", "end_time", "hook_text", "virality_score"]
        missing = [f for f in required_fields if f not in clip or clip[f] is None]
        if missing:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Eksik alanlar: {missing}")
            continue
        
        # --- Sayısal değer kontrolü ---
        try:
            start = float(clip["start_time"])
            end = float(clip["end_time"])
            score = int(clip["virality_score"])
        except (ValueError, TypeError) as e:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Sayısal dönüşüm hatası: {e}")
            continue
        
        # --- Mantık kontrolleri ---
        duration = end - start
        
        if start < 0:
            print(f"[Validation] ⚠️ {clip_label} — start_time negatif ({start}), 0'a düzeltildi.")
            start = 0.0
            clip["start_time"] = start
            duration = end - start
        
        if start >= end:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — start_time ({start}) >= end_time ({end})")
            continue
        
        if end > video_duration:
            print(f"[Validation] ⚠️ {clip_label} — end_time ({end}) video süresini ({video_duration}) aşıyor, kırpıldı.")
            end = video_duration
            clip["end_time"] = end
            duration = end - start
        
        if duration < MIN_CLIP_DURATION:
            print(f"[Validation] ⚠️ {clip_label} REDDEDILDI — Süre çok kısa ({duration:.1f}s < {MIN_CLIP_DURATION}s)")
            continue
        
        if duration > MAX_CLIP_DURATION + 10:
            # 10 saniye tolerans veriyoruz çünkü cutter.py kendi padding/trim mantığını uygulayacak
            print(f"[Validation] ⚠️ {clip_label} — Süre uzun ({duration:.1f}s), cutter kırpacak.")
        
        if not (0 <= score <= 100):
            print(f"[Validation] ⚠️ {clip_label} — Skor sınır dışı ({score}), 50'ye sabitlendi.")
            clip["virality_score"] = 50
        
        # --- Hook kontrolü ---
        hook = str(clip.get("hook_text", "")).strip()
        if len(hook) < 3:
            print(f"[Validation] ⚠️ {clip_label} — Hook çok kısa, devam ediliyor.")
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
    """
    Videonun içindeki viral potansiyelli anları bulur.
    
    Parametreler:
    - audio_path: Gemini'ye gönderilecek ses dosyası
    - video_title: Video başlığı + açıklama bağlamı
    - transcript_text: Groq/Gemini transkript çıktısı (opsiyonel, zenginleştirme)
    - energy_summary: Librosa enerji analizi özeti (opsiyonel, zenginleştirme)
    """
    
    # --- RAG Hafıza Taraması ---
    print(f"[Analyzer] '{video_title}' için RAG hafızası taranıyor...")
    refs = find_similar_viral_dna(video_title)
    ref_text = json.dumps(refs, ensure_ascii=False) if refs else "Referans bulunamadı, genel viral kurallarını uygula."

    # --- Transkript bölümü ---
    transcript_block = ""
    if transcript_text and len(transcript_text.strip()) > 50:
        # Gemini'nin context window'unu aşmamak için ilk 15000 karakter
        truncated = transcript_text[:15000]
        transcript_block = f"""
        TRANSCRIPT (Word-level timestamps from Whisper):
        {truncated}
        {"[...TRUNCATED...]" if len(transcript_text) > 15000 else ""}
        
        IMPORTANT: Use this transcript to find EXACT sentence boundaries. 
        Do NOT cut mid-sentence. Your start_time should begin at the start of a sentence 
        and end_time should end at the completion of a sentence.
        """
    
    # --- Enerji analizi bölümü ---
    energy_block = ""
    if energy_summary and len(energy_summary.strip()) > 20:
        energy_block = f"""
        AUDIO ENERGY ANALYSIS (Mathematical - from Librosa):
        {energy_summary}
        
        IMPORTANT: Energy peaks indicate emotional moments (laughter, shouting, excitement).
        Prioritize clips that OVERLAP with these high-energy timestamps.
        Silence zones are natural cut points — prefer starting/ending clips near silences.
        """

    # --- Gemini Prompt ---
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
        
        # JSON formatına zorlama
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=json_config
        )
        
        # Dosya temizliği
        try:
            client.files.delete(name=audio_file.name)
        except:
            pass

        # --- JSON TEMİZLİK VE ONARMA KATMANI ---
        raw_text = response.text.strip()
        
        # Markdown bloklarını temizle
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
        
        # --- SCHEMA VALIDATION ---
        validated = validate_clips(parsed_json)
        return validated
            
    except Exception as e:
        print(f"[Analyzer] ❌ Gemini Analiz Hatası: {e}")
        return []