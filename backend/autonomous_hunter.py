import os
import json
import psycopg2
from google import genai
import yt_dlp
from dotenv import load_dotenv

# .env dosyasındaki değişkenleri yükle
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

def get_embedding(text):
    try:
        result = client.models.embed_content(model="text-embedding-004", contents=text)
        return result.embeddings[0].values
    except Exception as e:
        print(f"[!] Embedding hatası: {e}")
        return None

def process_and_save(video_url):
    """Videonun DNA'sını çıkarıp Railway'e işleyen ana motor."""
    audio_path = "temp_hunter_audio.m4a"
    try:
        print(f"[*] Analiz ediliyor: {video_url}")
        
        # 1. YouTube'dan Sesi İndir (Lokal bypass için Mac'indesin)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'temp_hunter_audio.%(ext)s',
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            title = info.get('title', 'Unknown')

        # 2. Gemini Analizi
        audio_file = client.files.upload(file=audio_path)
        prompt = "Analyze this viral video. Return ONLY JSON: {'hook_text': '...', 'why_it_went_viral': '...', 'viral_score': 95}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config={"response_mime_type": "application/json"}
        )
        dna = json.loads(response.text)
        
        # 3. Vektör (Embedding) Oluşturma
        vector = get_embedding(dna["why_it_went_viral"])
        
        # 4. Railway'e Güvenli Kayıt (Context Manager ile)
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                query = """
                INSERT INTO viral_library (video_title, why_it_went_viral, embedding, source_url)
                VALUES (%s, %s, %s, %s)
                """
                cur.execute(query, (title, dna["why_it_went_viral"], vector, video_url))
        
        print(f"[✔] Kütüphane Güncellendi: {title}")

    except Exception as e:
        print(f"[!] Hata oluştu: {e}")
    finally:
        # Railway limitlerini korumak için temizlik şart!
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if 'audio_file' in locals():
            client.files.delete(name=audio_file.name)