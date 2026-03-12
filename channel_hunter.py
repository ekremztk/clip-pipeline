"""
channel_hunter.py — Kanal Bazlı Viral Shorts DNA Toplayıcı (V1.3)
===================================================================
Kullanım: python3 channel_hunter.py

Düzeltme: Gemini Files API upload + ACTIVE bekleme sorunu çözüldü.
Artık ses dosyası inline bytes olarak gönderiliyor (küçük dosyalar için ideal).
Büyük dosyalar (>20MB) için Files API fallback kullanılır.
"""

import os
import sys
import json
import time
import re
import mimetypes
from pathlib import Path

import yt_dlp
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# --- AYARLAR ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")

MIN_VIEWS = 300_000
MAX_VIDEOS = 50
AUDIO_DIR = Path("temp_hunter")

INLINE_MAX_BYTES = 20 * 1024 * 1024  # 20MB — bunun altı inline gider
GEMINI_RETRY_DELAY = 4
MAX_RETRIES = 3

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODELS = [
    "text-embedding-004",
    "models/text-embedding-004",
    "embedding-001",
    "models/embedding-001",
]

# MIME type mapping
MIME_MAP = {
    '.m4a': 'audio/mp4',
    '.mp3': 'audio/mpeg',
    '.webm': 'audio/webm',
    '.opus': 'audio/opus',
    '.ogg': 'audio/ogg',
    '.wav': 'audio/wav',
}


# ══════════════════════════════════════════════════════════════════════
# YOUTUBE KANAL TARAMA (SADECE SHORTS)
# ══════════════════════════════════════════════════════════════════════

def is_shorts(entry: dict) -> bool:
    url = entry.get('url', '') or entry.get('id', '')
    title = entry.get('title', '')
    duration = entry.get('duration', 0) or 0
    if '/shorts/' in str(url):
        return True
    if 0 < duration <= 61:
        return True
    if '#shorts' in title.lower():
        return True
    return False


def get_channel_shorts(channel_url: str, min_views: int = MIN_VIEWS) -> list[dict]:
    print(f"\n[Hunter] Kanal taranıyor: {channel_url}")
    print(f"[Hunter] Hedef: Sadece SHORTS ({min_views:,}+ izlenme)")
    
    shorts_url = channel_url.rstrip('/')
    if '/shorts' not in shorts_url:
        shorts_url = shorts_url + '/shorts'
    
    videos = _scan_playlist(shorts_url, min_views)
    
    if not videos:
        print(f"[Hunter] /shorts boş, /videos taranıyor...")
        videos_url = channel_url.rstrip('/') + '/videos'
        videos = _scan_playlist(videos_url, min_views, filter_shorts=True)
    
    videos.sort(key=lambda v: v["views"], reverse=True)
    
    if len(videos) > MAX_VIDEOS:
        print(f"[Hunter] ⚠️ {len(videos)} bulundu, ilk {MAX_VIDEOS} işlenecek.")
        videos = videos[:MAX_VIDEOS]
    
    print(f"[Hunter] ✅ {len(videos)} Shorts filtreden geçti")
    
    for i, v in enumerate(videos[:10]):
        dur_str = f"{v['duration']}s" if v['duration'] else "?s"
        print(f"  {i+1}. {v['views']:>10,} | {dur_str:>4} | {v['title'][:55]}")
    if len(videos) > 10:
        print(f"  ... +{len(videos) - 10} daha")
    
    return videos


def _scan_playlist(url: str, min_views: int, filter_shorts: bool = False) -> list[dict]:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'force_generic_extractor': False,
        'ignoreerrors': True,
        'playlistend': 500,
    }
    
    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result:
                return []
            
            entries = result.get('entries', [])
            channel_name = result.get('channel', result.get('uploader', ''))
            if channel_name:
                print(f"[Hunter] Kanal: {channel_name}")
            print(f"[Hunter] Sayfada {len(entries)} video")
            
            for entry in entries:
                if not entry:
                    continue
                if filter_shorts and not is_shorts(entry):
                    continue
                
                video_url = entry.get('url', '')
                video_id = entry.get('id', '')
                if not video_url and video_id:
                    video_url = f"https://www.youtube.com/shorts/{video_id}"
                elif not video_url:
                    continue
                if not video_url.startswith('http'):
                    video_url = f"https://www.youtube.com/shorts/{video_url}"
                
                view_count = entry.get('view_count', 0) or 0
                duration = entry.get('duration', 0) or 0
                title = entry.get('title', 'Başlıksız')
                
                if view_count >= min_views:
                    videos.append({
                        "url": video_url,
                        "title": title,
                        "views": view_count,
                        "duration": duration,
                    })
    except Exception as e:
        print(f"[Hunter] Tarama hatası: {e}")
    
    return videos


