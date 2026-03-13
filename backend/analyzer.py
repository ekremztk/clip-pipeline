"""
analyzer.py (V2.0 - Supabase RAG + Schema Validation)
------------------------------------------------------
RAG sorguları artık Supabase PostgreSQL üzerinden yapılır.
DATABASE_URL tanımlı değilse Supabase connection string otomatik oluşturulur.
"""

import os
import tempfile
import psycopg2  # type: ignore
import json
import re
from google import genai  # type: ignore
from google.genai import types  # type: ignore

# --- AYARLAR ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GCP_PROJECT = os.getenv("GCP_PROJECT")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GCP_CREDENTIALS_JSON = os.getenv("GCP_CREDENTIALS_JSON")

if GCP_CREDENTIALS_JSON:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        f.write(GCP_CREDENTIALS_JSON)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path

if GCP_PROJECT:
    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

# RAG veritabanı bağlantısı: Önce DATABASE_URL, yoksa Supabase
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")

MIN_CLIP_DURATION = 15
MAX_CLIP_DURATION = 35

EMBEDDING_MODELS = [
    "text-embedding-004",
    "text-embedding-005",
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

def _parse_timestamp(val) -> float:
    """MM:SS veya SS formatındaki timestamp'i float saniyeye çevirir."""
    try:
        s = str(val).strip()
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return float(s)
    except Exception:
        return 0.0


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
            start = _parse_timestamp(clip.get("start_time", 0))
            end = _parse_timestamp(clip.get("end_time", 0))
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
        You are a specialized viral content editor for "Speedy Cast Clip" — a proven YouTube Shorts channel with 276+ videos and 93M+ views that clips English-language podcasts and talk shows.

        ═══════════════════════════════════════════════════════
        RAG CONTEXT — PROVEN VIRAL DNA FROM THIS CHANNEL:
        {ref_text}
        Study these references carefully. Match their hook style, tone, and content patterns.
        ═══════════════════════════════════════════════════════

        {transcript_block}

        {energy_block}

        ═══════════════════════════════════════════════════════
        CURRENT VIDEO: "{video_title}"
        ═══════════════════════════════════════════════════════

        YOUR MISSION: Extract exactly 3 clips with the highest viral potential for YouTube Shorts.

        ── CLIP DURATION ───────────────────────────────────────
        - Target: {ch_min}–{ch_max} seconds. Hard limit: never exceed {ch_max}s.
        - NEVER cut mid-sentence. Use transcript word-level timestamps for exact boundaries.
        - Add 0.5s buffer to end_time for natural fade.
        - If the best moment is slightly over {ch_max}s, note exactly what to trim (filler words, silence, repeated phrase).

        ── MULTI-DIMENSIONAL ANALYSIS ──────────────────────────
        Analyze each candidate moment across three dimensions:

        AUDIO SIGNALS:
        - Tone shifts: excitement spike, tension build, whisper→shout, dramatic pause
        - Laugh moments: any laughter (studio audience or speaker) — note exact second, strong viral signal
        - Pacing: accelerating speech, emphasized words, rhythm breaks
        - Atmosphere: applause, music sting, sound effects, crowd reaction
        - Silence: unexpected pause before a punchline or revelation

        CONTENT SIGNALS:
        - The core: what exactly is being said or revealed in this moment?
        - Story arc: does it complete a setup→punchline or question→answer or reveal→reaction cycle?
        - Hook quality: can someone understand and be hooked within 2 seconds, with zero context?
        - Shareability: is this something someone would immediately send to a friend?

        VISUAL SIGNALS (infer from audio/content context):
        - Facial expression value: shock, laughter, embarrassment, disgust, confusion (thumbnail potential)
        - Physical reaction: leaning in, covering mouth, pointing, gesturing
        - Speaker dynamics: are multiple people reacting? interrupting? laughing simultaneously?

        ── CONTENT PRIORITY (highest to lowest) ────────────────
        ✅ TIER 1 — Almost guaranteed viral:
           • Celebrity conflict, beef, or tension between people
           • Unexpected confession or shocking revelation ("I never told anyone this...")
           • Self-deprecating or embarrassing story told by a famous person
           • A-list celebrity's unknown past (failed career, rejected audition, secret hobby)

        ✅ TIER 2 — High viral potential:
           • Roasting dynamic between two people (host vs guest)
           • Edgy, controversial, or taboo opinion stated confidently
           • Funny physical reaction caught mid-sentence
           • "What if" scenario that reframes someone's entire career or life

        ✅ TIER 3 — Solid viral content:
           • Relatable moment with universal emotion (everyone's been there)
           • Satisfying punchline that pays off a setup from the same clip
           • Two-person chemistry moment (unexpected agreement, shared laughter)

        ❌ NEVER SELECT:
           • Inside references that require watching the full episode to understand
           • Political opinion pieces or long ideological monologues
           • Flat-toned, low-energy talking-head segments
           • Clips that start or end mid-thought with no resolution

        ── HOOK RULE (NON-NEGOTIABLE) ──────────────────────────
        The first 2–3 seconds must be scroll-stopping. The viewer is mid-scroll on their phone.
        Strong hook types:
        • Shocking mid-thought opener: "I nearly got arrested for that..."
        • Laugh explosion that starts the clip
        • Provocative question with stakes: "Did you actually threaten to quit?"
        • Visual reaction moment: gasp, spit-take, face cover
        • Name-drop with tension: "So Elon turns to me and says..."
        Weak hook (avoid): "So, um, basically what happened was..." or slow scene-setting

        ── TITLE RULES ─────────────────────────────────────────
        Format: [guest name] + [the moment] + [1-3 emojis]
        Rules: ALL lowercase (no caps except proper nouns), max 70 chars, punchy and specific
        Good examples:
        • "cillian murphy on almost becoming a rock star 🎸😂"
        • "ice cube was getting mad at kevin hart 😨😂"
        • "kit harington regrets saying he'd do anything 😳🎬"
        • "jake gyllenhaal on people mispronouncing his name 😂📛"
        Bad examples (too vague, wrong format):
        • "Funny Celebrity Moment! 😂" ❌
        • "Actor Reveals Shocking Secret" ❌

        ── DESCRIPTION RULES ───────────────────────────────────
        3 sentences max:
        1. Who + what happened (expand the title, add the key detail)
        2. The surprising context, backstory, or consequence
        3. (Optional) Reaction hook or cliffhanger closer
        Good example:
        "Cillian Murphy reveals the real reason behind Tommy Shelby's iconic Peaky Blinders haircut.
        Turns out barbers at the time had a very specific — and stomach-turning — method.
        You'll never look at it the same way again."

        ── HASHTAG RULES ───────────────────────────────────────
        Always include base tags: #comedy #funny #actor #celebrities #talkshow #interview #comedygold #comedyclips
        Then add 8–12 specific tags (all lowercase, space-separated):
        • Guest's name (e.g. #cillianmurphy)
        • Their known projects/films (e.g. #peakyblinders #oppenheimer)
        • The clip topic (e.g. #behindthescenes #haircut)
        • Any trending context if relevant (e.g. #emmys #oscars)
        Total: 16–20 hashtags per clip.

        ── OUTPUT RULES ────────────────────────────────────────
        - Output ONLY a valid JSON array. Zero markdown. Zero explanation outside JSON.
        - Timestamps in raw SECONDS (float), NOT MM:SS format.
        - If transcript is available, timestamps MUST align with exact sentence boundaries.
        - Prioritize clips that overlap with audio energy peaks.
        - virality_score: be honest. 95+ only for genuinely exceptional moments. Most clips: 75–90.

        JSON FORMAT (no deviations):
        [
          {{
            "start_time": 124.5,
            "end_time": 154.0,
            "hook_text": "The exact first sentence or sound in the clip that stops the scroll",
            "psychological_trigger": "One of: shock_value | unexpected_revelation | self_deprecation | celebrity_conflict | embarrassment | humor_subversion | relatable_moment | controversy | laugh_explosion",
            "rag_reference_used": "Exact title of matching RAG reference, or 'None'",
            "virality_score": 92,
            "why_selected": "Specific: name the hook, the dynamic, what makes it shareable, which tier it falls in",
            "suggested_title": "all lowercase guest name first then moment then 1-3 emojis — max 70 chars",
            "suggested_description": "Sentence 1: who + what. Sentence 2: surprising context. Sentence 3 (optional): hook closer.",
            "suggested_hashtags": "#comedy #funny #actor #celebrities #talkshow #interview #comedygold #comedyclips #guestname #theirproject #cliptopic [add more specific tags]",
            "audio_energy_note": "Which audio signal or energy peak made this moment stand out",
            "trim_note": "If over {ch_max}s: exactly what phrase/second to cut. Otherwise: none"
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