# ══════════════════════════════════════════════════════════════════════
# SES İNDİRME
# ══════════════════════════════════════════════════════════════════════

def download_audio(video_url: str, index: int) -> str | None:
    AUDIO_DIR.mkdir(exist_ok=True)
    output_path = str(AUDIO_DIR / f"hunter_{index:03d}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        for ext in ['m4a', 'webm', 'mp3', 'opus', 'ogg']:
            path = f"{output_path}.{ext}"
            if os.path.exists(path):
                return path
        return None
    except Exception as e:
        print(f"  [!] İndirme hatası: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# GEMİNİ ANALİZ (INLINE BYTES — ACTIVE SORUNU YOK)
# ══════════════════════════════════════════════════════════════════════

def get_audio_mime(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return MIME_MAP.get(ext, 'audio/mp4')


def analyze_viral_dna(audio_path: str, video_title: str, view_count: int) -> dict | None:
    """
    Gemini ile Shorts viral DNA analizi.
    Küçük dosyalar (<20MB) inline bytes ile gönderilir — ACTIVE bekleme yok.
    Büyük dosyalar Files API ile yüklenir.
    """
    file_size = os.path.getsize(audio_path)
    mime_type = get_audio_mime(audio_path)
    
    prompt = f"""
    Analyze this viral YouTube Shorts audio. 
    Title: "{video_title}" | Views: {view_count:,}
    
    This is a SHORT-FORM video (under 60 seconds) that went viral.
    Your analysis will train an AI that cuts long-form videos into viral Shorts clips.
    
    Analyze:
    1. THE HOOK: What exact words/moment in the first 3 seconds grabbed attention?
    2. RETENTION: How did this short keep viewers until the end?
    3. VIRAL DNA: What psychological triggers made people share/like?
    4. CONTENT PATTERN: What type of moment? (funny_reaction, hot_take, emotional_reveal, 
       controversial_opinion, unexpected_answer, relatable_moment, celebrity_moment)
    
    Return ONLY valid JSON:
    {{
        "hook_text": "Exact attention-grabbing first sentence",
        "transcript_segment": "Key 10-20 second transcript of most viral part",
        "why_it_went_viral": "Detailed: psychological triggers, content pattern, retention. Be SPECIFIC.",
        "viral_score": 85,
        "content_pattern": "e.g. funny_reaction"
    }}
    
    Score: 300k-500k=75-80, 500k-1M=80-85, 1M-5M=85-90, 5M-10M=90-95, 10M+=95+
    """
    
    json_config = types.GenerateContentConfig(response_mime_type="application/json")
    
    for attempt in range(MAX_RETRIES):
        try:
            if file_size <= INLINE_MAX_BYTES:
                # ── INLINE YÖNTEM (küçük dosyalar — ACTIVE sorunu yok) ──
                with open(audio_path, 'rb') as f:
                    audio_bytes = f.read()
                
                audio_part = types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type
                )
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[audio_part, prompt],
                    config=json_config
                )
            else:
                # ── FILES API (büyük dosyalar) ──
                print(f"  📤 Büyük dosya ({file_size // 1024 // 1024}MB), Files API kullanılıyor...")
                audio_file = client.files.upload(file=audio_path)
                time.sleep(8)  # Büyük dosya için daha uzun bekleme
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[audio_file, prompt],
                    config=json_config
                )
                
                try:
                    client.files.delete(name=audio_file.name)
                except:
                    pass
            
            # Cevabı parse et
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
                raw = re.sub(r"\s*```$", "", raw)
            
            return json.loads(raw)
        
        except json.JSONDecodeError as je:
            print(f"  [!] JSON hatası: {je}")
            return None
        
        except Exception as e:
            error_str = str(e)
            
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                wait = 30 if attempt < 2 else 60
                print(f"  [!] Rate limit, {wait}s bekleniyor...")
                time.sleep(wait)
                continue
            
            if 'FAILED_PRECONDITION' in error_str:
                print(f"  [!] Dosya hazır değil (deneme {attempt+1}), 10s bekleniyor...")
                time.sleep(10)
                continue
            
            print(f"  [!] Gemini hatası (deneme {attempt+1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(5)
                continue
            return None
    
    return None


# ══════════════════════════════════════════════════════════════════════
# EMBEDDING & VERİTABANI
# ══════════════════════════════════════════════════════════════════════

def get_embedding(text: str) -> list | None:
    for model_name in EMBEDDING_MODELS:
        try:
            result = client.models.embed_content(model=model_name, contents=text)
            return result.embeddings[0].values
        except:
            continue
    return None


def save_to_db(title: str, dna: dict, vector: list | None, source_url: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if supabase_url and supabase_key:
        try:
            from supabase import create_client
            sb = create_client(supabase_url, supabase_key)
            entry = {
                "video_title": title,
                "hook_text": dna.get("hook_text", ""),
                "transcript_segment": dna.get("transcript_segment", ""),
                "why_it_went_viral": dna.get("why_it_went_viral", ""),
                "viral_score": dna.get("viral_score", 80),
                "source_url": source_url,
            }
            if vector:
                entry["embedding"] = vector
            sb.table("viral_library").insert(entry).execute()
            return True
        except Exception as e:
            print(f"  [!] Supabase hatası: {e}")
    
    if DATABASE_URL:
        try:
            import psycopg2
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO viral_library 
                        (video_title, hook_text, transcript_segment, why_it_went_viral, viral_score, embedding, source_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (title, dna.get("hook_text",""), dna.get("transcript_segment",""),
                          dna.get("why_it_went_viral",""), dna.get("viral_score",80), vector, source_url))
            return True
        except Exception as e:
            print(f"  [!] PostgreSQL hatası: {e}")
    
    return False


def check_duplicate(source_url: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        try:
            from supabase import create_client
            sb = create_client(supabase_url, supabase_key)
            result = sb.table("viral_library").select("id").eq("source_url", source_url).execute()
            return len(result.data) > 0
        except:
            pass
    return False


# ══════════════════════════════════════════════════════════════════════
# ANA MOTOR
# ══════════════════════════════════════════════════════════════════════

def process_channel(channel_url: str, min_views: int = MIN_VIEWS):
    videos = get_channel_shorts(channel_url, min_views)
    
    if not videos:
        print("\n[Hunter] Filtreye uyan Shorts bulunamadı.")
        return
    
    print(f"\n{'='*60}")
    print(f"  {len(videos)} Shorts işlenecek.")
    print(f"  Tahmini: ~{len(videos) * 30 // 60} dakika")
    print(f"{'='*60}")
    
    confirm = input("\nDevam? (e/n): ").strip().lower()
    if confirm != 'e':
        print("[Hunter] İptal.")
        return
    
    success = skip = fail = 0
    
    for i, video in enumerate(videos):
        print(f"\n[{i+1}/{len(videos)}] {video['title'][:60]}")
        print(f"  İzlenme: {video['views']:,} | URL: {video['url']}")
        
        if check_duplicate(video['url']):
            print(f"  ⏭️ Zaten var.")
            skip += 1
            continue
        
        print(f"  📥 İndiriliyor...")
        audio_path = download_audio(video['url'], i)
        
        if not audio_path:
            fail += 1
            continue
        
        try:
            print(f"  🧠 Analiz ediliyor...")
            dna = analyze_viral_dna(audio_path, video['title'], video['views'])
            
            if not dna:
                fail += 1
                continue
            
            print(f"  🔢 Embedding...")
            vector = get_embedding(dna.get("why_it_went_viral", ""))
            
            print(f"  💾 Kayıt...")
            saved = save_to_db(video['title'], dna, vector, video['url'])
            
            if saved:
                pattern = dna.get('content_pattern', '?')
                print(f"  ✅ Skor: {dna.get('viral_score', '?')} | Pattern: {pattern}")
                print(f"     Hook: {dna.get('hook_text', '')[:80]}")
                success += 1
            else:
                fail += 1
            
            if i < len(videos) - 1:
                time.sleep(GEMINI_RETRY_DELAY)
        
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
    
    if AUDIO_DIR.exists():
        import shutil
        shutil.rmtree(AUDIO_DIR, ignore_errors=True)
    
    print(f"\n{'='*60}")
    print(f"  TAMAMLANDI | ✅ {success} | ⏭️ {skip} | ❌ {fail}")
    print(f"  RAG'a eklenen: +{success}")
    print(f"{'='*60}")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   PROGNOT — VİRAL SHORTS DNA TOPLAYICI V1.3            ║")
    print("║   Inline Bytes | ACTIVE Sorunu Yok | Shorts Only       ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    if not GEMINI_API_KEY:
        print("[!] GEMINI_API_KEY yok."); sys.exit(1)
    
    db_ok = DATABASE_URL or (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))
    if not db_ok:
        print("[!] DB bağlantısı yok."); sys.exit(1)
    
    print("DB: ✅ | Gemini: ✅\n")
    
    while True:
        url = input("Kanal URL ('q' çıkış): ").strip()
        if url.lower() in ('q','quit','exit',''):
            break
        if 'youtube.com' not in url and 'youtu.be' not in url:
            print("[!] Geçerli YouTube URL girin."); continue
        
        custom = input(f"Min izlenme ({MIN_VIEWS:,}, Enter=varsayılan): ").strip()
        min_v = MIN_VIEWS
        if custom:
            try: min_v = int(custom.replace(',','').replace('.',''))
            except: pass
        
        process_channel(url, min_v)
        print()